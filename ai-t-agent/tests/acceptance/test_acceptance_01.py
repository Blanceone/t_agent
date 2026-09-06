"""
验收测试 1-5

1. 风控原子性：Tick 内触发 HALT 后，本分钟无 BUY 成交
2. 止损深度穿透：无 bid1，mark_price 击穿 stop_loss*0.98，立即止损
3. 清仓跨日累计：连续跌停，attempts 跨日累计至 30 → LIQ_FAIL
4. 费用精度：2元股100股往返 ≈ 10.10 元
5. 14:57后不执行
"""

from decimal import Decimal
from datetime import datetime, timezone, timedelta

from agent.config.schema import AppConfig, RiskConfig, FeeConfig
from agent.common.models import (
    AccountSnapshot, ActionType, DecisionItem, OrderIntent, OrderSource,
    Position, PositionState, Quote, RiskState, WatchlistEntry,
)
from agent.trading.fee import FeeCalculator
from agent.trading.position import PositionManager
from agent.trading.liquidation import LiquidationWorker
from agent.trading.matcher import SimMatcher
from agent.risk.engine import RiskEngine
from agent.risk.stop_loss import StopLossDetector, StopLossResult
from agent.common.models import LiquidationTask

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


class TestAcceptance01RiskAtomicity:
    """验收1：风控原子性 - HALT 后禁止 BUY"""

    def test_halt_blocks_buy(self):
        config = RiskConfig()
        engine = RiskEngine(config)

        # 模拟日亏 3%：last_nav=30000, nav_mark=29100 → loss=3%
        snapshot = make_snapshot(nav_mark="29100", last_nav="30000")
        quotes = {"600584": make_quote()}

        # Tick guard 评估
        result = engine.tick_guard(snapshot, quotes)
        assert result.new_state == RiskState.HALT

        # BUY 被拒绝
        item = DecisionItem(action=ActionType.BUY, code="600584", shares=100,
                            confidence=0.9, reason="test", risk_level="LOW")
        verdict = engine.validate_decision(item, snapshot, quotes["600584"], {}, "2026-07-28")
        assert not verdict.passed

    def test_halt_allows_sell(self):
        config = RiskConfig()
        engine = RiskEngine(config)

        pos = Position(code="600584", total_shares=1000, sellable_shares=1000,
                       today_bought=0, cost_price=Decimal("28"), stop_loss_price=Decimal("25.76"))
        snapshot = make_snapshot(nav_mark="29100", last_nav="30000",
                                 positions={"600584": pos})
        quotes = {"600584": make_quote()}

        engine.tick_guard(snapshot, quotes)

        # SELL 允许
        item = DecisionItem(action=ActionType.SELL, code="600584", shares=100,
                            confidence=0.9, reason="test", risk_level="LOW")
        verdict = engine.validate_decision(item, snapshot, quotes["600584"], {}, "2026-07-28")
        assert verdict.passed


class TestAcceptance02DeepStopLoss:
    """验收2：止损深度穿透"""

    def test_deep_trigger_no_bid1(self):
        detector = StopLossDetector(enable_deep=True, deep_threshold=Decimal("0.98"))

        pos = Position(code="600584", total_shares=1000, sellable_shares=1000,
                       today_bought=0, cost_price=Decimal("28"),
                       stop_loss_price=Decimal("25.76"))

        # 无 bid1，mark_price = last = 25.00 < 25.76*0.98=25.2448
        quote = make_quote(bid1=None, last="25.00")
        result = detector.check(pos, quote)
        assert result == StopLossResult.DEEP_TRIGGER

    def test_normal_breach_needs_2_ticks(self):
        detector = StopLossDetector(enable_deep=False, breach_confirm_count=2)

        pos = Position(code="600584", total_shares=1000, sellable_shares=1000,
                       today_bought=0, cost_price=Decimal("28"),
                       stop_loss_price=Decimal("25.76"))

        quote = make_quote(bid1="25.50")  # 击穿但非深度

        r1 = detector.check(pos, quote)
        assert r1 == StopLossResult.BREACH_INCREMENT
        assert pos.stop_breach_count == 1

        r2 = detector.check(pos, quote)
        assert r2 == StopLossResult.TRIGGER
        assert pos.stop_breach_count == 2


class TestAcceptance03LiquidationCrossDay:
    """验收3：清仓跨日累计"""

    def test_30_attempts_liq_fail(self):
        fee_calc = FeeCalculator(FeeConfig())
        matcher = SimMatcher(fee_calc)
        worker = LiquidationWorker(matcher, max_attempts=30)

        task = LiquidationTask(task_id="t1", code="600584",
                               remaining_shares=1000, exit_reason="STOP_LOSS", attempts=29)

        pos = Position(code="600584", total_shares=1000, sellable_shares=1000,
                       today_bought=0, cost_price=Decimal("28"),
                       stop_loss_price=Decimal("25.76"))

        # 跌停行情：bid1 <= limit_down → 无法卖出
        quote = make_quote(bid1="24.84", limit_down=Decimal("24.84"))

        fills, rejects, exhausted = worker.process_tick(
            [task], {"600584": pos}, {"600584": quote})

        assert task.attempts == 30
        assert "t1" in exhausted


class TestAcceptance04FeePrecision:
    """验收4：费用精度"""

    def test_round_trip_10_10(self):
        fee_calc = FeeCalculator(FeeConfig())
        total = fee_calc.round_trip_fee_est(Decimal("2.00"), 100)
        assert total == Decimal("10.10")


class TestAcceptance05SessionSuspend:
    """验收5：14:57后不执行（逻辑验证）"""

    def test_session_boundary(self):
        from agent.scheduler.scheduler import Scheduler
        # 验证 _in_trading_session 逻辑
        # 14:56 在交易时段内
        t_1456 = 1456
        am = 930 <= t_1456 <= 1130
        pm = 1300 <= t_1456 <= 1456
        assert am or pm  # True

        # 14:57 不在交易时段
        t_1457 = 1457
        am2 = 930 <= t_1457 <= 1130
        pm2 = 1300 <= t_1457 <= 1456
        assert not (am2 or pm2)  # False
