"""
基准组合（等权 + 沪深300）

等权组合（Buy & Hold 上限参考）：
- 构成：100% 股票市值，无现金拖累
- 再平衡：watchlist 变更时清空重建（非增量）
- 估值：日终及决策前用 mark_price 重估

沪深300基准：
- 数据源：沪深300全收益指数（含股息再投）
- 更新：基准净值_n = 基准净值_{n-1} * (指数收盘价_n / 指数收盘价_{n-1})
"""

from decimal import Decimal
from typing import Dict, List

from agent.common.models import (
    BenchmarkPortfolio,
    CSI300Benchmark,
    EqualWeightBenchmark,
    Quote,
)
from agent.common.logger import get_logger

logger = get_logger("trading.benchmark")


class BenchmarkManager:
    """基准组合管理"""

    def rebuild_equal_weight(
        self,
        benchmark: BenchmarkPortfolio,
        watchlist: List[str],
        quotes: Dict[str, Quote],
        nav: Decimal,
        date: str,
    ) -> None:
        """
        watchlist 变更时：清空重建（非增量）。

        按当前 watchlist 成分 pre_close 全仓等权分配。
        """
        if not watchlist:
            benchmark.equal_weight = EqualWeightBenchmark(
                nav=nav, constituents={}, last_rebuild_date=date
            )
            return

        # 等权分配：每只票分配 nav / n 的市值
        per_stock_value = nav / len(watchlist)
        constituents: Dict[str, Decimal] = {}

        for code in watchlist:
            if code in quotes:
                price = quotes[code].pre_close
                if price > 0:
                    shares = per_stock_value / price
                    constituents[code] = shares

        benchmark.equal_weight = EqualWeightBenchmark(
            nav=nav,
            constituents=constituents,
            last_rebuild_date=date,
        )
        logger.info("benchmark_rebuild", stocks=len(constituents), nav=str(nav), date=date)

    def update_equal_weight(self, benchmark: BenchmarkPortfolio, quotes: Dict[str, Quote]) -> None:
        """日终重估等权组合"""
        ew = benchmark.equal_weight
        if not ew.constituents:
            return

        new_nav = Decimal("0")
        for code, shares in ew.constituents.items():
            if code in quotes:
                new_nav += quotes[code].mark_price * shares

        ew.nav = new_nav

    def update_csi300(
        self,
        benchmark: BenchmarkPortfolio,
        index_close: Decimal,
    ) -> None:
        """
        更新沪深300基准。

        基准净值_n = 基准净值_{n-1} * (指数收盘价_n / 指数收盘价_{n-1})
        """
        csi = benchmark.csi300
        if csi.last_index_close > 0:
            ratio = index_close / csi.last_index_close
            csi.nav = csi.nav * ratio

        csi.index_value = index_close
        csi.last_index_close = index_close
