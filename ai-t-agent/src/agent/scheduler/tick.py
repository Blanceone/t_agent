"""
单 Tick 原子执行流程

严格顺序（全同步，不可并行）：
1. 锁定快照
2. 行情检查
3. RiskGuard 扫描
4. LiquidationWorker
5. 组装 Context
6. LLM Decision（单飞行）
7. Risk 校验 Decision
8. Execution + Save
9. 写 Event Log
"""

from datetime import datetime
from typing import Dict, Optional

from agent.common.models import (
    ActionType,
    OrderIntent,
    OrderSource,
    Quote,
    RiskState,
    SystemEvent,
)
from agent.common.event_log import EventLog
from agent.common.logger import get_logger, bind_tick_context
from agent.common.utils import gen_tick_id
from agent.scheduler.order_filter import (
    OncePerDay,
    conflict_drop_actions,
    is_impossible_sell,
)

logger = get_logger("scheduler.tick")


class TickExecutor:
    """单 Tick 原子执行"""

    def __init__(self, trading_engine, risk_engine, decision_engine,
                 market_service, context_assembler, event_log: EventLog):
        self._trading = trading_engine
        self._risk = risk_engine
        self._decision = decision_engine
        self._market = market_service
        self._context = context_assembler
        self._event_log = event_log
        # Replay 决策全量快照（由 Scheduler 日切时注入）
        self._replay_store = None
        self._replay_date = ""
        self._once = OncePerDay()

    def set_replay(self, date: str, replay_store) -> None:
        """日切时注入当日 Replay 存储"""
        self._replay_date = date
        self._replay_store = replay_store

    def execute(self, now: datetime, system_mode: str = "NORMAL") -> Optional[str]:
        """
        执行一个完整 Tick。

        Returns:
            tick_id 或 None（跳过时）
        """
        tick_id = gen_tick_id()
        date_str = now.strftime("%Y-%m-%d")
        bind_tick_context(tick_id, f"replay_{date_str.replace('-', '')}")

        self._event_log.emit(SystemEvent.TICK_STARTED, tick_id=tick_id, date=date_str)

        # Step 0: 检查 CLI 外部修改（REMOVE/SET_CASH 等），有信号则重载账户
        self._trading.reload_if_cli_changed()

        # Step 1: 锁定快照
        quotes = self._market.get_quotes()
        if not quotes:
            self._event_log.emit(SystemEvent.SKIP_STALE, tick_id=tick_id, date=date_str)
            return None

        snapshot = self._trading.account.snapshot(quotes)

        # Step 2: 行情新鲜度检查
        if self._is_stale(quotes, now):
            self._event_log.emit(SystemEvent.SKIP_STALE, tick_id=tick_id, date=date_str)
            return None

        # Step 3: RiskGuard 扫描
        guard_result = self._risk.tick_guard(snapshot, quotes)
        if guard_result.state_changed:
            snapshot = self._trading.account.snapshot(quotes)

        # 止损清仓
        for code in guard_result.stop_loss_codes:
            self._trading.enqueue_liquidation(code, "STOP_LOSS")

        # Step 4: LiquidationWorker
        self._trading.process_liquidation(quotes, tick_id)

        # Step 5-8: 判断是否跳过 LLM
        if guard_result.new_state == RiskState.LIQUIDATE:
            self._trading.persist()
            self._event_log.emit(SystemEvent.TICK_FINISHED, tick_id=tick_id, date=date_str)
            return tick_id

        if system_mode == "PAUSE":
            self._trading.persist()
            self._event_log.emit(SystemEvent.TICK_FINISHED, tick_id=tick_id, date=date_str)
            return tick_id

        # Step 5: 组装 Context + Step 6: LLM Decision
        conflict_codes = set()
        exec_log = []
        if self._decision is not None:
            decision = self._decision.decide(snapshot, quotes, guard_result.new_state, tick_id)

            if decision:
                self._event_log.emit(SystemEvent.DECISION_FINISHED, tick_id=tick_id, date=date_str)

                # 同票买卖互斥过滤：同一标的同分钟出现 BUY+SELL 视为矛盾指令，全部丢弃
                drop_actions = conflict_drop_actions(
                    decision.decisions, snapshot.positions)
                conflict_codes = set(drop_actions)
                if drop_actions:
                    kept = []
                    for code, dropped in drop_actions.items():
                        keep = "SELL" if dropped.value == "BUY" else "BUY"
                        kept.append(f"{code} keep {keep} drop {dropped.value}")
                    self._decision.record_feedback(
                        "same-minute BUY+SELL arbitrated by account: "
                        + "; ".join(kept)
                    )
                    logger.warning("decision_conflict_arbitrated",
                                   detail=kept, tick_id=tick_id)

                # Step 7+8: Risk validate + Execution
                for item in decision.decisions:
                    if item.action == ActionType.HOLD:
                        continue
                    if drop_actions.get(item.code) == item.action:
                        continue
                    pos = snapshot.positions.get(item.code)
                    t_status = "open"
                    if hasattr(self._decision, "t_status"):
                        t_status = self._decision.t_status(item.code)

                    if is_impossible_sell(item, pos):
                        if self._once.first_time(date_str, item.code, "NO_SELLABLE"):
                            logger.warning(
                                "decision_sell_blocked_no_sellable",
                                code=item.code, shares=item.shares, tick_id=tick_id)
                            self._decision.record_feedback(
                                f"SELL {item.code} dropped: sellable=0 (T+1 or empty), "
                                f"further SELL today is ignored")
                        exec_log.append({
                            "stage": "prefilter", "code": item.code,
                            "action": item.action.value, "shares": item.shares,
                            "success": False, "reject": "REASON_INSUFFICIENT_SELLABLE",
                        })
                        continue

                    if t_status == "hold_only" and item.action in (
                            ActionType.BUY, ActionType.SELL):
                        if self._once.first_time(date_str, item.code, "T_BUDGET"):
                            logger.warning(
                                "decision_blocked_t_budget",
                                code=item.code, action=item.action.value,
                                tick_id=tick_id)
                            self._decision.record_feedback(
                                f"{item.action.value} {item.code} dropped: "
                                f"T budget exhausted, HOLD only")
                        exec_log.append({
                            "stage": "prefilter", "code": item.code,
                            "action": item.action.value, "shares": item.shares,
                            "success": False, "reject": "REASON_T_BUDGET_EXCEEDED",
                        })
                        continue

                    if item.code not in quotes:
                        # 幻觉代码（不在股票池/无行情）：丢弃+日志+反馈给模型
                        logger.warning("decision_code_not_in_pool", code=item.code,
                                       action=item.action.value, tick_id=tick_id)
                        self._decision.record_feedback(
                            f"{item.action.value} {item.code} 被丢弃: 该代码不在股票池中，"
                            f"只能对池内标的交易（当前池: {','.join(quotes.keys())}）"
                        )
                        continue

                    verdict = self._risk.validate_decision(
                        item, snapshot, quotes[item.code],
                        self._trading.account.watchlist, date_str,
                        t_status=t_status,
                    )

                    if verdict.passed:
                        intent = OrderIntent(
                            intent_id=f"dec_{tick_id}_{item.code}",
                            action=item.action,
                            code=item.code,
                            shares=item.shares,
                            source=OrderSource.DECISION,
                            confidence=item.confidence,
                        )
                        result = self._trading.execute_order(intent, quotes[item.code], tick_id)
                        exec_log.append({
                            "stage": "execution", "code": item.code,
                            "action": item.action.value, "shares": item.shares,
                            "success": result.success,
                            "reject": result.reject.reason.value if result.reject else None,
                        })
                        # 撮合层拒绝也反馈（如可卖不足）
                        if not result.success and result.reject:
                            logger.warning("order_rejected_by_matcher", code=item.code,
                                           action=item.action.value, shares=item.shares,
                                           reason=result.reject.reason.value, tick_id=tick_id)
                            self._decision.record_feedback(
                                f"{item.action.value} {item.code} {item.shares}股 执行被拒: "
                                f"{result.reject.reason.value}"
                            )
                    else:
                        # 风控拒绝：打日志（可观测）+ 反馈注入决策引擎（闭环，避免重复提交）
                        reason = verdict.reason_code.value if verdict.reason_code else "unknown"
                        exec_log.append({
                            "stage": "risk_validate", "code": item.code,
                            "action": item.action.value, "shares": item.shares,
                            "success": False, "reject": reason,
                        })
                        logger.warning("decision_risk_rejected", code=item.code,
                                       action=item.action.value, shares=item.shares,
                                       reason=reason, tick_id=tick_id)
                        self._decision.record_feedback(
                            f"{item.action.value} {item.code} {item.shares}股 被风控拒绝: {reason}"
                        )

        # Replay 全量快照落盘：Prompt + LLM原始输出 + 解析决策 + 执行/拒绝
        # （根因调查必需：模型看到了什么、回了什么、哪些被执行/被拒）
        if self._replay_store is not None and self._decision is not None:
            try:
                dec = None
                if decision is not None:
                    dec = {
                        "thought": decision.thought_process,
                        "decisions": [
                            {"action": d.action.value, "code": d.code, "shares": d.shares,
                             "confidence": d.confidence, "reason": d.reason}
                            for d in decision.decisions
                        ],
                    }
                self._replay_store.save_decision_tick(self._replay_date, {
                    "tick_id": tick_id,
                    "timestamp": now.isoformat(),
                    "prompt": getattr(self._decision, "_last_prompt", ""),
                    "raw_response": getattr(self._decision, "_last_raw", None),
                    "decision": dec,
                    "conflict_filtered": sorted(conflict_codes),
                    "execution": exec_log,
                })
            except Exception as e:
                logger.error("replay_tick_save_failed", error=str(e), tick_id=tick_id)

        # Step 9: Save + Event
        self._trading.persist()
        self._event_log.emit(SystemEvent.TICK_FINISHED, tick_id=tick_id, date=date_str)
        return tick_id

    def _is_stale(self, quotes: Dict[str, Quote], now: datetime, threshold_sec: int = 5) -> bool:
        """检查行情是否陈旧"""
        for quote in quotes.values():
            if quote.timestamp:
                diff = abs((now - quote.timestamp).total_seconds())
                if diff > threshold_sec:
                    return True
        return False
