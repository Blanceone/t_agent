"""
交易日历服务

判定交易日、session 类型。
"""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from agent.common.logger import get_logger

logger = get_logger("scheduler.calendar")


class TradingCalendar:
    """交易日历"""

    def __init__(self, calendar_path: Optional[str] = None):
        self._trading_days: set[str] = set()
        self._sessions: dict[str, str] = {}  # date -> full/am_only/pm_only

        if calendar_path and Path(calendar_path).exists():
            self._load(calendar_path)

    def _load(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for entry in data.get("days", []):
            d = entry["date"]
            self._trading_days.add(d)
            self._sessions[d] = entry.get("session", "full")
        logger.info("calendar_loaded", days=len(self._trading_days))

    def is_trading_day(self, d: date) -> bool:
        """是否交易日"""
        ds = d.strftime("%Y-%m-%d")
        if self._trading_days:
            return ds in self._trading_days
        # 无日历文件时：周一到周五视为交易日
        return d.weekday() < 5

    def get_session(self, d: date) -> str:
        """获取 session 类型"""
        ds = d.strftime("%Y-%m-%d")
        return self._sessions.get(ds, "full")

    def next_trading_day(self, d: date) -> date:
        """下一个交易日"""
        from datetime import timedelta
        current = d + timedelta(days=1)
        for _ in range(30):
            if self.is_trading_day(current):
                return current
            current += timedelta(days=1)
        return current
