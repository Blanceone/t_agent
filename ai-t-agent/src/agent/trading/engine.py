"""
TradingEngine 主类

协调撮合、记账、状态管理。
所有交易必须经过 Risk Engine 校验后才能进入本模块执行。
"""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
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
    RiskState,
)
from agent.common.event_log import EventLog
from agent.common.logger import get_logger
from agent.common.utils import gen_task_id, today_str
from agent.config.schema import AppConfig
from agent.trading.account import Account
from agent.trading.benchmark import BenchmarkManager
from agent.trading.fee import FeeCalculator
from agent.trading.liquidation import LiquidationWorker
from agent.trading.matcher import SimMatcher
from agent.trading.position import PositionManager
from agent.trading.settlement import SettlementManager

logger = get_logger("trading.engine")


@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool
    fill: Optional[Fill] = None
    reject: Optional[RejectResult] = None


class TradingEngine:
    """交易引擎主类"""

    def __init__(self, config: AppConfig, event_log: Optional[EventLog] = None):
        self._config = config
        self._event_log = event_log

        # 子模块
        self.fee_calc = FeeCalculator(config.fee)
        self.matcher = SimMatcher(self.fee_calc)
        self.position_mgr = PositionManager(config.risk.stop_loss_ratio)
        self.liquidation_worker = LiquidationWorker(
            matcher=self.matcher,
            max_attempts=config.trading.max_liquidation_attempts,
            max_shares_per_tick=config.trading.max_liquidation_shares_per_tick,
        )
        self.benchmark_mgr = BenchmarkManager()
        self.settlement_mgr = SettlementManager()

        # 账户
        self.account = Account(
            account_id="sim_001",
            initial_cash=config.trading.initial_cash,
            reserved_min_ratio=config.risk.reserved_min_cash_ratio,
        )

        # 当日成交记录
        self.today_fills: List[Fill] = []

    def execute_order(self, intent: OrderIntent, quote: Quote, tick_id: str = "") -> ExecutionResult:
        """
        执行一笔订单（Risk 已放行）。

        Args:
            intent: 订单意图
            quote: 实时行情
            tick_id: Tick ID

        Returns:
            ExecutionResult
        """
        position = self.account.positions.get(intent.code)
        is_liquidation = intent.source in (OrderSource.LIQUIDATE, OrderSource.STOP_LOSS, OrderSource.USER_REMOVE)

        # 撮合
        result = self.matcher.match(
            intent=intent,
            quote=quote,
            position=position,
            is_liquidation=is_liquidation,
            tick_id=tick_id,
        )

        if not result.success:
            logger.warning("order_rejected", code=intent.code, reason=result.reject.reason.value if result.reject else "unknown")
            return ExecutionResult(success=False, reject=result.reject)

        fill = result.fill
        assert fill is not None

        # 记账
        self._apply_fill(fill, intent)
        self.today_fills.append(fill)

        logger.info(
            "order_filled",
            code=fill.code,
            action=fill.action.value,
            shares=fill.shares,
            price=str(fill.price),
            fee=str(fill.fee),
            tick_id=tick_id,
        )

        return ExecutionResult(success=True, fill=fill)

    def _apply_fill(self, fill: Fill, intent: OrderIntent) -> None:
        """将成交应用到账户"""
        code = fill.code

        if fill.action == ActionType.BUY:
            self._apply_buy(code, fill)
        else:
            self._apply_sell(code, fill, intent)

    def _apply_buy(self, code: str, fill: Fill) -> None:
        """买入记账"""
        if code in self.account.positions:
            # 加仓
            pos = self.account.positions[code]
            self.position_mgr.apply_buy(pos, fill.shares, fill.price, fill.fee)
        else:
            # 建仓
            pos = self.position_mgr.create_position(code, fill.shares, fill.price, fill.fee)
            self.account.positions[code] = pos

        # 扣减现金（金额 + 费用）
        self.account.cash.available -= (fill.amount + fill.fee)

    def _apply_sell(self, code: str, fill: Fill, intent: OrderIntent) -> None:
        """卖出记账"""
        pos = self.account.positions.get(code)
        if pos is None:
            return

        # 更新持仓
        self.position_mgr.apply_sell(pos, fill.shares, fill.price, fill.fee)

        # 增加现金（金额 - 费用）
        self.account.cash.available += (fill.amount - fill.fee)

        # 累计已实现盈亏
        if fill.realized_pnl is not None:
            self.account.realized_pnl_today += fill.realized_pnl

        # 清仓完成检查
        if self.position_mgr.is_cleared(pos):
            self._on_position_cleared(code, pos, intent)

    def _on_position_cleared(self, code: str, pos: Position, intent: OrderIntent) -> None:
        """持仓清零后处理（统一移除0股残留记录，避免污染决策上下文）"""
        if intent.source == OrderSource.USER_REMOVE:
            # 用户移除：清零后移出池（不冷却）
            self.account.remove_from_watchlist(code)
            del self.account.positions[code]
            logger.info("position_removed", code=code, reason="USER_REMOVE")
        elif intent.source == OrderSource.STOP_LOSS:
            # 止损：清零后留池，冷却（冷却记录在 watchlist entry 上）
            pos.exit_reason = "STOP_LOSS"
            entry = self.account.watchlist.get(code)
            if entry:
                entry.cooldown_until_date = today_str()
            del self.account.positions[code]
            logger.info("position_stop_loss_cleared", code=code, cooldown=today_str())
        elif intent.source == OrderSource.LIQUIDATE:
            # 强平：清零后移除记录，留池
            pos.exit_reason = "LIQUIDATE"
            del self.account.positions[code]
            logger.info("position_liquidate_cleared", code=code)
        else:
            # 决策正常清仓：移除记录，留池（无冷却，允许后续再次建仓）
            pos.exit_reason = "DECISION_SELL"
            del self.account.positions[code]
            logger.info("position_closed", code=code, reason="DECISION_SELL")

    def enqueue_liquidation(self, code: str, exit_reason: str) -> None:
        """加入清仓队列"""
        pos = self.account.positions.get(code)
        if pos is None or pos.total_shares == 0:
            return

        pos.position_state = PositionState.CLEARING
        pos.exit_reason = exit_reason

        task = LiquidationTask(
            task_id=gen_task_id(),
            code=code,
            remaining_shares=pos.total_shares,  # 用 total_shares，T+1 解冻后自然可卖
            exit_reason=exit_reason,
            attempts=0,
            created_at=today_str(),
        )
        self.account.liquidation_queue.append(task)
        logger.info("liquidation_enqueued", code=code, shares=task.remaining_shares, reason=exit_reason)

    def process_liquidation(self, quotes: Dict[str, Quote], tick_id: str = "") -> List[Fill]:
        """处理清仓队列"""
        fills, rejects, exhausted = self.liquidation_worker.process_tick(
            queue=self.account.liquidation_queue,
            positions=self.account.positions,
            quotes=quotes,
            tick_id=tick_id,
        )

        # 应用成交
        for fill in fills:
            intent = OrderIntent(
                intent_id=fill.order_id,
                action=ActionType.SELL,
                code=fill.code,
                shares=fill.shares,
                source=OrderSource.LIQUIDATE,
            )
            self._apply_sell(fill.code, fill, intent)
            self.today_fills.append(fill)
            logger.info(
                "order_filled",
                code=fill.code,
                action=fill.action.value,
                shares=fill.shares,
                price=str(fill.price),
                fee=str(fill.fee),
                tick_id=tick_id,
            )

        # 处理耗尽的任务
        for task_id in exhausted:
            for task in self.account.liquidation_queue:
                if task.task_id == task_id:
                    pos = self.account.positions.get(task.code)
                    if pos:
                        self.position_mgr.transition_to_liq_fail(pos)

        # 清理已完成任务
        self.account.liquidation_queue = self.liquidation_worker.remove_completed(
            self.account.liquidation_queue
        )

        return fills

    def on_day_start(self, current_date: str, quotes: Dict[str, Quote], watchlist_changed: bool = False) -> None:
        """
        日切处理。
        """
        # 日切结算（T+1解冻、冷却清理）
        self.settlement_mgr.on_day_start(
            self.account.positions, self.account.watchlist, current_date
        )

        # 防御性清理：移除历史残留的0股持仓记录
        for code in [c for c, p in self.account.positions.items() if p.total_shares <= 0]:
            del self.account.positions[code]
            logger.info("position_residual_cleaned", code=code)

        # 重置当日累计
        self.account.reset_daily()
        self.today_fills = []

        # 记录当日开盘 NAV（日报 day_pnl 基准，日内重启不覆盖）
        if self.account.nav_open_date != current_date:
            self.account.nav_open = (
                self.account.nav_mark(quotes) if quotes else self.account.last_nav
            )
            self.account.nav_open_date = current_date

        # 基准重建
        if watchlist_changed:
            nav = self.account.nav_mark(quotes)
            self.benchmark_mgr.rebuild_equal_weight(
                self.account.benchmark,
                list(self.account.watchlist.keys()),
                quotes,
                nav,
                current_date,
            )

        logger.info("trading_day_start", date=current_date, watchlist_changed=watchlist_changed)

    def on_day_end(self, quotes: Dict[str, Quote], current_date: str) -> None:
        """日终处理"""
        self.account.update_nav(quotes, current_date)
        self.benchmark_mgr.update_equal_weight(self.account.benchmark, quotes)
        self.account.save()
        logger.info("trading_day_end", date=current_date, nav=str(self.account.last_nav))

    def persist(self) -> None:
        """持久化账户状态"""
        self.account.save()

    def cli_flag_path(self) -> Path:
        """CLI 变更信号文件路径"""
        return Path(self._config.data_dir) / "account" / "cli_changed.flag"

    def reload_if_cli_changed(self) -> bool:
        """检测外部 CLI 对账户的修改（信号文件机制），有则重新加载。

        CLI 与本常驻服务是独立进程：CLI 修改 state.json 后写信号文件通知，
        否则本服务的 persist() 会用旧内存副本覆盖 CLI 的修改（如 REMOVE 失效）。
        """
        flag = self.cli_flag_path()
        if not flag.exists():
            return False
        state_path = str(Path(self._config.data_dir) / "account" / "state.json")
        ok = self.account.load(state_path)
        try:
            flag.unlink()
        except OSError:
            pass
        logger.info("account_reloaded_by_cli", loaded=ok,
                    watchlist=list(self.account.watchlist.keys()))
        return ok
