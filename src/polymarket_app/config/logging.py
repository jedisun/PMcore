"""PMcore 日志初始化模块。

结构化日志只在 CLI 启动时初始化一次，
后续 service 和 client 模块复用同一套输出约定。
console / JSON 两种渲染方式也和第一阶段设计保持一致：
本地开发偏向 console，可观测性或自动化环境偏向 JSON。
"""

from __future__ import annotations

import logging
import sys

import structlog

from polymarket_app.config.settings import AppSettings

_CONFIGURED = False


def configure_logging(settings: AppSettings) -> None:
    global _CONFIGURED

    # 从第一阶段开始就保留上下文字段合并能力，
    # 后续接入 Polymarket 交易流程时，可以自然附带
    # account_id、token_id、order_id 等关键字段。
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

    # `force=True` 可以保证重复初始化时行为稳定。
    # 这一点对测试很重要，因为 phase 1 的测试会在同一进程里多次启动 CLI。
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
