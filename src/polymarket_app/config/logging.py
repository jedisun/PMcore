"""Logging bootstrap for PMcore.

Structured logging is initialized once during CLI startup so later service and
client modules can emit consistent records. The split between console and JSON
rendering matches the phase-1 design: console for local development, JSON for
machine-readable environments.
"""

from __future__ import annotations

import logging
import sys

import structlog

from polymarket_app.config.settings import AppSettings

_CONFIGURED = False


def configure_logging(settings: AppSettings) -> None:
    global _CONFIGURED

    # Context merging is included from the beginning because later Polymarket
    # workflows will attach fields such as account_id, token_id, and order_id.
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
    ]

    renderer: structlog.types.Processor
    if settings.log_json:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    # `force=True` keeps repeated test/bootstrap runs deterministic. This is
    # important because phase-1 tests create the app multiple times in one
    # process.
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(message)s",
        stream=sys.stdout,
        force=True,
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.dict_tracebacks,
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _CONFIGURED = True


def get_logger(name: str):
    return structlog.get_logger(name)


def is_logging_configured() -> bool:
    return _CONFIGURED
