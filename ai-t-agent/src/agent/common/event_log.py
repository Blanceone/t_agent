"""
Event Log 统一事件日志

所有关键系统阶段必须产生事件，便于定位系统问题。
格式：event_log.jsonl
"""

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from agent.common.models import SystemEvent
from agent.common.logger import get_logger

logger = get_logger("event_log")

# 东八区
TZ_CST = timezone(timedelta(hours=8))


class EventLog:
    """统一事件日志"""

    def __init__(self, log_dir: str = "data/logs"):
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._log_dir / "event_log.jsonl"

    def emit(
        self,
        event: SystemEvent,
        tick_id: Optional[str] = None,
        date: Optional[str] = None,
        latency_ms: Optional[float] = None,
        status: str = "OK",
        detail: Optional[dict] = None,
    ):
        """
        发出一个系统事件。

        Args:
            event: 事件类型
            tick_id: 关联的 Tick ID
            date: 交易日期
            latency_ms: 阶段耗时（毫秒）
            status: OK / FAILED / SKIPPED
            detail: 补充信息
        """
        now = datetime.now(TZ_CST)
        record = {
            "timestamp": now.isoformat(timespec="milliseconds"),
            "event": event.value,
            "tick_id": tick_id,
            "date": date or now.strftime("%Y-%m-%d"),
            "latency_ms": round(latency_ms, 2) if latency_ms is not None else None,
            "status": status,
            "detail": detail or {},
        }

        try:
            with open(self._file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.error("event_log_write_failed", error=str(e), event=event.value)

    def emit_with_timer(self, event: SystemEvent, **kwargs):
        """返回一个计时器上下文管理器"""
        return _EventTimer(self, event, **kwargs)


class _EventTimer:
    """事件计时器"""

    def __init__(self, event_log: EventLog, event: SystemEvent, **kwargs):
        self._event_log = event_log
        self._event = event
        self._kwargs = kwargs
        self._start: float = 0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed_ms = (time.perf_counter() - self._start) * 1000
        status = "FAILED" if exc_type else "OK"
        self._event_log.emit(
            self._event,
            latency_ms=elapsed_ms,
            status=status,
            **self._kwargs,
        )
        return False  # 不吞异常
