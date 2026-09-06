"""
LiquidationWorker 清仓队列

规则：
- 消费 liquidation_queue
- 每分钟最多卖 max_liquidation_shares_per_tick
- 清仓允许零股
- 连续 30 分钟未成交（跨交易日累计，不清零）→ LIQ_FAIL
"""

from decimal import Decimal
from typing import Dict, List, Optional

from agent.common.models import (
    ActionType,
    Fill,
    LiquidationTask,
    OrderIntent,
    OrderSource,
    Position,
    PositionState,
    Quote,
    RejectResult,
)
from agent.common.logger import get_logger
from agent.common.utils import gen_order_id
from agent.trading.matcher import SimMatcher, MatchResult

logger = get_logger("trading.liquidation")


class LiquidationWorker:
    """清仓队列消费者"""

    def __init__(self, matcher: SimMatcher, max_attempts: int = 30,
                 max_shares_per_tick: int = 10000):
        self._matcher = matcher
        self._max_attempts = max_attempts
        self._max_shares_per_tick = max_shares_per_tick

    def process_tick(
        self,
        queue: List[LiquidationTask],
        positions: Dict[str, Position],
        quotes: Dict[str, Quote],
        tick_id: str = "",
    ) -> tuple[List[Fill], List[RejectResult], List[str]]:
        """
        每分钟消费清仓队列。

        Args:
            queue: 清仓任务队列
            positions: 持仓字典
            quotes: 行情字典
            tick_id: Tick ID

        Returns:
            (fills, rejects, exhausted_task_ids)
        """
        fills: List[Fill] = []
        rejects: List[RejectResult] = []
        exhausted: List[str] = []

        for task in queue:
            if task.remaining_shares <= 0:
                continue

            code = task.code
            if code not in quotes:
                task.attempts += 1
                continue

            quote = quotes[code]
            position = positions.get(code)
            if position is None:
                continue

            # 本次卖出数量（拆单）
            sell_shares = min(task.remaining_shares, self._max_shares_per_tick)

            # 构造卖出意图
            intent = OrderIntent(
                intent_id=gen_order_id(),
                action=ActionType.SELL,
                code=code,
                shares=sell_shares,
                source=OrderSource.LIQUIDATE,
            )

            # 撮合（清仓模式允许零股）
            result = self._matcher.match(
                intent=intent,
                quote=quote,
                position=position,
                is_liquidation=True,
                tick_id=tick_id,
            )

            if result.success and result.fill:
                fills.append(result.fill)
                task.remaining_shares -= sell_shares
                logger.info(
                    "liquidation_fill",
                    code=code,
                    shares=sell_shares,
                    remaining=task.remaining_shares,
                    tick_id=tick_id,
                )
            else:
                task.attempts += 1
                if result.reject:
                    rejects.append(result.reject)
                logger.warning(
                    "liquidation_failed",
                    code=code,
                    attempts=task.attempts,
                    reason=result.reject.reason.value if result.reject else "unknown",
                    tick_id=tick_id,
                )

            # 检查是否耗尽
            if task.attempts >= self._max_attempts:
                exhausted.append(task.task_id)
                logger.error(
                    "liquidation_exhausted",
                    code=code,
                    attempts=task.attempts,
                    task_id=task.task_id,
                )

        return fills, rejects, exhausted

    def remove_completed(self, queue: List[LiquidationTask]) -> List[LiquidationTask]:
        """移除已完成或已耗尽的任务"""
        return [t for t in queue if t.remaining_shares > 0 and t.attempts < self._max_attempts]
