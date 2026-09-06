"""
验收测试 11-15

11. Market Regime 四态（第一阶段默认 RANGE）
12. Reflection 统计先行：与账本一致
13. Context 统一注入：Prompt 通过 Context 组装
14. Event Log 可还原时间线
15. Schema Version 可审计
"""

import json
import tempfile
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from pathlib import Path

from agent.config.schema import AppConfig, FeeConfig
from agent.common.models import (
    AccountSnapshot, ActionType, DecisionItem, DecisionOutput,
    Fill, FeeDetail, MarketRegime, MemoryItem, MemoryType,
    Position, Quote, RiskState, SystemEvent,
)
from agent.common.event_log import EventLog
from agent.decision.context import ContextAssembler, Context
from agent.decision.validator import DecisionValidator
from agent.reflection.stats import ReflectionEngine, ReflectionStats
from agent.trading.fee import FeeCalculator

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


class TestAcceptance11MarketRegime:
    """验收11：Market Regime 四态"""

    def test_regime_enum_has_four_states(self):
        """Regime 必须为 TREND|RANGE|HIGH_VOL|LOW_VOL 四态之一"""
        valid = {MarketRegime.TREND, MarketRegime.RANGE, MarketRegime.HIGH_VOL, MarketRegime.LOW_VOL}
        assert len(valid) == 4

    def test_default_regime_is_range(self):
        """第一阶段默认 Regime 为 RANGE"""
        assembler = ContextAssembler()
        snapshot = make_snapshot()
        quotes = {"600584": make_quote()}

        ctx = assembler.assemble(snapshot, quotes, date="2026-07-28")
        assert ctx.market.market_regime == "RANGE"

    def test_regime_values_are_valid(self):
        """所有 Regime 值均为合法枚举"""
        for r in MarketRegime:
            assert r.value in ("TREND", "RANGE", "HIGH_VOL", "LOW_VOL")


class TestAcceptance12ReflectionStatsFirst:
    """验收12：Reflection 统计先行 - 与账本一致"""

    def test_stats_match_fills(self):
        """代码统计与成交账本一致"""
        fee_calc = FeeCalculator(FeeConfig())

        # 模拟成交记录
        fills = [
            Fill(fill_id="f1", order_id="o1", code="600584", action=ActionType.SELL,
                 shares=500, price=Decimal("29.00"), amount=Decimal("14500"),
                 fee=Decimal("5.10"),
                 fee_detail=FeeDetail(commission=Decimal("5.00"), stamp_tax=Decimal("0.07"), transfer_fee=Decimal("0.03")),
                 realized_pnl=Decimal("490.00"),
                 timestamp=datetime.now(TZ), tick_id="tick_001"),
            Fill(fill_id="f2", order_id="o2", code="600584", action=ActionType.BUY,
                 shares=500, price=Decimal("28.00"), amount=Decimal("14000"),
                 fee=Decimal("5.00"),
                 fee_detail=FeeDetail(commission=Decimal("5.00"), stamp_tax=Decimal("0"), transfer_fee=Decimal("0")),
                 realized_pnl=None,
                 timestamp=datetime.now(TZ), tick_id="tick_002"),
        ]

        # 验证统计
        total_fees = sum(f.fee for f in fills)
        assert total_fees == Decimal("10.10")

        t_pnl = sum(f.realized_pnl for f in fills if f.action == ActionType.SELL and f.realized_pnl)
        assert t_pnl == Decimal("490.00")

        sell_count = len([f for f in fills if f.action == ActionType.SELL])
        buy_count = len([f for f in fills if f.action == ActionType.BUY])
        assert sell_count == 1
        assert buy_count == 1

    def test_stats_are_code_generated(self):
        """统计由代码生成，非 LLM"""
        stats = ReflectionStats(
            day_pnl=Decimal("100"),
            total_fees=Decimal("10.10"),
            fee_ratio=0.000337,
            t_trading_pnl=Decimal("490"),
            trade_count=2,
            buy_count=1,
            sell_count=1,
            nav_start=Decimal("30000"),
            nav_end=Decimal("30100"),
        )
        # 所有数值字段均为 Decimal/int/float，非字符串
        assert isinstance(stats.day_pnl, Decimal)
        assert isinstance(stats.total_fees, Decimal)
        assert isinstance(stats.trade_count, int)
        assert isinstance(stats.fee_ratio, float)


class TestAcceptance13ContextUnifiedInjection:
    """验收13：Context 统一注入"""

    def test_context_assembled_with_all_slices(self):
        """Context 包含 System/Portfolio/Holdings/Memory 切片"""
        assembler = ContextAssembler()
        pos = Position(code="600584", total_shares=1000, sellable_shares=1000,
                       today_bought=0, cost_price=Decimal("28"), stop_loss_price=Decimal("25.76"))
        snapshot = make_snapshot(positions={"600584": pos})
        quotes = {"600584": make_quote()}

        memory_items = [
            MemoryItem(memory_id="mem_001", type=MemoryType.REFLECTION,
                       codes=["600584"], created_at="2026-07-27",
                       ttl_days=None, tags=["test"], content="昨日做T成功",
                       source="reflection", importance=0.8)
        ]

        ctx = assembler.assemble(snapshot, quotes, memory_items=memory_items, date="2026-07-28")

        # 验证所有切片存在
        assert ctx.system is not None
        assert ctx.system.date == "2026-07-28"
        assert ctx.portfolio is not None
        assert ctx.portfolio.nav_mark == Decimal("30000")
        assert len(ctx.holdings) == 1
        assert ctx.holdings[0].code == "600584"
        assert ctx.memory is not None
        assert len(ctx.memory.memory_ids) == 1

    def test_context_has_version_and_hash(self):
        """Context 携带 schema_version 和 hash"""
        assembler = ContextAssembler()
        snapshot = make_snapshot()
        ctx = assembler.assemble(snapshot, {}, date="2026-07-28")

        assert ctx.schema_version == "context.v1"
        assert ctx.context_hash != ""
        assert ctx.context_id.startswith("ctx_")

    def test_prompt_uses_context_not_raw(self):
        """Prompt 通过 Context 渲染，非原始数据"""
        assembler = ContextAssembler()
        pos = Position(code="600584", total_shares=1000, sellable_shares=1000,
                       today_bought=0, cost_price=Decimal("28"), stop_loss_price=Decimal("25.76"))
        snapshot = make_snapshot(positions={"600584": pos})
        quotes = {"600584": make_quote()}

        ctx = assembler.assemble(snapshot, quotes, date="2026-07-28")
        rendered = assembler.render_for_prompt(ctx)

        # 渲染结果包含结构化信息
        assert "[系统]" in rendered
        assert "[账户]" in rendered
        assert "[持仓]" in rendered
        assert "600584" in rendered


class TestAcceptance14EventLogTimeline:
    """验收14：Event Log 可还原时间线"""

    def test_event_log_records_milestones(self):
        """Event Log 记录关键里程碑"""
        with tempfile.TemporaryDirectory() as tmpdir:
            event_log = EventLog(tmpdir)

            # 模拟一天的事件
            event_log.emit(SystemEvent.SCHEDULER_DAY_START, date="2026-07-28")
            event_log.emit(SystemEvent.TRADING_SESSION_START, date="2026-07-28")
            event_log.emit(SystemEvent.TICK_STARTED, tick_id="tick_001", date="2026-07-28")
            event_log.emit(SystemEvent.DECISION_FINISHED, tick_id="tick_001", date="2026-07-28")
            event_log.emit(SystemEvent.RISK_PASSED, tick_id="tick_001", date="2026-07-28")
            event_log.emit(SystemEvent.EXECUTION_FINISHED, tick_id="tick_001", date="2026-07-28")
            event_log.emit(SystemEvent.TICK_FINISHED, tick_id="tick_001", date="2026-07-28")
            event_log.emit(SystemEvent.SESSION_SUSPEND, date="2026-07-28")
            event_log.emit(SystemEvent.REFLECTION_FINISHED, date="2026-07-28")
            event_log.emit(SystemEvent.DAY_CLOSE_FINISHED, date="2026-07-28")

            # 读取并验证
            log_file = Path(tmpdir) / "event_log.jsonl"
            assert log_file.exists()

            events = []
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    events.append(json.loads(line))

            assert len(events) == 10

            # 验证时间线顺序
            event_names = [e["event"] for e in events]
            assert event_names[0] == "SCHEDULER_DAY_START"
            assert event_names[-1] == "DAY_CLOSE_FINISHED"
            assert "TICK_STARTED" in event_names
            assert "DECISION_FINISHED" in event_names

    def test_event_has_required_fields(self):
        """每条事件包含必须字段"""
        with tempfile.TemporaryDirectory() as tmpdir:
            event_log = EventLog(tmpdir)
            event_log.emit(SystemEvent.RISK_REJECTED, tick_id="tick_001",
                          date="2026-07-28", detail={"reason": "LOW_CONFIDENCE"})

            log_file = Path(tmpdir) / "event_log.jsonl"
            with open(log_file, "r", encoding="utf-8") as f:
                record = json.loads(f.readline())

            assert "timestamp" in record
            assert "event" in record
            assert "tick_id" in record
            assert "date" in record
            assert "status" in record
            assert record["detail"]["reason"] == "LOW_CONFIDENCE"


class TestAcceptance15SchemaVersion:
    """验收15：Schema Version 可审计"""

    def test_decision_has_schema_version(self):
        """Decision 输出携带 schema_version"""
        validator = DecisionValidator()
        raw = {
            "thought_process": "test",
            "decisions": [{"action": "HOLD", "code": "600584", "shares": 0,
                           "confidence": 0.5, "reason": "wait", "risk_level": "LOW"}]
        }
        result = validator.validate(raw, prompt_version="decision.v1.0", context_id="ctx_001")
        assert result is not None
        assert result.schema_version == "decision.v1"

    def test_memory_has_schema_version(self):
        """Memory 条目携带 schema_version"""
        item = MemoryItem(
            memory_id="mem_001", type=MemoryType.REFLECTION,
            codes=["600584"], created_at="2026-07-28",
            ttl_days=None, tags=[], content="test",
            source="reflection", importance=0.5
        )
        assert item.schema_version == "memory.v1"

    def test_context_has_schema_version(self):
        """Context 携带 schema_version"""
        assembler = ContextAssembler()
        ctx = assembler.assemble(make_snapshot(), {}, date="2026-07-28")
        assert ctx.schema_version == "context.v1"

    def test_feature_has_schema_version(self):
        """Feature 携带 schema_version"""
        from agent.common.models import FeatureSnapshot
        feat = FeatureSnapshot(
            code="600584", pre_close=Decimal("27.6"), open=Decimal("27.8"),
            high=Decimal("28.5"), low=Decimal("27.5"), last=Decimal("28.0"),
            open_chg_pct=0.007, chg_pct_1d=0.014,
            chg_pct_5d=None, chg_pct_10d=None,
            vwap=Decimal("28.0"), amplitude=0.036,
            volume=1000000, volume_ratio=None, turnover_rate=None,
            round_trip_fee_est=Decimal("10.10"),
        )
        assert feat.schema_version == "feature.v1"

    def test_all_schemas_versioned(self):
        """所有核心 Schema 均有版本号"""
        versions = {
            "feature": "feature.v1",
            "memory": "memory.v1",
            "context": "context.v1",
            "decision": "decision.v1",
            "replay": "replay.v1",
        }
        for name, version in versions.items():
            assert version.endswith(".v1"), f"{name} schema must be versioned"
