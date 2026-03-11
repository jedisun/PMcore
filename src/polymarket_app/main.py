"""CLI entrypoint for PMcore phase 1.

This file intentionally exposes only bootstrap commands. It does not reach out
to Polymarket APIs yet; instead, it verifies that local configuration,
structured logging, and database connectivity checks are wired correctly.
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
    # Command bootstrap follows the design contract:
    # 1. load settings
    # 2. validate by runtime mode
    # 3. initialize logging once
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
        # The first phase only needs a connectivity probe. We intentionally do
        # not initialize metadata or run migrations here because health checks
        # must stay cheap and side-effect free.
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
    # The health payload mirrors the phase-1 design document. It reports the
    # current runtime mode, whether logging bootstrap succeeded, and whether the
    # configured database target is reachable or intentionally disabled.
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

    # Human-readable output is kept simple for local CLI use. The JSON path is
    # the stable interface for tests and future automation.
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
