"""
RiskEngine 主类

风控流程：Decision → Risk → Execution
Risk 永远优先，不可绕过。

校验流水线：
1. risk_state == LIQUIDATE → 忽略所有
2. risk_state == HALT && action == BUY → REJECT
3. confidence < threshold → REJECT(LOW_CONFIDENCE)
4. BUY: 冷却期 → 现金预留 → 单票上限
5. SELL: sellable_shares 检查
6. PASS
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional

from agent.common.models import (
    AccountSnapshot,
    ActionType,
    DecisionItem,
    OrderIntent,
    OrderSource,
    Position,
    PositionState,
    Quote,
    RejectReason,
    RiskSnapshot,
    RiskState,
    RiskVerdict,
    WatchlistEntry,
)
from agent.common.event_log import EventLog
from agent.common.logger import get_logger
from agent.config.schema import RiskConfig
from agent.risk.confidence_filter import ConfidenceFilter
from agent.risk.position_limit import PositionLimitChecker
from agent.risk.state import RiskStateManager
from agent.risk.stop_loss import StopLossDetector, StopLossResult

logger = get_logger("risk.engine")


@dataclass
class TickGuardResult:
    """Tick 开始风控扫描结果"""
    state_changed: bool
    new_state: RiskState
    stop_loss_codes: List[str]  # 需要止损清仓的标的


class RiskEngine:
    """风控引擎主类"""

    def __init__(self, config: RiskConfig, event_log: Optional[EventLog] = None):
        self._config = config
        self._event_log = event_log

        self.state_mgr = RiskStateManager(
            day_loss_halt_ratio=config.day_loss_halt_ratio,
            realized_loss_halt_abs=config.realized_loss_halt_abs,
            max_drawdown_liquidate=config.max_drawdown_liquidate,
        )
        self.stop_loss_detector = StopLossDetector(
            enable_deep=config.enable_deep_stop_loss,
            deep_threshold=config.deep_stop_loss_threshold,
            breach_confirm_count=config.stop_breach_confirm_count,
        )
        self.confidence_filter = ConfidenceFilter(
            threshold=config.decision_confidence_threshold,
        )
        self.position_checker = PositionLimitChecker(
            reserved_min_cash_ratio=config.reserved_min_cash_ratio,
            max_single_position_ratio=config.max_single_position_ratio,
        )

        self._stop_loss_count_today = 0

    @property
    def risk_state(self) -> RiskState:
        return self.state_mgr.state

    def tick_guard(self, snapshot: AccountSnapshot, quotes: Dict[str, Quote]) -> TickGuardResult:
        """
        每分钟 Tick 开始调用（优先级最高）。

        1. 评估风控状态（HALT/LIQUIDATE）
        2. 扫描所有持仓止损
        3. 返回需要执行的止损清仓列表
        """
        old_state = self.state_mgr.state

        # 1. 评估状态
        new_state = self.state_mgr.evaluate(snapshot)
        state_changed = old_state != new_state

        # 2. 止损扫描
        stop_loss_codes: List[str] = []
        for code, pos in snapshot.positions.items():
            if pos.total_shares <= 0:
                continue
            if code not in quotes:
                continue

            result = self.stop_loss_detector.check(pos, quotes[code])
            if result in (StopLossResult.TRIGGER, StopLossResult.DEEP_TRIGGER):
                stop_loss_codes.append(code)
                self._stop_loss_count_today += 1

        return TickGuardResult(
            state_changed=state_changed,
            new_state=new_state,
            stop_loss_codes=stop_loss_codes,
        )

    def validate_decision(
        self,
        item: DecisionItem,
        snapshot: AccountSnapshot,
        quote: Quote,
        watchlist: Dict[str, WatchlistEntry],
        current_date: str,
        source: OrderSource = OrderSource.DECISION,
        t_status: str = "open",
    ) -> RiskVerdict:
        """
        校验单条 Decision。

        校验流水线顺序不可变。
        t_status: open | buyback_only | hold_only（由决策层按成交与计划计算）
        """
        # 1. LIQUIDATE 下忽略所有
        if self.state_mgr.state == RiskState.LIQUIDATE:
            return RiskVerdict(False, RejectReason.HALT, "LIQUIDATE state")

        # 2. HALT 下禁止 BUY
        if self.state_mgr.state == RiskState.HALT and item.action == ActionType.BUY:
            return RiskVerdict(False, RejectReason.HALT, "HALT state, BUY forbidden")

        # 2b. 做T次数已闭环：只允许 HOLD
        if t_status == "hold_only" and item.action in (ActionType.BUY, ActionType.SELL):
            return RiskVerdict(False, RejectReason.T_BUDGET_EXCEEDED,
                               "T budget exhausted, HOLD only")

        # 3. confidence 过滤
        if item.action in (ActionType.BUY, ActionType.SELL):
            if not self.confidence_filter.check(item, source):
                return RiskVerdict(False, RejectReason.LOW_CONFIDENCE,
                                   f"confidence {item.confidence} < {self.confidence_filter.threshold}")

        # 4. BUY 约束
        if item.action == ActionType.BUY:
            # 4-pre. 仓位状态检查：CLEARING/LIQ_FAIL 禁止买入
            pos = snapshot.positions.get(item.code)
            if pos and pos.position_state not in (PositionState.ACTIVE,):
                return RiskVerdict(False, RejectReason.HALT,
                                   f"Position state {pos.position_state.value} forbids BUY")

            intent = OrderIntent(
                intent_id="risk_check",
                action=ActionType.BUY,
                code=item.code,
                shares=item.shares,
                source=source,
            )

            # 4a. 冷却期
            if not self.position_checker.check_cooldown(watchlist, item.code, current_date):
                return RiskVerdict(False, RejectReason.COOLDOWN, "In cooldown period")

            # 4b. 现金预留（含最低佣金估算）
            est_fee = Decimal("5")  # 最低佣金作为保守估计
            if not self.position_checker.check_cash_reserve(snapshot, intent, quote, est_fee=est_fee):
                return RiskVerdict(False, RejectReason.CASH_RESERVE, "Cash reserve insufficient")

            # 4c. 单票上限
            if not self.position_checker.check_single_position(snapshot, intent, quote):
                return RiskVerdict(False, RejectReason.POSITION_LIMIT, "Single position limit exceeded")

        # 5. SELL 约束
        if item.action == ActionType.SELL:
            pos = snapshot.positions.get(item.code)
            if pos is None or item.shares > pos.sellable_shares:
                return RiskVerdict(False, RejectReason.INSUFFICIENT_SELLABLE, "Insufficient sellable shares")

        # 6. PASS
        return RiskVerdict(True)

    def get_risk_snapshot(self, snapshot: AccountSnapshot) -> RiskSnapshot:
        """获取风控状态快照（注入 Context）"""
        return RiskSnapshot(
            risk_state=self.state_mgr.state,
            day_loss_ratio=self.state_mgr.get_day_loss_ratio(snapshot),
            drawdown_ratio=self.state_mgr.get_drawdown_ratio(snapshot),
            realized_pnl_today=snapshot.realized_pnl_today,
            halt_count_today=self.state_mgr.halt_count_today,
            stop_loss_count_today=self._stop_loss_count_today,
        )

    def on_day_start(self) -> None:
        """日切重置"""
        self.state_mgr.on_day_start()
        self._stop_loss_count_today = 0

    def on_resume(self) -> bool:
        """用户 RESUME"""
        return self.state_mgr.on_resume()
