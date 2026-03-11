"""Tests for structured logging bootstrap."""

import logging

from polymarket_app.config.logging import configure_logging, get_logger, is_logging_configured
from polymarket_app.config.settings import AppSettings


def build_settings(level: str = "INFO", json_mode: bool = False) -> AppSettings:
    return AppSettings(
        app_env="test",
        log_level=level,
        log_json=json_mode,
        log_http=False,
        log_ws=False,
    )


def test_configure_logging_is_idempotent() -> None:
    settings = build_settings()

    # CLI bootstrap and tests may initialize logging multiple times in one
    # interpreter session, so repeated configuration must stay safe.
    configure_logging(settings)
    configure_logging(settings)

    assert is_logging_configured() is True


def test_configure_logging_sets_root_level() -> None:
    configure_logging(build_settings(level="DEBUG"))

    assert logging.getLogger().level == logging.DEBUG


def test_get_logger_returns_bound_logger() -> None:
    configure_logging(build_settings())
    logger = get_logger("test.logger")

    assert logger is not None


def test_json_mode_configures_logging() -> None:
    configure_logging(build_settings(json_mode=True))

    assert is_logging_configured() is True
