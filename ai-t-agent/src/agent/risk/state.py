"""
RiskState 状态机（NORMAL/HALT/LIQUIDATE）

三级风控：
- NORMAL: 默认，正常交易
- HALT: 日亏损率>=3% 或 累计已实现亏损>=500 → 禁止开新仓
- LIQUIDATE: 总资产回撤>=10% → 强制平仓

公式：
- 日亏损率: (last_nav - nav_mark) / last_nav >= 0.03
- 累计已实现亏损: sum(realized_pnl) <= -500
- 回撤: (peak_nav - nav_mark) / peak_nav >= 0.10
"""

from decimal import Decimal
from typing import Optional

from agent.common.models import RiskState, AccountSnapshot
from agent.common.logger import get_logger

logger = get_logger("risk.state")


class RiskStateManager:
    """三级风控状态机"""

    def __init__(
        self,
        day_loss_halt_ratio: Decimal = Decimal("0.03"),
        realized_loss_halt_abs: Decimal = Decimal("500"),
        max_drawdown_liquidate: Decimal = Decimal("0.10"),
    ):
        self._state = RiskState.NORMAL
        self._day_loss_halt_ratio = day_loss_halt_ratio
        self._realized_loss_halt_abs = realized_loss_halt_abs
        self._max_drawdown_liquidate = max_drawdown_liquidate
        self._halt_count_today = 0

    @property
    def state(self) -> RiskState:
        return self._state

    @property
    def halt_count_today(self) -> int:
        return self._halt_count_today

    def evaluate(self, snapshot: AccountSnapshot) -> RiskState:
        """
        每分钟 Tick 开始时评估风控状态。

        优先级：LIQUIDATE > HALT > NORMAL
        """
        old_state = self._state

        # 1. LIQUIDATE 优先级最高
        if snapshot.peak_nav > 0:
            drawdown = (snapshot.peak_nav - snapshot.nav_mark) / snapshot.peak_nav
            if drawdown >= self._max_drawdown_liquidate:
                new_state = RiskState.LIQUIDATE
                if old_state != new_state:
                    logger.warning(
                        "liquidate_triggered",
                        drawdown=f"{float(drawdown):.4f}",
                        peak_nav=str(snapshot.peak_nav),
                        nav_mark=str(snapshot.nav_mark),
                    )
                self._state = new_state
                return self._state

        # 2. HALT 判定
        # 2a. 日亏损率
        if snapshot.last_nav > 0:
            day_loss = (snapshot.last_nav - snapshot.nav_mark) / snapshot.last_nav
            if day_loss >= self._day_loss_halt_ratio:
                new_state = RiskState.HALT
                if old_state != new_state:
                    self._halt_count_today += 1
                    logger.warning(
                        "halt_triggered_day_loss",
                        day_loss=f"{float(day_loss):.4f}",
                        last_nav=str(snapshot.last_nav),
                        nav_mark=str(snapshot.nav_mark),
                    )
                self._state = new_state
                return self._state

        # 2b. 累计已实现亏损
        if snapshot.realized_pnl_today <= -self._realized_loss_halt_abs:
            new_state = RiskState.HALT
            if old_state != new_state:
                self._halt_count_today += 1
                logger.warning(
                    "halt_triggered_realized_loss",
                    realized_pnl=str(snapshot.realized_pnl_today),
                )
            self._state = new_state
            return self._state

        # 3. 如果当前是 HALT 但条件不再满足，不自动恢复（需等次日或 RESUME）
        # LIQUIDATE 不自动恢复
        return self._state

    def on_day_start(self) -> None:
        """次日 09:20：HALT → NORMAL（LIQUIDATE 不自动恢复）"""
        if self._state == RiskState.HALT:
            self._state = RiskState.NORMAL
            logger.info("risk_state_reset", from_state="HALT", to_state="NORMAL")
        self._halt_count_today = 0

    def on_resume(self) -> bool:
        """用户 RESUME 指令：HALT → NORMAL"""
        if self._state == RiskState.HALT:
            self._state = RiskState.NORMAL
            logger.info("risk_state_resume", from_state="HALT", to_state="NORMAL")
            return True
        return False

    def get_day_loss_ratio(self, snapshot: AccountSnapshot) -> float:
        """获取当前日亏损率"""
        if snapshot.last_nav <= 0:
            return 0.0
        return float((snapshot.last_nav - snapshot.nav_mark) / snapshot.last_nav)

    def get_drawdown_ratio(self, snapshot: AccountSnapshot) -> float:
        """获取当前回撤率"""
        if snapshot.peak_nav <= 0:
            return 0.0
        return float((snapshot.peak_nav - snapshot.nav_mark) / snapshot.peak_nav)
