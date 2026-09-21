"""decision.v2.24：跨日接回闭环角色；空仓接回可买上限与未接回取小。"""
from dataclasses import replace
from decimal import Decimal

from agent.common.models import ActionType, RiskState
from tests.unit.test_prompt_v213 import _engine, _fill, _quote, _sec, _snap
from tests.unit.test_prompt_v222 import _invariants
from tests.unit.test_prompt_v223 import _overnight_snap


class TestClosedOvernightBuybackRole:
    def test_full_buyback_is_closed_not_add(self):
        engine = _engine(max_trades=1)
        engine._trading_engine = type("T", (), {
            "today_fills": [_fill(ActionType.BUY, 300, "15.80", 9, 40)],
        })()
        snap = replace(
            _snap(shares=300, sellable=0, cash="5000", nav="9770"),
            pending_buyback={},
            buyback_bought_today={"002185": 300},
        )
        prompt = engine._build_prompt(
            snap,
            {"002185": _quote(last=Decimal("15.80"), ask1=Decimal("15.80"))},
            RiskState.NORMAL,
        )
        hold = _sec(prompt, "持仓")
        hard = _sec(prompt, "硬性约束")
        assert "今日已买300股" in hold
        assert "不是接回" not in hold
        assert "买入是接回该笔做T，不是建仓" not in hard
        _invariants(prompt)

    def test_buy_only_without_buyback_still_not_pending(self):
        engine = _engine()
        engine._trading_engine = type("T", (), {
            "today_fills": [_fill(ActionType.BUY, 100, "16.49", 10, 33)],
        })()
        prompt = engine._build_prompt(
            _snap(shares=300, sellable=200, cash="5000.72", nav="9956.72"),
            {"002185": _quote(last=Decimal("16.52"), ask1=Decimal("16.52"))},
            RiskState.NORMAL,
        )
        hold = _sec(prompt, "持仓")
        assert "今日已买100股" in hold
        assert "接回已闭环" not in hold
        _invariants(prompt)


class TestBuyableNotCappedToPending:
    def test_empty_pending_uses_cash_cap_not_pending(self):
        engine = _engine(max_trades=1)
        prompt = engine._build_prompt(
            _overnight_snap(shares=100, cash="9771.75"),
            {"002185": _quote(
                last=Decimal("8.00"), ask1=Decimal("8.00"),
                bid1=Decimal("7.99"), pre_close=Decimal("8.00"),
            )},
            RiskState.NORMAL,
        )
        quotes = _sec(prompt, "股票池行情")
        hard = _sec(prompt, "硬性约束")
        assert "买入是接回不是建仓" not in quotes
        assert "买入是接回该笔做T，不是建仓" not in hard
        assert "最多可买100股" not in quotes
        assert "最多可买900股" in quotes or "最多可买900股" in hard
        _invariants(prompt)
