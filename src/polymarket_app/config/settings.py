"""应用配置与运行模式校验。

这里的设计遵循 `pmdesign.md` 中已经确认的约束：

- readonly 模式必须能用最小本地配置启动
- trading 模式下，若 Polymarket 交易凭证不完整，必须尽早失败
- 数据库配置需要显式建模，因为从第一阶段开始 PostgreSQL 就是主路径
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class AppSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    app_env: str
    log_level: str
    log_json: bool
    log_http: bool
    log_ws: bool


class DatabaseSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    database_url: str
    database_enabled: bool


class PolymarketSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    private_key: str = ""
    funder: str = ""
    signature_type: str = ""
    api_key: str = ""
    api_secret: str = ""
    api_passphrase: str = ""
    enable_trading: bool = False
    enable_websocket: bool = True


class RiskSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_order_notional: float
    max_market_exposure: float
    max_total_exposure: float
    max_price_deviation_bps: int


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="dev", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="APP_LOG_LEVEL")
    log_json: bool = Field(default=False, alias="APP_LOG_JSON")
    log_http: bool = Field(default=False, alias="APP_LOG_HTTP")
    log_ws: bool = Field(default=False, alias="APP_LOG_WS")

    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/pmcore",
        alias="DATABASE_URL",
    )
    database_enabled: bool = Field(default=True, alias="DATABASE_ENABLED")

    private_key: str = Field(default="", alias="POLY_PRIVATE_KEY")
    funder: str = Field(default="", alias="POLY_FUNDER")
    signature_type: str = Field(default="", alias="POLY_SIGNATURE_TYPE")
    api_key: str = Field(default="", alias="POLY_API_KEY")
    api_secret: str = Field(default="", alias="POLY_API_SECRET")
    api_passphrase: str = Field(default="", alias="POLY_API_PASSPHRASE")
    enable_trading: bool = Field(default=False, alias="PM_ENABLE_TRADING")
    enable_websocket: bool = Field(default=True, alias="PM_ENABLE_WEBSOCKET")

    max_order_notional: float = Field(default=100, alias="PM_MAX_ORDER_NOTIONAL")
    max_market_exposure: float = Field(default=500, alias="PM_MAX_MARKET_EXPOSURE")
    max_total_exposure: float = Field(default=2000, alias="PM_MAX_TOTAL_EXPOSURE")
    max_price_deviation_bps: int = Field(default=100, alias="PM_MAX_PRICE_DEVIATION_BPS")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in VALID_LOG_LEVELS:
            raise ValueError(f"APP_LOG_LEVEL must be one of {sorted(VALID_LOG_LEVELS)}")
        return normalized

    @field_validator(
        "max_order_notional",
        "max_market_exposure",
        "max_total_exposure",
        "max_price_deviation_bps",
    )
    @classmethod
    def validate_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("risk values must be non-negative")
        return value

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("DATABASE_URL must not be empty")
        return value


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    app: AppSettings
    database: DatabaseSettings
    polymarket: PolymarketSettings
    risk: RiskSettings

    @classmethod
    def load(cls) -> "Settings":
        # BaseSettings 负责统一读取 .env 和进程环境变量。
        # 这里再把扁平环境变量整理成分组配置对象，避免下游模块直接依赖
        # 具体 env 名称，降低后续重构成本。
        raw = EnvSettings()
        return cls(
            app=AppSettings(
                app_env=raw.app_env,
                log_level=raw.log_level,
                log_json=raw.log_json,
                log_http=raw.log_http,
                log_ws=raw.log_ws,
            ),
            database=DatabaseSettings(
                database_url=raw.database_url,
                database_enabled=raw.database_enabled,
            ),
            polymarket=PolymarketSettings(
                private_key=raw.private_key,
                funder=raw.funder,
                signature_type=raw.signature_type,
                api_key=raw.api_key,
                api_secret=raw.api_secret,
                api_passphrase=raw.api_passphrase,
                enable_trading=raw.enable_trading,
                enable_websocket=raw.enable_websocket,
            ),
            risk=RiskSettings(
                max_order_notional=raw.max_order_notional,
                max_market_exposure=raw.max_market_exposure,
                max_total_exposure=raw.max_total_exposure,
                max_price_deviation_bps=raw.max_price_deviation_bps,
            ),
        )

    @property
    def mode(self) -> Literal["readonly", "trading"]:
        return "trading" if self.polymarket.enable_trading else "readonly"

    def validate_for_readonly(self) -> None:
        # readonly 模式是第一阶段 CLI 的最小启动路径。
        # 它允许缺少 Polymarket 交易凭证，但仍然要求基础运行配置正确，
        # 例如数据库检查开启时，DATABASE_URL 不能为空。
        if self.database.database_enabled and not self.database.database_url.strip():
            raise ValidationError.from_exception_data(
                "DatabaseSettings",
                [{"loc": ("database_url",), "msg": "DATABASE_URL must not be empty", "type": "value_error"}],
            )

    def validate_for_trading(self) -> None:
        self.validate_for_readonly()
        # Polymarket 的 CLOB 交易链路不只是“有私钥即可”。
        # 按官方文档，交易请求至少还涉及 signer 身份、funder 地址和
        # API credentials。这里先把这个边界卡住，确保第二、三阶段在
        # 真正发请求前就能快速失败，而不是把错误拖到网络层。
        missing = [
            name
            for name, value in {
                "POLY_PRIVATE_KEY": self.polymarket.private_key,
                "POLY_FUNDER": self.polymarket.funder,
                "POLY_SIGNATURE_TYPE": self.polymarket.signature_type,
                "POLY_API_KEY": self.polymarket.api_key,
                "POLY_API_SECRET": self.polymarket.api_secret,
                "POLY_API_PASSPHRASE": self.polymarket.api_passphrase,
            }.items()
            if not value.strip()
        ]
        if missing:
            raise ValueError(f"trading mode requires credentials: {', '.join(missing)}")
