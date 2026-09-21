"""decision.v2.23 / planner.v1.7：上限 0 不是已满；跨日未接回是接回不是建仓。"""
from dataclasses import replace
from decimal import Decimal

from agent.common.models import MarketRegime, PendingBuyback, RiskState
from agent.decision.planner import Planner
from agent.market.understanding import MarketUnderstandingOutput
from tests.unit.test_prompt_v213 import (
    OPEN_JIANCANG,
    FakeLLM,
    _engine,
    _empty_snap,
    _quote,
    _sec,
)
from tests.unit.test_prompt_v222 import _engine_strat, _invariants, _role


def _overnight_snap(shares=300, avg="15.88", cash="9771.75"):
    return replace(
        _empty_snap(cash=cash, nav=cash),
        pending_buyback={
            "002185": PendingBuyback(
                code="002185",
                shares=shares,
                sell_avg=Decimal(avg),
                sell_date="2026-09-07",
            )
        },
    )


class TestWaitZeroNotExhausted:
    def test_wait_zero_empty_allows_jiancang_not_hold_only(self):
        engine = _engine_strat("WAIT", max_trades=0)
        prompt = engine._build_prompt(
            _empty_snap(cash="9771.75", nav="9771.75"),
            {"002185": _quote()},
            RiskState.NORMAL,
        )
        hard = _sec(prompt, "硬性约束")
        plan = _sec(prompt, "今日计划")
        assert "达到上限0次" not in hard
        assert "停止交易只可HOLD" not in hard
        assert "禁止发出BUY（今日该标的只可HOLD）" not in prompt
        assert "买入建仓或观望（无持仓）" in plan
        assert "HOLD（做T次数已满）" not in plan
        assert "上限0不是次数已满" in prompt or "上限0不是已满" in prompt
        _invariants(prompt)


class TestOvernightPending:
    def test_empty_book_carried_pending_is_buyback(self):
        engine = _engine(max_trades=1)
        prompt = engine._build_prompt(
            _overnight_snap(),
            {"002185": _quote(last=Decimal("15.97"), ask1=Decimal("15.97"))},
            RiskState.NORMAL,
        )
        hold = _sec(prompt, "持仓")
        hard = _sec(prompt, "硬性约束")
        plan = _sec(prompt, "今日计划")
        assert "持仓0股" in hold
        assert "未接回300股" in hold
        assert "卖出均价15.88" in hold
        assert "## 持仓\n无持仓" not in prompt
        assert "买入是接回该笔做T，不是建仓" not in hard
        assert "可买或观望" in plan
        assert "接回买入（未接回300股）" not in plan
        assert "买入建仓或观望（无持仓）" not in plan
        for kw in OPEN_JIANCANG:
            assert kw not in _role(prompt)
        _invariants(prompt)

    def test_wait_zero_with_overnight_pending_still_buyback(self):
        engine = _engine_strat("WAIT", max_trades=0)
        prompt = engine._build_prompt(
            _overnight_snap(),
            {"002185": _quote(last=Decimal("15.97"), ask1=Decimal("15.97"))},
            RiskState.NORMAL,
        )
        hard = _sec(prompt, "硬性约束")
        plan = _sec(prompt, "今日计划")
        assert "达到上限0次" not in hard
        assert "停止交易只可HOLD" not in hard
        assert "买入是接回该笔做T，不是建仓" not in hard
        assert "可买或观望" in plan
        assert "接回买入（未接回300股）" not in plan
        assert "买入建仓或观望（无持仓）" not in plan
        _invariants(prompt)

    def test_planner_sees_overnight_pending(self):
        llm = FakeLLM()
        planner = Planner(llm)
        mu = MarketUnderstandingOutput(
            date="2026-09-08", market_regime=MarketRegime.RANGE,
            today_risk_level="MEDIUM", today_strategy_preference="BALANCED",
            today_market_summary="震荡",
        )
        q = _quote(last=Decimal("16.08"))
        planner.generate(
            "2026-09-08", mu, _overnight_snap(), {"002185": q}, ["002185"],
        )
        p = llm.prompt
        assert p is not None
        assert "未接回300股" in p
        assert "卖出均价15.88" in p
        assert "不是买入上限" in p
        assert "不要把 max_trades_hint 写成 0" in p
