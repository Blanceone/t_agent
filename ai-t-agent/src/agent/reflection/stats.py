"""
Reflection 日终复盘

流程：Statistics → LLM Analysis → Memory → Report
统计全部由代码完成，LLM 负责解释。
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional

from agent.common.models import Fill, ActionType, Quote, SystemEvent, MarketRegime
from agent.common.event_log import EventLog
from agent.common.logger import get_logger
from agent.reflection.report import ReportGenerator, DailyReport

logger = get_logger("reflection")


@dataclass
class ReflectionStats:
    """代码统计（客观层）"""
    date: str = ""
    day_pnl: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")
    fee_ratio: float = 0.0
    t_trading_pnl: Decimal = Decimal("0")
    holdings_mark_pnl: Decimal = Decimal("0")
    trade_count: int = 0
    buy_count: int = 0
    sell_count: int = 0
    stop_loss_count: int = 0
    halt_count: int = 0
    low_confidence_filter_count: int = 0
    nav_start: Decimal = Decimal("0")
    nav_end: Decimal = Decimal("0")
    market_regime: str = "RANGE"
    benchmark_nav: Decimal = Decimal("0")
    excess_vs_benchmark: Decimal = Decimal("0")


class ReflectionEngine:
    """日终复盘引擎"""

    def __init__(self, event_log: Optional[EventLog] = None, memory_writer=None,
                 llm_client=None, report_dir: str = "data/reports"):
        self._event_log = event_log
        self._memory_writer = memory_writer
        self._llm = llm_client
        self._report_gen = ReportGenerator(report_dir)

    def run(self, trading_engine, quotes: Dict[str, Quote], date: str,
            market_regime: Optional[MarketRegime] = None) -> ReflectionStats:
        """执行日终复盘"""
        # Step 1: 代码统计
        stats = self.compute_stats(trading_engine, quotes, date, market_regime)

        if self._event_log:
            self._event_log.emit(SystemEvent.REFLECTION_STATS_READY, date=date)

        # Step 2: LLM 解释（可选）
        llm_analysis = ""
        if self._llm and stats.trade_count > 0:
            llm_analysis = self._llm_analyze(stats)

        # Step 3: Memory 写入
        if self._memory_writer and stats.trade_count > 0:
            summary = (
                f"日期{date}: Regime={stats.market_regime}, "
                f"交易{stats.trade_count}笔(买{stats.buy_count}/卖{stats.sell_count}), "
                f"做T盈亏{stats.t_trading_pnl}, 持仓浮动{stats.holdings_mark_pnl}, "
                f"费用{stats.total_fees}(占比{stats.fee_ratio:.4f}), "
                f"日盈亏{stats.day_pnl}"
            )
            if llm_analysis:
                summary += f" | LLM归因: {llm_analysis[:100]}"
            codes = list(trading_engine.account.positions.keys())
            self._memory_writer.write_reflection(summary, codes, ["daily_summary"], 0.7)

        # Step 4: 日报生成与保存
        report = self._report_gen.generate(stats)
        self._report_gen.save(report)

        if self._event_log:
            self._event_log.emit(SystemEvent.REFLECTION_FINISHED, date=date)

        logger.info("reflection_done", date=date, trades=stats.trade_count,
                    t_pnl=str(stats.t_trading_pnl), fees=str(stats.total_fees),
                    regime=stats.market_regime)
        return stats

    def compute_stats(self, trading_engine, quotes: Dict[str, Quote],
                      date: str = "", market_regime: Optional[MarketRegime] = None) -> ReflectionStats:
        """代码统计层（不依赖 LLM）"""
        fills: List[Fill] = trading_engine.today_fills
        account = trading_engine.account

        total_fees = sum(f.fee for f in fills) if fills else Decimal("0")
        t_pnl = sum(
            f.realized_pnl for f in fills
            if f.action == ActionType.SELL and f.realized_pnl
        ) if fills else Decimal("0")
        buy_count = len([f for f in fills if f.action == ActionType.BUY])
        sell_count = len([f for f in fills if f.action == ActionType.SELL])

        nav_end = account.nav_mark(quotes)
        # 开盘 NAV 优先取日切时记录的 nav_open（last_nav 在日终会被覆盖为收盘值）
        nav_start = getattr(account, "nav_open", None) or account.last_nav
        day_pnl = nav_end - nav_start
        # 持仓浮动 = 日盈亏 - 做T盈亏 - 费用（近似归因）
        holdings_mark_pnl = day_pnl - t_pnl

        fee_ratio = float(total_fees / nav_end) if nav_end > 0 else 0.0

        # 基准
        benchmark_nav = account.benchmark.equal_weight.nav if account.benchmark else Decimal("0")
        excess = nav_end - benchmark_nav if benchmark_nav > 0 else Decimal("0")

        return ReflectionStats(
            date=date,
            day_pnl=day_pnl,
            total_fees=total_fees,
            fee_ratio=fee_ratio,
            t_trading_pnl=t_pnl,
            holdings_mark_pnl=holdings_mark_pnl,
            trade_count=len(fills),
            buy_count=buy_count,
            sell_count=sell_count,
            nav_start=nav_start,
            nav_end=nav_end,
            market_regime=market_regime.value if market_regime else "RANGE",
            benchmark_nav=benchmark_nav,
            excess_vs_benchmark=excess,
        )

    def _llm_analyze(self, stats: ReflectionStats) -> str:
        """LLM 归因分析（简化版）"""
        prompt = f"""你是量化交易复盘分析师。根据今日统计数据给出简要归因分析（50字以内）。

今日数据：
- 日盈亏: {stats.day_pnl}
- 做T盈亏: {stats.t_trading_pnl}
- 持仓浮动: {stats.holdings_mark_pnl}
- 费用: {stats.total_fees}
- 交易笔数: {stats.trade_count}
- Regime: {stats.market_regime}

请输出一句话归因："""

        try:
            result = self._llm.call(prompt, timeout_ms=10000)
            return result.strip() if result else ""
        except Exception:
            return ""
