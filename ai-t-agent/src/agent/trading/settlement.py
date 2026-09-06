"""
T+1 解冻 / 日切结算

日切（09:20）：
1. T+1 解冻（sellable_shares = total_shares, today_bought = 0）
2. 清零 stop_breach_count
3. 清理过期冷却期
4. 检查 PENDING_CLEAR / 未完成清仓
5. 等权基准若 watchlist 变更则清空重建
6. HALT → NORMAL
"""

from typing import Dict, List

from agent.common.models import (
    Position,
    PositionState,
    RiskState,
    WatchlistEntry,
)
from agent.common.logger import get_logger

logger = get_logger("trading.settlement")


class SettlementManager:
    """日切结算管理"""

    def on_day_start(
        self,
        positions: Dict[str, Position],
        watchlist: Dict[str, WatchlistEntry],
        current_date: str,
    ) -> None:
        """
        日切处理。

        Args:
            positions: 持仓字典
            watchlist: 股票池
            current_date: 当前日期 YYYY-MM-DD
        """
        # 1. T+1 解冻 + 清零 stop_breach_count
        for code, pos in positions.items():
            pos.sellable_shares = pos.total_shares
            pos.today_bought = 0
            pos.stop_breach_count = 0

        # 2. 清理过期冷却期
        self._clear_expired_cooldown(watchlist, current_date)

        logger.info("day_start_settlement", positions=len(positions), date=current_date)

    def _clear_expired_cooldown(self, watchlist: Dict[str, WatchlistEntry], current_date: str) -> None:
        """
        冷却校验：cooldown_until_date >= 当前日期 时禁止 BUY。
        次日 09:20：若 当前日期 > cooldown_until_date，清除冷却字段。
        """
        for code, entry in watchlist.items():
            if entry.cooldown_until_date and current_date > entry.cooldown_until_date:
                entry.cooldown_until_date = None
                logger.info("cooldown_cleared", code=code, date=current_date)

    def is_in_cooldown(self, watchlist: Dict[str, WatchlistEntry], code: str, current_date: str) -> bool:
        """检查是否在冷却期"""
        entry = watchlist.get(code)
        if entry is None:
            return False
        if entry.cooldown_until_date is None:
            return False
        return entry.cooldown_until_date >= current_date
