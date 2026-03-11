from __future__ import annotations

import logging
import sys

import structlog

from polymarket_app.config.settings import AppSettings

_CONFIGURED = False


def configure_logging(settings: AppSettings) -> None:
    global _CONFIGURED

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
