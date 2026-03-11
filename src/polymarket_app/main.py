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

