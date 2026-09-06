"""
低置信度过滤器

规则：
- confidence < threshold 的 BUY/SELL 自动 HOLD
- 风控强制单（止损/强平）不受此限制
- 缺失 confidence 视为 0
"""

from agent.common.models import ActionType, DecisionItem, OrderSource
from agent.common.logger import get_logger

logger = get_logger("risk.confidence")


class ConfidenceFilter:
    """低置信度过滤器"""

    def __init__(self, threshold: float = 0.60):
        self._threshold = threshold

    @property
    def threshold(self) -> float:
        return self._threshold

    def check(self, item: DecisionItem, source: OrderSource = OrderSource.DECISION) -> bool:
        """
        检查置信度是否通过。

        Args:
            item: 决策条目
            source: 订单来源

        Returns:
            True = 通过，False = 过滤
        """
        # HOLD 不过滤
        if item.action == ActionType.HOLD:
            return True

        # 风控强制单不受限制
        if source in (OrderSource.STOP_LOSS, OrderSource.LIQUIDATE):
            return True

        # 缺失 confidence 视为 0
        confidence = item.confidence if item.confidence is not None else 0.0

        if confidence < self._threshold:
            logger.info(
                "low_confidence_filtered",
                code=item.code,
                action=item.action.value,
                confidence=confidence,
                threshold=self._threshold,
            )
            return False

        return True
