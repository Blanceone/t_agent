"""
撮合引擎（模拟盘零滑点）

规则：
- 买入按 ask1（对手价）
- 卖出按 bid1（对手价）
- 涨跌停/停牌拒单
- 买入必须100股整数倍
- 常规卖出禁止产生零股；仅清仓允许零股
- 零滑点声明：MVP 模型，收益不可线性外推实盘
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from agent.common.models import (
    ActionType,
    FeeDetail,
    Fill,
    OrderIntent,
    OrderSource,
    Position,
    PositionState,
    Quote,
    RejectReason,
    RejectResult,
)
from agent.common.utils import gen_fill_id, gen_order_id, now_cst
from agent.trading.fee import FeeCalculator


@dataclass
class MatchResult:
    """撮合结果"""
    success: bool
    fill: Optional[Fill] = None
    reject: Optional[RejectResult] = None


class SimMatcher:
    """模拟撮合引擎（零滑点）"""

    def __init__(self, fee_calculator: FeeCalculator):
        self._fee_calc = fee_calculator

    def match(
        self,
        intent: OrderIntent,
        quote: Quote,
        position: Optional[Position],
        is_liquidation: bool = False,
        tick_id: str = "",
    ) -> MatchResult:
        """
        撮合一笔订单。

        Args:
            intent: 订单意图
            quote: 实时行情
            position: 当前持仓（卖出时需要）
            is_liquidation: 是否清仓（允许零股）
            tick_id: 当前 Tick ID

        Returns:
            MatchResult
        """
        # 1. 基础校验
        reject = self._validate(intent, quote, position, is_liquidation)
        if reject:
            return MatchResult(success=False, reject=reject)

        # 2. 确定成交价
        if intent.action == ActionType.BUY:
            price = quote.ask1
        else:
            price = quote.bid1

        # 3. 计算金额与费用
        amount = price * intent.shares
        if intent.action == ActionType.BUY:
            fee_detail = self._fee_calc.buy_fee(amount)
        else:
            fee_detail = self._fee_calc.sell_fee(amount)

        total_fee = fee_detail.total

        # 4. 计算已实现盈亏（卖出时）
        realized_pnl = None
        if intent.action == ActionType.SELL and position:
            realized_pnl = (price - position.cost_price) * intent.shares - total_fee

        # 5. 生成 Fill
        fill = Fill(
            fill_id=gen_fill_id(),
            order_id=intent.intent_id,
            code=intent.code,
            action=intent.action,
            shares=intent.shares,
            price=price,
            amount=amount,
            fee=total_fee,
            fee_detail=fee_detail,
            realized_pnl=realized_pnl,
            timestamp=now_cst(),
            tick_id=tick_id,
        )

        return MatchResult(success=True, fill=fill)

    def _validate(
        self,
        intent: OrderIntent,
        quote: Quote,
        position: Optional[Position],
        is_liquidation: bool,
    ) -> Optional[RejectResult]:
        """基础校验"""

        # 停牌
        if quote.is_suspended:
            return self._reject(intent, RejectReason.SUSPENDED, "标的停牌")

        if intent.action == ActionType.BUY:
            return self._validate_buy(intent, quote)
        else:
            return self._validate_sell(intent, quote, position, is_liquidation)

    def _validate_buy(self, intent: OrderIntent, quote: Quote) -> Optional[RejectResult]:
        """买入校验"""
        # 无 ask1
        if quote.ask1 is None:
            return self._reject(intent, RejectReason.NO_QUOTE, "无 ask1")

        # 涨停（ask1 >= limit_up 时禁止买入）
        if quote.ask1 >= quote.limit_up:
            return self._reject(intent, RejectReason.LIMIT_BOARD, "涨停无法买入")

        # 买入必须100股整数倍
        if intent.shares % 100 != 0:
            return self._reject(intent, RejectReason.INVALID_LOT, f"买入非100整数倍: {intent.shares}")

        return None

    def _validate_sell(
        self,
        intent: OrderIntent,
        quote: Quote,
        position: Optional[Position],
        is_liquidation: bool,
    ) -> Optional[RejectResult]:
        """卖出校验"""
        # 无 bid1
        if quote.bid1 is None:
            return self._reject(intent, RejectReason.NO_QUOTE, "无 bid1")

        # 跌停（bid1 <= limit_down 时禁止卖出）
        if quote.bid1 <= quote.limit_down:
            return self._reject(intent, RejectReason.LIMIT_BOARD, "跌停无法卖出")

        # 持仓检查
        if position is None:
            return self._reject(intent, RejectReason.INSUFFICIENT_SELLABLE, "无持仓")

        # 可卖数量检查
        if intent.shares > position.sellable_shares:
            return self._reject(
                intent,
                RejectReason.INSUFFICIENT_SELLABLE,
                f"可卖不足: 需{intent.shares} 有{position.sellable_shares}",
            )

        # 零股检查（非清仓禁止产生零股）
        if not is_liquidation:
            remaining = position.total_shares - intent.shares
            if 0 < remaining < 100:
                return self._reject(intent, RejectReason.ODD_LOT, f"卖出后产生零股: {remaining}")

        return None

    @staticmethod
    def _reject(intent: OrderIntent, reason: RejectReason, detail: str) -> RejectResult:
        return RejectResult(
            intent_id=intent.intent_id,
            code=intent.code,
            action=intent.action,
            reason=reason,
            detail=detail,
        )
