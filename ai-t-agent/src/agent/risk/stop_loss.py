"""
止损检测器

规则：
- 初始化：建仓时 stop_loss_price = cost_price * 0.92
- 触发价：优先 bid1，回退 mark_price
- 深度穿透加速（enable_deep_stop_loss，默认false）：
  bid1 <= stop_loss_price * 0.98 立即触发
- 常规确认：连续 2 分钟触发（stop_breach_count >= 2）；未触发则归零
"""

from decimal import Decimal
from enum import Enum
from typing import Optional

from agent.common.models import Position, Quote
from agent.common.logger import get_logger

logger = get_logger("risk.stop_loss")


class StopLossResult(Enum):
    """止损检测结果"""
    NONE = "NONE"                    # 未触发
    BREACH_INCREMENT = "BREACH_INCREMENT"  # 触发但计数中
    TRIGGER = "TRIGGER"              # 常规触发（连续确认）
    DEEP_TRIGGER = "DEEP_TRIGGER"    # 深度穿透立即触发


class StopLossDetector:
    """止损检测器"""

    def __init__(
        self,
        enable_deep: bool = False,
        deep_threshold: Decimal = Decimal("0.98"),
        breach_confirm_count: int = 2,
    ):
        self._enable_deep = enable_deep
        self._deep_threshold = deep_threshold
        self._breach_confirm_count = breach_confirm_count

    def check(self, position: Position, quote: Quote) -> StopLossResult:
        """
        检测止损。

        Args:
            position: 持仓
            quote: 行情

        Returns:
            StopLossResult
        """
        # 确定触发价格：优先 bid1，回退 mark_price
        trigger_price = quote.bid1 if quote.bid1 is not None else quote.mark_price

        if trigger_price is None:
            return StopLossResult.NONE

        # 未击穿止损价：归零计数
        if trigger_price > position.stop_loss_price:
            position.stop_breach_count = 0
            return StopLossResult.NONE

        # 深度穿透（开关开启时）
        if self._enable_deep:
            deep_price = position.stop_loss_price * self._deep_threshold
            if trigger_price <= deep_price:
                logger.warning(
                    "deep_stop_loss",
                    code=position.code,
                    trigger_price=str(trigger_price),
                    deep_price=str(deep_price),
                    stop_loss_price=str(position.stop_loss_price),
                )
                return StopLossResult.DEEP_TRIGGER

        # 常规确认
        position.stop_breach_count += 1
        if position.stop_breach_count >= self._breach_confirm_count:
            logger.warning(
                "stop_loss_triggered",
                code=position.code,
                trigger_price=str(trigger_price),
                stop_loss_price=str(position.stop_loss_price),
                breach_count=position.stop_breach_count,
            )
            return StopLossResult.TRIGGER

        return StopLossResult.BREACH_INCREMENT
