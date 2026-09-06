"""
统一结构化日志（JSONL）

统一格式字段：timestamp, module, level, event, message, tick_id, decision_id, replay_id, request_id, detail
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import structlog


def setup_logging(log_level: str = "INFO", log_dir: Optional[str] = None):
    """
    统一结构化日志配置。

    Args:
        log_level: 日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)
        log_dir: 日志目录（可选，配置后输出到文件）
    """
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        processors.append(structlog.processors.JSONRenderer())

        handler = logging.FileHandler(log_path / "agent.log", encoding="utf-8")
    else:
        processors.append(structlog.dev.ConsoleRenderer())
        handler = logging.StreamHandler(sys.stdout)

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=handler.stream if hasattr(handler, 'stream') else sys.stdout),
        cache_logger_on_first_use=True,
    )

    # 同时配置标准 logging
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper(), logging.INFO),
        handlers=[handler],
    )


def get_logger(module: str) -> structlog.BoundLogger:
    """
    获取模块级 Logger。

    Usage:
        logger = get_logger("trading")
        logger.info("order_filled", tick_id="tick_001", code="600584", shares=100)
    """
    return structlog.get_logger(module=module)


def bind_tick_context(tick_id: str, replay_id: str):
    """绑定 Tick 上下文（当前 Tick 内所有日志自动携带）"""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        tick_id=tick_id,
        replay_id=replay_id,
    )


def bind_decision_context(decision_id: str, request_id: str):
    """绑定 Decision 上下文"""
    structlog.contextvars.bind_contextvars(
        decision_id=decision_id,
        request_id=request_id,
    )


def clear_context():
    """清除上下文"""
    structlog.contextvars.clear_contextvars()
