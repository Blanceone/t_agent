"""
Account / Cash / NAV 管理

NAV 口径：
- 盯市净值 nav_mark = cash.available + Σ(mark_price * total_shares)
- 盯市价格回退：bid1 → last → pre_close

持久化：JSON 文件（data/account/state.json），每次变更落盘。
"""

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

from agent.common.models import (
    AccountSnapshot,
    BenchmarkPortfolio,
    Cash,
    EqualWeightBenchmark,
    CSI300Benchmark,
    LiquidationTask,
    Position,
    PositionState,
    Quote,
    RiskState,
    WatchlistEntry,
)
from agent.common.logger import get_logger
from agent.common.utils import now_cst

logger = get_logger("trading.account")


class Account:
    """账户主类"""

    SCHEMA_VERSION = "account.v1"

    def __init__(
        self,
        account_id: str = "sim_001",
        initial_cash: Decimal = Decimal("30000"),
        reserved_min_ratio: Decimal = Decimal("0.20"),
    ):
        self.account_id = account_id
        self.initial_cash = initial_cash
        self.cash = Cash(available=initial_cash, reserved_min_ratio=reserved_min_ratio)
        self.positions: Dict[str, Position] = {}
        self.watchlist: Dict[str, WatchlistEntry] = {}
        self.risk_state = RiskState.NORMAL
        self.last_nav_date: str = ""
        self.last_nav: Decimal = initial_cash
        self.peak_nav: Decimal = initial_cash
        self.nav_open: Decimal = initial_cash  # 当日开盘 NAV（日报 day_pnl 基准）
        self.nav_open_date: str = ""
        self.realized_pnl_today: Decimal = Decimal("0")
        self.liquidation_queue: List[LiquidationTask] = []
        self.benchmark = BenchmarkPortfolio(
            equal_weight=EqualWeightBenchmark(
                nav=initial_cash, constituents={}, last_rebuild_date=""
            ),
            csi300=CSI300Benchmark(
                nav=initial_cash,
                index_value=Decimal("3500"),
                last_index_close=Decimal("3500"),
            ),
        )

    def nav_mark(self, quotes: Dict[str, Quote]) -> Decimal:
        """
        盯市净值 = cash.available + Σ(mark_price * total_shares)
        """
        market_value = Decimal("0")
        for code, pos in self.positions.items():
            if pos.total_shares > 0 and code in quotes:
                mark = quotes[code].mark_price
                market_value += mark * pos.total_shares
        return self.cash.available + market_value

    def market_value(self, quotes: Dict[str, Quote]) -> Decimal:
        """总市值"""
        mv = Decimal("0")
        for code, pos in self.positions.items():
            if pos.total_shares > 0 and code in quotes:
                mv += quotes[code].mark_price * pos.total_shares
        return mv

    def snapshot(self, quotes: Dict[str, Quote]) -> AccountSnapshot:
        """生成不可变快照用于 Tick 内决策"""
        return AccountSnapshot(
            account_id=self.account_id,
            nav_mark=self.nav_mark(quotes),
            cash_available=self.cash.available,
            peak_nav=self.peak_nav,
            last_nav=self.last_nav,
            risk_state=self.risk_state,
            positions=dict(self.positions),
            realized_pnl_today=self.realized_pnl_today,
            liquidation_queue=list(self.liquidation_queue),
            snapshot_time=now_cst(),
        )

    def add_to_watchlist(self, code: str, date: str) -> bool:
        """加入股票池"""
        if code in self.watchlist:
            return False
        self.watchlist[code] = WatchlistEntry(code=code, added_at=date)
        return True

    def remove_from_watchlist(self, code: str) -> bool:
        """移出股票池"""
        if code not in self.watchlist:
            return False
        del self.watchlist[code]
        return True

    def reset_daily(self) -> None:
        """日切重置（每日累计量）"""
        self.realized_pnl_today = Decimal("0")

    def update_nav(self, quotes: Dict[str, Quote], date: str) -> None:
        """日终更新 NAV"""
        nav = self.nav_mark(quotes)
        self.last_nav = nav
        self.last_nav_date = date
        if nav > self.peak_nav:
            self.peak_nav = nav

    # ==================== 持久化 ====================

    def save(self, path: str = "data/account/state.json") -> None:
        """保存账户状态到 JSON 文件（原子写入，防止崩溃时数据丢失）"""
        import os
        import tempfile

        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        data = self._to_dict()

        # 写入临时文件后原子替换，防止进程崩溃导致文件截断
        fd, tmp_path = tempfile.mkstemp(dir=str(file_path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            os.replace(tmp_path, str(file_path))  # Windows/Linux 均为原子操作
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        logger.debug("account_saved", path=path)

    def load(self, path: str = "data/account/state.json") -> bool:
        """从 JSON 文件加载账户状态"""
        file_path = Path(path)
        if not file_path.exists():
            return False

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._from_dict(data)
        logger.info("account_loaded", path=path, account_id=self.account_id)
        return True

    def _to_dict(self) -> dict:
        """序列化为 dict"""
        positions = {}
        for code, pos in self.positions.items():
            positions[code] = {
                "code": pos.code,
                "total_shares": pos.total_shares,
                "sellable_shares": pos.sellable_shares,
                "today_bought": pos.today_bought,
                "cost_price": str(pos.cost_price),
                "stop_loss_price": str(pos.stop_loss_price),
                "stop_breach_count": pos.stop_breach_count,
                "position_state": pos.position_state.value,
                "exit_reason": pos.exit_reason,
            }

        watchlist = {}
        for code, entry in self.watchlist.items():
            watchlist[code] = {
                "code": entry.code,
                "added_at": entry.added_at,
                "cooldown_until_date": entry.cooldown_until_date,
            }

        liq_queue = []
        for task in self.liquidation_queue:
            liq_queue.append({
                "task_id": task.task_id,
                "code": task.code,
                "remaining_shares": task.remaining_shares,
                "exit_reason": task.exit_reason,
                "attempts": task.attempts,
                "created_at": task.created_at,
            })

        return {
            "schema_version": self.SCHEMA_VERSION,
            "account_id": self.account_id,
            "saved_at": now_cst().isoformat(),
            "initial_cash": str(self.initial_cash),
            "cash": {
                "available": str(self.cash.available),
                "reserved_min_ratio": str(self.cash.reserved_min_ratio),
            },
            "positions": positions,
            "watchlist": watchlist,
            "risk_state": self.risk_state.value,
            "last_nav_date": self.last_nav_date,
            "last_nav": str(self.last_nav),
            "peak_nav": str(self.peak_nav),
            "nav_open": str(self.nav_open),
            "nav_open_date": self.nav_open_date,
            "realized_pnl_today": str(self.realized_pnl_today),
            "liquidation_queue": liq_queue,
            "benchmark": {
                "equal_weight": {
                    "nav": str(self.benchmark.equal_weight.nav),
                    "constituents": {k: str(v) for k, v in self.benchmark.equal_weight.constituents.items()},
                    "last_rebuild_date": self.benchmark.equal_weight.last_rebuild_date,
                },
                "csi300": {
                    "nav": str(self.benchmark.csi300.nav),
                    "index_value": str(self.benchmark.csi300.index_value),
                    "last_index_close": str(self.benchmark.csi300.last_index_close),
                },
            },
        }

    def _from_dict(self, data: dict) -> None:
        """从 dict 反序列化"""
        self.account_id = data["account_id"]
        self.initial_cash = Decimal(data["initial_cash"])
        self.cash = Cash(
            available=Decimal(data["cash"]["available"]),
            reserved_min_ratio=Decimal(data["cash"]["reserved_min_ratio"]),
        )

        self.positions = {}
        for code, pos_data in data.get("positions", {}).items():
            self.positions[code] = Position(
                code=pos_data["code"],
                total_shares=pos_data["total_shares"],
                sellable_shares=pos_data["sellable_shares"],
                today_bought=pos_data["today_bought"],
                cost_price=Decimal(pos_data["cost_price"]),
                stop_loss_price=Decimal(pos_data["stop_loss_price"]),
                stop_breach_count=pos_data["stop_breach_count"],
                position_state=PositionState(pos_data["position_state"]),
                exit_reason=pos_data.get("exit_reason"),
            )

        self.watchlist = {}
        for code, entry_data in data.get("watchlist", {}).items():
            self.watchlist[code] = WatchlistEntry(
                code=entry_data["code"],
                added_at=entry_data["added_at"],
                cooldown_until_date=entry_data.get("cooldown_until_date"),
            )

        self.risk_state = RiskState(data["risk_state"])
        self.last_nav_date = data["last_nav_date"]
        self.last_nav = Decimal(data["last_nav"])
        self.peak_nav = Decimal(data["peak_nav"])
        self.nav_open = Decimal(data.get("nav_open", data["last_nav"]))
        self.nav_open_date = data.get("nav_open_date", "")
        self.realized_pnl_today = Decimal(data["realized_pnl_today"])

        self.liquidation_queue = []
        for task_data in data.get("liquidation_queue", []):
            self.liquidation_queue.append(LiquidationTask(
                task_id=task_data["task_id"],
                code=task_data["code"],
                remaining_shares=task_data["remaining_shares"],
                exit_reason=task_data["exit_reason"],
                attempts=task_data["attempts"],
                created_at=task_data.get("created_at", ""),
            ))

        bm = data.get("benchmark", {})
        ew = bm.get("equal_weight", {})
        c3 = bm.get("csi300", {})
        self.benchmark = BenchmarkPortfolio(
            equal_weight=EqualWeightBenchmark(
                nav=Decimal(ew.get("nav", "0")),
                constituents={k: Decimal(v) for k, v in ew.get("constituents", {}).items()},
                last_rebuild_date=ew.get("last_rebuild_date", ""),
            ),
            csi300=CSI300Benchmark(
                nav=Decimal(c3.get("nav", "0")),
                index_value=Decimal(c3.get("index_value", "3500")),
                last_index_close=Decimal(c3.get("last_index_close", "3500")),
            ),
        )
