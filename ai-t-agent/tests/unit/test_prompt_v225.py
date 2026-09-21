"""decision.v2.25：接回价差预计算（数据，非禁令）；费用行去掉打平。"""
from decimal import Decimal

from agent.decision.engine import _buyback_spread_note
from agent.common.models import RiskState
from tests.unit.test_prompt_v213 import _engine, _empty_snap, _quote, _sec, _snap
from tests.unit.test_prompt_v222 import _invariants
from tests.unit.test_prompt_v223 import _overnight_snap


FORCE = (
    "禁止高于卖出价",
    "禁止高接",
    "必须等回落",
    "不得在卖出价上方接回",
    "必须接回",
    "强制接回",
    "禁止在卖出价上方",
)


def _no_force(prompt: str) -> None:
    for kw in FORCE:
        assert kw not in prompt, kw


class TestBuybackSpreadHelper:
    def test_above_sell_negative(self):
        s = _buyback_spread_note(
            Decimal("16.17"), Decimal("15.88"), Decimal("0.11"))
        assert "卖出均价15.88-现价16.17=-0.29元/股（买在卖出价上方）" in s
        assert "扣往返费用后约-0.40元/股" in s
        _no_force(s)

    def test_below_sell_positive(self):
        s = _buyback_spread_note(
            Decimal("15.70"), Decimal("15.88"), Decimal("0.11"))
        assert "卖出均价15.88-现价15.70=+0.18元/股（买在卖出价下方）" in s
        assert "扣往返费用后约+0.07元/股" in s
        _no_force(s)

    def test_equal_sell(self):
        s = _buyback_spread_note(Decimal("15.88"), Decimal("15.88"), Decimal("0.11"))
        assert "现价等于卖出均价" in s
        assert "=+0.00元/股" in s
        _no_force(s)


class TestBuybackSpreadInPrompt:
    def test_above_sell_injected_not_ban(self):
        prompt = _engine(max_trades=1)._build_prompt(
            _overnight_snap(),
            {"002185": _quote(last=Decimal("16.17"), ask1=Decimal("16.17"))},
            RiskState.NORMAL,
        )
        quotes = _sec(prompt, "股票池行情")
        hard = _sec(prompt, "硬性约束")
        assert "若按现价接回：卖出均价15.88-现价16.17=-0.29元/股（买在卖出价上方）" in quotes
        assert "扣往返费用后约" in quotes
        assert "较卖出均价" in quotes
        assert "打平" not in prompt
        assert "也不强制买回" in prompt
        assert "不是接回时机的硬指令" in prompt
        _no_force(prompt)
        _invariants(prompt)

    def test_below_sell_positive_spread(self):
        prompt = _engine(max_trades=1)._build_prompt(
            _overnight_snap(),
            {"002185": _quote(last=Decimal("15.70"), ask1=Decimal("15.70"))},
            RiskState.NORMAL,
        )
        quotes = _sec(prompt, "股票池行情")
        assert "若按现价接回：卖出均价15.88-现价15.70=+0.18元/股（买在卖出价下方）" in quotes
        _no_force(prompt)
        _invariants(prompt)

    def test_no_pending_omits_spread(self):
        prompt = _engine()._build_prompt(
            _empty_snap(),
            {"002185": _quote()},
            RiskState.NORMAL,
        )
        assert "若按现价接回" not in prompt
        assert "买在卖出价上方" not in prompt
        assert "打平" not in prompt
        _no_force(prompt)

    def test_held_without_pending_omits_spread(self):
        prompt = _engine()._build_prompt(
            _snap(),
            {"002185": _quote()},
            RiskState.NORMAL,
        )
        assert "若按现价接回" not in prompt
        _no_force(prompt)
