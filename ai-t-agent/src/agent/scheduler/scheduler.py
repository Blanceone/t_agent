"""
Scheduler 主循环

全系统唯一调度中心，驱动日级生命周期与分钟级 Tick 循环。
"""

import time
from datetime import datetime, date, timedelta
from typing import Optional

from agent.common.models import SystemEvent
from agent.common.event_log import EventLog
from agent.common.logger import get_logger
from agent.common.utils import now_cst, today_str
from agent.config.schema import AppConfig
from agent.scheduler.calendar import TradingCalendar
from agent.scheduler.tick import TickExecutor
from agent.market.understanding import MarketUnderstandingEngine, MarketUnderstandingOutput
from agent.decision.planner import Planner, TodayPlan

logger = get_logger("scheduler")


class Scheduler:
    """唯一调度中心"""

    def __init__(self, config: AppConfig, trading_engine, risk_engine,
                 decision_engine, market_service, reflection_engine,
                 event_log: EventLog, llm_client=None, memory_retriever=None,
                 replay_store=None):
        self._config = config
        self._trading = trading_engine
        self._risk = risk_engine
        self._decision = decision_engine
        self._market = market_service
        self._reflection = reflection_engine
        self._event_log = event_log
        self._memory_retriever = memory_retriever
        self._replay_store = replay_store

        self._calendar = TradingCalendar()
        self._tick_executor = TickExecutor(
            trading_engine, risk_engine, decision_engine,
            market_service, None, event_log
        )

        # 第二阶段：Market Understanding + Planner
        self._mu_engine = MarketUnderstandingEngine(llm_client)
        self._planner = Planner(llm_client)
        self._today_mu: Optional[MarketUnderstandingOutput] = None
        self._today_plan: Optional[TodayPlan] = None

        self._running = False
        self._system_mode = "NORMAL"  # NORMAL / PAUSE
        self._last_tick_minute: Optional[int] = None
        self._day_started = False
        self._suspend_logged = False
        # 用启动时账户清单初始化，避免重启后首日切误判 watchlist_changed=True
        # （误判会触发基准组合不必要的重建，导致基准净值跳变、超额序列失真）
        self._last_watchlist: set = set(self._trading.account.watchlist.keys())

    def run(self):
        """主循环"""
        self._running = True
        self._last_date = None
        logger.info("scheduler_started")

        while self._running:
            try:
                now = now_cst()
                today = now.date()

                # 跨日重置：防止异常后 _day_started 卡死
                if self._last_date and today != self._last_date:
                    self._day_started = False
                self._last_date = today

                if not self._calendar.is_trading_day(today):
                    time.sleep(60)
                    continue

                self._dispatch(now)
            except Exception as e:
                logger.error("scheduler_dispatch_error", error=str(e))
            time.sleep(1)

    def stop(self):
        """停止"""
        self._running = False
        logger.info("scheduler_stopped")

    def _dispatch(self, now: datetime):
        """根据时间分发"""
        t = now.hour * 100 + now.minute
        today = now.date()

        # 09:20 日切（正常触发）
        if t == 920 and not self._day_started:
            self._on_day_start(today)
            return

        # 补偿：交易时段内若未完成日切（进程重启/延迟启动），立即补执行
        if self._in_trading_session(t) and not self._day_started:
            logger.warning("day_start_compensation", time=today.strftime("%H:%M"))
            self._on_day_start(today)
            # 不 return，继续执行本分钟 Tick

        # 交易时段
        if self._in_trading_session(t):
            current_minute = now.hour * 60 + now.minute
            if current_minute != self._last_tick_minute:
                self._last_tick_minute = current_minute
                # 每 Tick 前刷新行情（未接入时 quotes 为空会全量 SKIP_STALE）
                self._market.set_watchlist(list(self._trading.account.watchlist.keys()))
                self._market.refresh()
                self._tick_executor.execute(now, self._system_mode)
            return

        # 14:57 挂起
        if t == 1457:
            self._on_session_suspend()
            return

        # 15:05 日终
        if t == 1505 and self._day_started:
            self._on_day_close(today)
            return

    def _in_trading_session(self, t: int) -> bool:
        """09:30-11:30 / 13:00-14:56"""
        am = 930 <= t <= 1130
        pm = 1300 <= t <= 1456
        return am or pm

    def _on_day_start(self, today: date):
        """09:20 日切 + Market Understanding + Planner"""
        date_str = today.strftime("%Y-%m-%d")
        self._event_log.emit(SystemEvent.SCHEDULER_DAY_START, date=date_str)

        # 先检查 CLI 是否修改过账户（如 REMOVE），有则重载，保证后续用新清单
        self._trading.reload_if_cli_changed()

        # 先刷新行情，保证 MU/Planner 拿到真实数据；09:20 竞价点不计入日内轨迹
        self._market.set_watchlist(list(self._trading.account.watchlist.keys()))
        quotes = self._market.refresh()
        self._market.reset_intraday()
        # 日K技术位（MA5/MA20/支撑压力/量比，失败不阻塞）
        try:
            self._market.refresh_klines()
        except Exception as e:
            logger.warning("kline_refresh_failed", error=str(e))

        # 检测 watchlist 是否变更（对比上次记录的快照）
        current_watchlist = set(self._trading.account.watchlist.keys())
        watchlist_changed = current_watchlist != self._last_watchlist
        self._last_watchlist = current_watchlist

        self._trading.on_day_start(date_str, quotes, watchlist_changed=watchlist_changed)
        self._risk.on_day_start()

        # 昨日复盘摘要（差异化注入：MU/Planner 用详版含归因拆分，决策层用简版避免注意力稀释）
        yesterday_summary_detail = self._load_yesterday_summary(date_str, brief=False)
        yesterday_summary_brief = self._load_yesterday_summary(date_str, brief=True)

        # Market Understanding（四态 Regime，真实大盘指数 + 量比）
        watchlist_codes = list(self._trading.account.watchlist.keys())
        self._today_mu = self._mu_engine.run(
            date=date_str,
            quotes=quotes,
            watchlist=watchlist_codes,
            yesterday_summary=yesterday_summary_detail,
            market_service=self._market,
        )
        self._event_log.emit(SystemEvent.MARKET_UNDERSTANDING_FINISHED, date=date_str)

        # Planner（Today Plan）
        snapshot = self._trading.account.snapshot(quotes)
        memory_items = None
        if self._memory_retriever:
            memory_items = self._memory_retriever.retrieve_for_decision(watchlist_codes)

        self._today_plan = self._planner.generate(
            date=date_str,
            mu_output=self._today_mu,
            snapshot=snapshot,
            quotes=quotes,
            watchlist=watchlist_codes,
            memory_items=memory_items,
            market_service=self._market,
            yesterday_summary=yesterday_summary_detail,
        )
        # 可观测性：Planner 完整输出落日志（根因调查必需，此前完全不可追溯）
        if self._today_plan is not None:
            logger.info("planner_output", date=date_str,
                        regime=self._today_plan.market_regime.value,
                        global_bias=self._today_plan.global_bias,
                        degraded=self._today_plan.degraded,
                        generated_at=self._today_plan.generated_at,
                        last_at_plan={k: str(v) for k, v in (
                            self._today_plan.last_at_plan or {}).items()},
                        plans=[{
                            "code": p.code, "t_strategy": p.t_strategy,
                            "max_trades_hint": p.max_trades_hint,
                            "target_position_ratio": p.target_position_ratio,
                            "risk_level": p.risk_level,
                            "trade_plan": p.trade_plan, "notes": p.notes,
                        } for p in self._today_plan.plans])
        self._event_log.emit(SystemEvent.PLANNER_FINISHED, date=date_str)

        # 注入日级上下文到决策引擎
        if self._decision is not None:
            self._decision.set_daily_context(
                watchlist_codes, self._today_plan, self._market,
                trading_engine=self._trading,
                memory_retriever=self._memory_retriever,
                regime=self._today_mu.market_regime.value,
                market_summary=self._today_mu.today_market_summary,
                yesterday_summary=yesterday_summary_brief,
            )

        # 注入当日 Replay 存储到 Tick 执行器（Prompt/决策全量快照落盘）
        self._tick_executor.set_replay(date_str, self._replay_store)

        self._day_started = True
        self._suspend_logged = False
        self._last_tick_minute = None
        logger.info(
            "day_start",
            date=date_str,
            watchlist_changed=watchlist_changed,
            regime=self._today_mu.market_regime.value,
            plan_degraded=self._today_plan.degraded,
        )

    def _load_yesterday_summary(self, today_date: str, brief: bool = False) -> str:
        """
        加载最近一个交易日的日报摘要。

        brief=True（决策层，每分钟注入）: 仅核心4字段，控制上下文长度
        brief=False（MU/Planner，每日1次）: 追加盈亏归因拆分与买卖结构
        """
        try:
            import json as _json
            from pathlib import Path as _Path

            report_dir = _Path(self._config.data_dir) / "reports"
            files = sorted(report_dir.glob("*_daily.json"))
            for fp in reversed(files):
                rep_date = fp.stem.split("_")[0]
                if rep_date >= today_date:
                    continue
                data = _json.load(open(fp, encoding="utf-8"))
                summary = (
                    f"{rep_date}: 日盈亏{data.get('day_pnl')}, "
                    f"交易{data.get('trade_count')}笔, Regime={data.get('market_regime')}, "
                    f"超额{str(data.get('excess_vs_equal_weight', ''))[:6]}"
                )
                if not brief:
                    summary += (
                        f"（盈亏拆分: 做T{data.get('t_trading_pnl')}, "
                        f"持仓浮动{data.get('holdings_mark_pnl')}; "
                        f"买卖结构: 买{data.get('buy_count')}笔/卖{data.get('sell_count')}笔, "
                        f"费用{data.get('total_fees')}）"
                    )
                return summary
        except Exception:
            pass
        return ""

    def _on_session_suspend(self):
        """14:57 挂起（每分钟仅记录一次，避免日志刷屏）"""
        if self._suspend_logged:
            return
        self._suspend_logged = True
        self._event_log.emit(SystemEvent.SESSION_SUSPEND, date=today_str())
        logger.info("session_suspend")

    def _on_day_close(self, today: date):
        """15:05 日终"""
        date_str = today.strftime("%Y-%m-%d")
        quotes = self._market.refresh()

        self._trading.on_day_end(quotes, date_str)

        if self._reflection:
            regime = self._today_mu.market_regime if self._today_mu else None
            self._reflection.run(self._trading, quotes, date_str, market_regime=regime)

        self._event_log.emit(SystemEvent.DAY_CLOSE_FINISHED, date=date_str)
        self._day_started = False
        self._today_mu = None
        self._today_plan = None
        if self._decision is not None:
            self._decision.set_daily_context([], None)
        logger.info("day_close", date=date_str)

    def pause(self):
        self._system_mode = "PAUSE"

    def resume(self):
        self._system_mode = "NORMAL"
        self._risk.on_resume()
