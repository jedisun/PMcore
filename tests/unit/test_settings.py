"""settings 启动与模式校验测试。

这些测试保护第一阶段最关键的启动契约：
readonly 模式必须足够轻，trading 模式必须对缺失凭证快速失败。
"""

import pytest

from polymarket_app.config.settings import Settings


def clear_pm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # 每个测试都重置已知环境变量，
    # 避免继承开发机当前环境导致结果不稳定。
    keys = [
        "APP_ENV",
        "APP_LOG_LEVEL",
        "APP_LOG_JSON",
        "APP_LOG_HTTP",
        "APP_LOG_WS",
        "DATABASE_URL",
        "DATABASE_ENABLED",
        "POLY_PRIVATE_KEY",
        "POLY_FUNDER",
        "POLY_SIGNATURE_TYPE",
        "POLY_API_KEY",
        "POLY_API_SECRET",
        "POLY_API_PASSPHRASE",
        "PM_ENABLE_TRADING",
        "PM_ENABLE_WEBSOCKET",
        "PM_MAX_ORDER_NOTIONAL",
        "PM_MAX_MARKET_EXPOSURE",
        "PM_MAX_TOTAL_EXPOSURE",
        "PM_MAX_PRICE_DEVIATION_BPS",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)


def test_settings_load_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_pm_env(monkeypatch)

    settings = Settings.load()

    assert settings.mode == "readonly"
    assert settings.app.log_level == "INFO"
    assert settings.database.database_enabled is True
    assert settings.database.database_url.startswith("postgresql+psycopg://")


def test_settings_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_pm_env(monkeypatch)
    monkeypatch.setenv("APP_LOG_LEVEL", "debug")
    monkeypatch.setenv("APP_LOG_JSON", "true")
    monkeypatch.setenv("DATABASE_ENABLED", "false")

    settings = Settings.load()

    assert settings.app.log_level == "DEBUG"
    assert settings.app.log_json is True
    assert settings.database.database_enabled is False


def test_settings_invalid_log_level_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_pm_env(monkeypatch)
    monkeypatch.setenv("APP_LOG_LEVEL", "LOUD")

    with pytest.raises(ValueError):
        Settings.load()


def test_settings_invalid_risk_value_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_pm_env(monkeypatch)
    monkeypatch.setenv("PM_MAX_ORDER_NOTIONAL", "-1")

    with pytest.raises(ValueError):
        Settings.load()


def test_readonly_mode_allows_missing_trading_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_pm_env(monkeypatch)
    monkeypatch.setenv("PM_ENABLE_TRADING", "false")

    settings = Settings.load()
    settings.validate_for_readonly()


def test_trading_mode_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_pm_env(monkeypatch)
    monkeypatch.setenv("PM_ENABLE_TRADING", "true")

    settings = Settings.load()

    # trading 模式应当在真正尝试访问 Polymarket 之前就失败。
    with pytest.raises(ValueError, match="POLY_PRIVATE_KEY"):
        settings.validate_for_trading()
