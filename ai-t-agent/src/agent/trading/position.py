"""
持仓状态机

状态：ACTIVE → PENDING_CLEAR → CLEARING → (清零后处理)
                                        → LIQ_FAIL

T+1 制度：
- 日切时 sellable_shares = total_shares, today_bought = 0
- 买入增加 total_shares 和 today_bought，不增加 sellable_shares
- 卖出减少 total_shares 和 sellable_shares

成本：加权平均成本法
止损：cost_price * stop_loss_ratio
"""

from decimal import Decimal
from typing import Optional

from agent.common.models import Position, PositionState


class PositionManager:
    """持仓管理器"""

    def __init__(self, stop_loss_ratio: Decimal):
        self._stop_loss_ratio = stop_loss_ratio

    def create_position(self, code: str, shares: int, price: Decimal, fee: Decimal) -> Position:
        """
        建仓（首次买入）。

        成本价 = (买入金额 + 买入费用) / 数量
        止损价 = 成本价 * stop_loss_ratio
        """
        amount = price * shares
        cost_price = (amount + fee) / shares
        stop_loss_price = self._round_price(cost_price * self._stop_loss_ratio)

        return Position(
            code=code,
            total_shares=shares,
            sellable_shares=0,  # T+1：当日买入不可卖
            today_bought=shares,
            cost_price=self._round_price(cost_price),
            stop_loss_price=stop_loss_price,
            stop_breach_count=0,
            position_state=PositionState.ACTIVE,
            exit_reason=None,
        )

    def apply_buy(self, position: Position, shares: int, price: Decimal, fee: Decimal) -> None:
        """
        加仓（买入）。

        新成本价 = (原成本×原数量 + 买入金额 + 买入费用) / (原数量 + 买入数量)
        止损价随之更新。
        T+1：sellable_shares 不增加。
        """
        old_total_cost = position.cost_price * position.total_shares
        new_amount = price * shares
        new_total_shares = position.total_shares + shares

        new_cost = (old_total_cost + new_amount + fee) / new_total_shares
        position.cost_price = self._round_price(new_cost)
        position.stop_loss_price = self._round_price(new_cost * self._stop_loss_ratio)

        position.total_shares = new_total_shares
        position.today_bought += shares
        # sellable_shares 不变（T+1）

    def apply_sell(self, position: Position, shares: int, price: Decimal, fee: Decimal) -> Decimal:
        """
        卖出。

        成本价不变。
        已实现盈亏 = (卖出价 - 成本价) × 数量 - 卖出费用

        Returns:
            已实现盈亏
        """
        realized_pnl = (price - position.cost_price) * shares - fee
        position.total_shares -= shares
        position.sellable_shares -= shares
        return realized_pnl

    def on_day_start(self, position: Position) -> None:
        """
        日切：T+1 解冻。

        - sellable_shares = total_shares
        - today_bought = 0
        - stop_breach_count = 0
        """
        position.sellable_shares = position.total_shares
        position.today_bought = 0
        position.stop_breach_count = 0

    def transition_to_clearing(self, position: Position, exit_reason: str) -> None:
        """迁移到清仓状态"""
        position.position_state = PositionState.CLEARING
        position.exit_reason = exit_reason

    def transition_to_liq_fail(self, position: Position) -> None:
        """迁移到清仓失败状态"""
        position.position_state = PositionState.LIQ_FAIL

    def is_cleared(self, position: Position) -> bool:
        """是否已清零"""
        return position.total_shares == 0

    def can_buy(self, position: Position) -> bool:
        """是否允许买入"""
        return position.position_state == PositionState.ACTIVE

    def can_sell(self, position: Position) -> bool:
        """是否允许卖出（含清仓）"""
        return position.position_state in (
            PositionState.ACTIVE,
            PositionState.CLEARING,
        )

    @staticmethod
    def _round_price(value: Decimal) -> Decimal:
        """价格保留4位小数（A股精度）"""
        return value.quantize(Decimal("0.0001"))
