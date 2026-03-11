"""PMcore 第一阶段 CLI 入口。

这个文件当前只暴露启动与基础检查命令，
还不会真正访问 Polymarket API。
它的职责是先验证本地配置、结构化日志和数据库连通性
已经按设计接好。
"""

from __future__ import annotations

import json
from typing import Any

import typer
from sqlalchemy import create_engine, text

from polymarket_app import __version__
from polymarket_app.config.logging import configure_logging, is_logging_configured
from polymarket_app.config.settings import Settings

app = typer.Typer(no_args_is_help=True)
health_app = typer.Typer(help="Health checks")
app.add_typer(health_app, name="health")


def _load_settings() -> Settings:
    # 命令启动流程遵循设计文档约定：
    # 1. 加载 settings
    # 2. 按当前模式做校验
    # 3. 初始化日志
    settings = Settings.load()
    if settings.mode == "trading":
        settings.validate_for_trading()
    else:
        settings.validate_for_readonly()
    configure_logging(settings.app)
    return settings


def _database_status(settings: Settings) -> dict[str, Any]:
    if not settings.database.database_enabled:
        return {"enabled": False, "status": "disabled"}

    try:
        # 第一阶段这里只做数据库连通性探测。
        # 故意不在 health check 里初始化 metadata 或执行迁移，
        # 因为健康检查必须保持轻量、无副作用。
        engine = create_engine(settings.database.database_url, future=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return {"enabled": True, "status": "ok"}
    except Exception:
        return {"enabled": True, "status": "failed"}


@app.command()
def version() -> None:
    typer.echo(__version__)


@health_app.command("check")
def health_check(json_output: bool = typer.Option(False, "--json", help="Emit JSON output")) -> None:
    # health payload 和 phase 1 设计文档保持一致：
    # 输出当前模式、日志是否初始化成功、以及数据库目标是可连通还是被禁用。
    settings = _load_settings()
    payload = {
        "mode": settings.mode,
        "logging": {
            "configured": is_logging_configured(),
            "level": settings.app.log_level,
            "format": "json" if settings.app.log_json else "console",
        },
        "database": _database_status(settings),
    }

    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    # 人类可读输出保持简单，方便本地 CLI 使用；
    # JSON 输出则作为测试和后续自动化的稳定接口。
    typer.echo(f"mode: {payload['mode']}")
    typer.echo(
        "logging: configured={configured} level={level} format={format}".format(
            **payload["logging"],
        )
    )
    typer.echo(
        "database: enabled={enabled} status={status}".format(
            **payload["database"],
        )
    )
