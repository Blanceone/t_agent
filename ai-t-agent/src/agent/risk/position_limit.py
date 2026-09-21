"""
仓位与资金约束校验

规则：
- 20% 现金预留：available_cash - (预买金额 + 预估费用) >= nav_mark * 20%
- 单票上限：mark_price * (total_shares + new_shares) <= nav_mark * 配置比例（默认 100%，由现金预留先卡住）
- 冷却期：cooldown_until_date >= 当前日期 → 禁止 BUY
- 换仓亏损联动拒绝：同分钟亏损SELL后的跨标的BUY拒绝
"""

from decimal import Decimal
from typing import Dict, Optional

from agent.common.models import (
    AccountSnapshot,
    ActionType,
    OrderIntent,
    Position,
    Quote,
    WatchlistEntry,
)
from agent.common.logger import get_logger

logger = get_logger("risk.position_limit")


class PositionLimitChecker:
    """仓位与资金约束"""

    def __init__(
        self,
        reserved_min_cash_ratio: Decimal = Decimal("0.20"),
        max_single_position_ratio: Decimal = Decimal("0.50"),
    ):
        self._reserved_ratio = reserved_min_cash_ratio
        self._max_position_ratio = max_single_position_ratio

    def check_cash_reserve(
        self,
        snapshot: AccountSnapshot,
        intent: OrderIntent,
        quote: Quote,
        est_fee: Decimal = Decimal("0"),
    ) -> bool:
        """
        现金预留检查。

        available_cash - (预买金额 + 预估费用) >= nav_mark * 20%
        """
        if intent.action != ActionType.BUY:
            return True

        buy_amount = quote.ask1 * intent.shares if quote.ask1 else Decimal("0")
        remaining_cash = snapshot.cash_available - buy_amount - est_fee
        min_required = snapshot.nav_mark * self._reserved_ratio

        if remaining_cash < min_required:
            logger.info(
                "cash_reserve_breach",
                code=intent.code,
                remaining=str(remaining_cash),
                min_required=str(min_required),
            )
            return False
        return True

    def check_single_position(
        self,
        snapshot: AccountSnapshot,
        intent: OrderIntent,
        quote: Quote,
    ) -> bool:
        """
        单票上限检查。

        mark_price * (total_shares + new_shares) <= nav_mark * 50%
        """
        if intent.action != ActionType.BUY:
            return True

        current_shares = 0
        pos = snapshot.positions.get(intent.code)
        if pos:
            current_shares = pos.total_shares

        new_total_shares = current_shares + intent.shares
        position_value = quote.mark_price * new_total_shares
        max_allowed = snapshot.nav_mark * self._max_position_ratio

        if position_value > max_allowed:
            logger.info(
                "position_limit_breach",
                code=intent.code,
                position_value=str(position_value),
                max_allowed=str(max_allowed),
            )
            return False
        return True

    def check_cooldown(
        self,
        watchlist: Dict[str, WatchlistEntry],
        code: str,
        current_date: str,
    ) -> bool:
        """
        冷却期检查。

        cooldown_until_date >= 当前日期 → 禁止 BUY

        Returns:
            True = 可交易，False = 冷却中
        """
        entry = watchlist.get(code)
        if entry is None:
            return True
        if entry.cooldown_until_date is None:
            return True
        if entry.cooldown_until_date >= current_date:
            logger.info("cooldown_active", code=code, until=entry.cooldown_until_date)
            return False
        return True
