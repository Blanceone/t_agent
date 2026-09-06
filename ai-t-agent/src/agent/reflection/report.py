"""
日报生成

日报需包含：净值曲线、基准对比、拒单率、费用率、做T贡献、
低置信度过滤次数、SET_CASH 高亮标记。
"""

import json
from dataclasses import dataclass, asdict
from decimal import Decimal
from pathlib import Path
from typing import Optional

from agent.common.logger import get_logger

logger = get_logger("reflection.report")


@dataclass
class DailyReport:
    """日报结构"""
    date: str
    nav_start: str
    nav_end: str
    day_pnl: str
    t_trading_pnl: str
    holdings_mark_pnl: str
    total_fees: str
    fee_ratio: float
    trade_count: int
    buy_count: int
    sell_count: int
    stop_loss_count: int
    halt_count: int
    low_confidence_filter_count: int
    market_regime: str
    benchmark_equal_weight_nav: str
    excess_vs_equal_weight: str
    set_cash_event: bool = False
    schema_version: str = "reflection.v1"


class ReportGenerator:
    """日报生成器"""

    def __init__(self, report_dir: str = "data/reports"):
        self._report_dir = Path(report_dir)
        self._report_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, stats, set_cash_event: bool = False) -> DailyReport:
        """从 ReflectionStats 生成日报"""
        report = DailyReport(
            date=getattr(stats, 'date', ''),
            nav_start=str(stats.nav_start),
            nav_end=str(stats.nav_end),
            day_pnl=str(stats.day_pnl),
            t_trading_pnl=str(stats.t_trading_pnl),
            holdings_mark_pnl=str(getattr(stats, 'holdings_mark_pnl', Decimal("0"))),
            total_fees=str(stats.total_fees),
            fee_ratio=stats.fee_ratio,
            trade_count=stats.trade_count,
            buy_count=stats.buy_count,
            sell_count=stats.sell_count,
            stop_loss_count=getattr(stats, 'stop_loss_count', 0),
            halt_count=getattr(stats, 'halt_count', 0),
            low_confidence_filter_count=getattr(stats, 'low_confidence_filter_count', 0),
            market_regime=getattr(stats, 'market_regime', 'RANGE'),
            benchmark_equal_weight_nav=str(getattr(stats, 'benchmark_nav', Decimal("0"))),
            excess_vs_equal_weight=str(getattr(stats, 'excess_vs_benchmark', Decimal("0"))),
            set_cash_event=set_cash_event,
        )

        return report

    def save(self, report: DailyReport) -> str:
        """保存日报到 JSON 文件"""
        filename = f"{report.date}_daily.json"
        filepath = self._report_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(asdict(report), f, ensure_ascii=False, indent=2)

        logger.info("report_saved", path=str(filepath), date=report.date)
        return str(filepath)
