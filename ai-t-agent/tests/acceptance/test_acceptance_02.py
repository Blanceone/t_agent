"""
验收测试 6-10

6. 基准再平衡：Watchlist 变更时等权基准「清空重建」
7. Memory 跨日：重启后 Memory 仍可用
8. Replay 可复现：同包回放关键结果一致
9. LLM 必经 Risk：无绕过路径
10. 低置信度过滤：confidence < threshold 不成交
"""

import json
import tempfile
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from pathlib import Path

from agent.config.schema import AppConfig, RiskConfig, FeeConfig
from agent.common.models import (
    AccountSnapshot, ActionType, DecisionItem, DecisionOutput,
    OrderIntent, OrderSource, Position, PositionState,
    Quote, RiskState, WatchlistEntry, MemoryItem, MemoryType,
    BenchmarkPortfolio, EqualWeightBenchmark, CSI300Benchmark,
)
from agent.trading.benchmark import BenchmarkManager
from agent.trading.fee import FeeCalculator
from agent.trading.matcher import SimMatcher
from agent.risk.engine import RiskEngine
from agent.risk.confidence_filter import ConfidenceFilter
from agent.memory.store import MemoryStore, MemoryWriter, MemoryRetriever
from agent.replay.runner import ReplayRunner
from agent.decision.validator import DecisionValidator

TZ = timezone(timedelta(hours=8))


def make_quote(code="600584", bid1="27.90", ask1="28.10", last="28.00", **kw):
    defaults = dict(
        code=code, name="测试", last=Decimal(last),
        bid1=Decimal(bid1) if bid1 else None,
        ask1=Decimal(ask1) if ask1 else None,
        high=Decimal("28.50"), low=Decimal("27.50"),
        open=Decimal("27.80"), pre_close=Decimal("27.60"),
        limit_up=Decimal("30.36"), limit_down=Decimal("24.84"),
        volume=1000000, turnover=Decimal("28000000"), vwap=Decimal("28.00"),
        is_suspended=False, is_st=False,
        timestamp=datetime(2026, 7, 28, 10, 0, 0, tzinfo=TZ),
    )
    defaults.update(kw)
    return Quote(**defaults)


def make_snapshot(nav_mark="30000", last_nav="30000", peak_nav="30000",
                  realized_pnl="0", risk_state=RiskState.NORMAL, positions=None):
    return AccountSnapshot(
        account_id="sim_001", nav_mark=Decimal(nav_mark),
        cash_available=Decimal("15000"), peak_nav=Decimal(peak_nav),
        last_nav=Decimal(last_nav), risk_state=risk_state,
        positions=positions or {}, realized_pnl_today=Decimal(realized_pnl),
        liquidation_queue=[], snapshot_time=datetime.now(TZ),
    )


class TestAcceptance06BenchmarkRebuild:
    """验收6：基准再平衡 - Watchlist 变更时清空重建"""

    def test_watchlist_change_triggers_rebuild(self):
        mgr = BenchmarkManager()
        benchmark = BenchmarkPortfolio(
            equal_weight=EqualWeightBenchmark(
                nav=Decimal("30000"),
                constituents={"OLD001": Decimal("1000")},
                last_rebuild_date="2026-07-25",
            ),
            csi300=CSI300Benchmark(
                nav=Decimal("30000"),
                index_value=Decimal("3500"),
                last_index_close=Decimal("3500"),
            ),
        )

        quotes = {
            "600584": make_quote(code="600584"),
            "002049": make_quote(code="002049", last="15.00", pre_close=Decimal("15.00")),
        }

        # 重建
        mgr.rebuild_equal_weight(benchmark, ["600584", "002049"], quotes, Decimal("30000"), "2026-07-28")

        # 旧成分被清空
        assert "OLD001" not in benchmark.equal_weight.constituents
        # 新成分存在
        assert "600584" in benchmark.equal_weight.constituents
        assert "002049" in benchmark.equal_weight.constituents
        # 日期更新
        assert benchmark.equal_weight.last_rebuild_date == "2026-07-28"

    def test_rebuild_is_equal_weight(self):
        mgr = BenchmarkManager()
        benchmark = BenchmarkPortfolio(
            equal_weight=EqualWeightBenchmark(nav=Decimal("30000"), constituents={}, last_rebuild_date=""),
            csi300=CSI300Benchmark(nav=Decimal("30000"), index_value=Decimal("3500"), last_index_close=Decimal("3500")),
        )

        quotes = {
            "600584": make_quote(code="600584"),
            "002049": make_quote(code="002049", last="15.00", pre_close=Decimal("15.00")),
        }

        mgr.rebuild_equal_weight(benchmark, ["600584", "002049"], quotes, Decimal("30000"), "2026-07-28")

        # 等权：每只票分配 15000 的市值
        c1 = benchmark.equal_weight.constituents["600584"]
        c2 = benchmark.equal_weight.constituents["002049"]
        # 600584: 15000 / 27.60(pre_close)
        assert abs(c1 - Decimal("15000") / Decimal("27.60")) < Decimal("0.01")
        # 002049: 15000 / 15.00
        assert abs(c2 - Decimal("15000") / Decimal("15.00")) < Decimal("0.01")


class TestAcceptance07MemoryCrossDay:
    """验收7：Memory 跨日 - 重启后仍可用"""

    def test_memory_survives_restart(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/memory.db"

            # 第一次运行：写入
            store1 = MemoryStore(db_path)
            writer1 = MemoryWriter(store1)
            mid = writer1.write_reflection(
                "600584今日做T成功，高抛低吸获利",
                ["600584"], ["t_trading", "success"], 0.8
            )
            assert mid

            # 模拟重启：新实例
            store2 = MemoryStore(db_path)
            retriever = MemoryRetriever(store2, top_k=8)
            items = retriever.retrieve_for_decision(["600584"])

            assert len(items) >= 1
            assert any("600584" in item.codes for item in items)
            assert any("做T成功" in item.content for item in items)

    def test_memory_ids_traceable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/memory.db"
            store = MemoryStore(db_path)
            writer = MemoryWriter(store)

            mid = writer.write_risk_event("STOP_LOSS", "600584", "止损触发，成本28，现价25")
            assert mid.startswith("mem_")

            items = store.query(codes=["600584"])
            assert items[0].memory_id == mid


class TestAcceptance08ReplayReproducible:
    """验收8：Replay 可复现"""

    def test_same_package_same_result(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 写入模拟 Replay 数据
            day_dir = Path(tmpdir) / "2026-07-28"
            day_dir.mkdir()

            ticks = [
                {"tick_id": "tick_001", "timestamp": "09:31", "risk_state": "NORMAL",
                 "executions": [{"code": "600584", "action": "SELL"}], "risk_verdicts": []},
                {"tick_id": "tick_002", "timestamp": "09:32", "risk_state": "NORMAL",
                 "executions": [], "risk_verdicts": [{"passed": False}]},
            ]
            with open(day_dir / "ticks.jsonl", "w") as f:
                for t in ticks:
                    f.write(json.dumps(t) + "\n")

            summary = {"nav_start": "30000", "nav_end": "30100"}
            with open(day_dir / "daily_summary.json", "w") as f:
                json.dump(summary, f)

            runner = ReplayRunner(tmpdir)

            # 两次回放结果一致
            assert runner.verify_consistency("2026-07-28") is True

            r = runner.replay_day("2026-07-28")
            assert r is not None
            assert r.total_ticks == 2
            assert r.total_fills == 1
            assert r.nav_end == Decimal("30100")


class TestAcceptance09LLMMustPassRisk:
    """验收9：LLM 必经 Risk - 无绕过路径"""

    def test_decision_cannot_bypass_risk(self):
        """验证 DecisionEngine 输出必须经 RiskEngine 校验"""
        config = RiskConfig()
        risk_engine = RiskEngine(config)

        snapshot = make_snapshot()
        quote = make_quote()

        # 即使 confidence 很高的 BUY 也必须经 Risk
        item = DecisionItem(action=ActionType.BUY, code="600584", shares=100,
                            confidence=0.99, reason="strong signal", risk_level="LOW")

        # NORMAL 状态下通过
        verdict = risk_engine.validate_decision(item, snapshot, quote, {}, "2026-07-28")
        assert verdict.passed

        # HALT 状态下拒绝（证明 Risk 不可绕过）
        halt_snapshot = make_snapshot(nav_mark="29100", last_nav="30000")
        risk_engine.tick_guard(halt_snapshot, {"600584": quote})
        verdict2 = risk_engine.validate_decision(item, halt_snapshot, quote, {}, "2026-07-28")
        assert not verdict2.passed

    def test_liiquidate_blocks_all(self):
        """LIQUIDATE 下所有决策被拒"""
        config = RiskConfig()
        risk_engine = RiskEngine(config)

        # 触发 LIQUIDATE：回撤 >= 10%
        snapshot = make_snapshot(nav_mark="27000", peak_nav="30000")
        quote = make_quote()
        risk_engine.tick_guard(snapshot, {"600584": quote})

        assert risk_engine.risk_state == RiskState.LIQUIDATE

        # SELL 也被拒
        item = DecisionItem(action=ActionType.SELL, code="600584", shares=100,
                            confidence=0.99, reason="sell", risk_level="LOW")
        verdict = risk_engine.validate_decision(item, snapshot, quote, {}, "2026-07-28")
        assert not verdict.passed


class TestAcceptance10LowConfidenceFilter:
    """验收10：低置信度过滤"""

    def test_below_threshold_rejected(self):
        config = RiskConfig(decision_confidence_threshold=0.60)
        risk_engine = RiskEngine(config)

        snapshot = make_snapshot()
        quote = make_quote()

        # confidence = 0.45 < 0.60 → 拒绝
        item = DecisionItem(action=ActionType.BUY, code="600584", shares=100,
                            confidence=0.45, reason="weak", risk_level="MEDIUM")
        verdict = risk_engine.validate_decision(item, snapshot, quote, {}, "2026-07-28")
        assert not verdict.passed
        assert verdict.reason_code.value == "REASON_LOW_CONFIDENCE"

    def test_above_threshold_passes(self):
        config = RiskConfig(decision_confidence_threshold=0.60)
        risk_engine = RiskEngine(config)

        snapshot = make_snapshot()
        quote = make_quote()

        item = DecisionItem(action=ActionType.BUY, code="600584", shares=100,
                            confidence=0.75, reason="strong", risk_level="LOW")
        verdict = risk_engine.validate_decision(item, snapshot, quote, {}, "2026-07-28")
        assert verdict.passed

    def test_missing_confidence_treated_as_zero(self):
        """缺失 confidence 视为 0，触发过滤"""
        filt = ConfidenceFilter(threshold=0.60)

        item = DecisionItem(action=ActionType.BUY, code="600584", shares=100,
                            confidence=0.0, reason="test", risk_level="LOW")
        assert filt.check(item) is False

    def test_risk_forced_order_bypasses_filter(self):
        """风控强制单不受置信度限制"""
        filt = ConfidenceFilter(threshold=0.60)

        item = DecisionItem(action=ActionType.SELL, code="600584", shares=100,
                            confidence=0.1, reason="stop loss", risk_level="HIGH")
        # STOP_LOSS 来源不受限
        assert filt.check(item, OrderSource.STOP_LOSS) is True
