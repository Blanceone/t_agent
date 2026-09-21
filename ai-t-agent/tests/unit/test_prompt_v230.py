"""decision.v2.30 / planner.v1.9：未接回不再截可买；提示词不做接回/建仓记账。"""
from decimal import Decimal

from agent.config.schema import PromptConfig
from agent.common.models import ActionType, RiskState
from tests.unit.test_prompt_v213 import _engine, _empty_snap, _fill, _quote, _sec, _snap
from tests.unit.test_prompt_v222 import _invariants
from tests.unit.test_prompt_v223 import _overnight_snap


class TestVersion:
    def test_pin(self):
        assert PromptConfig().decision_version == "decision.v2.30"
        assert PromptConfig().planner_version == "planner.v1.9"


class TestPendingNotBuyCap:
    def test_empty_pending_max_buy_follows_cash(self):
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
        assert "最多可买900股" in quotes
        assert "最多可买900股" in hard
        assert "买入是接回不是建仓" not in prompt
        assert "不得超过未接回" not in prompt
        _invariants(prompt)

    def test_empty_pending_allows_buy_not_jiancang_lock(self):
        prompt = _engine()._build_prompt(
            _overnight_snap(),
            {"002185": _quote(last=Decimal("16.35"), ask1=Decimal("16.35"))},
            RiskState.NORMAL,
        )
        hard = _sec(prompt, "硬性约束")
        plan = _sec(prompt, "今日计划")
        hold = _sec(prompt, "持仓")
        rules = _sec(prompt, "规则")
        assert "未接回300股" in hold
        assert "无持仓，无股可卖，禁止发出SELL" in hard
        assert "买入是接回该笔做T，不是建仓" not in prompt
        assert "可买或观望" in plan
        assert "买入建仓或观望（无持仓）" not in plan
        assert "未接回不是买入上限" in rules
        assert "「今日已成交」只记录当天买卖" in prompt
        _invariants(prompt)


class TestBudgetDoneStillAllowsBuy:
    def test_no_new_t_ban_on_buy(self):
        engine = _engine(max_trades=1)
        engine._trading_engine = type("T", (), {
            "today_fills": [_fill(ActionType.SELL, 200, "17.21")],
        })()
        prompt = engine._build_prompt(
            _empty_snap(),
            {"002185": _quote(last=Decimal("17.32"), ask1=Decimal("17.32"))},
            RiskState.NORMAL,
        )
        hard = _sec(prompt, "硬性约束")
        quotes = _sec(prompt, "股票池行情")
        assert "仍可BUY" in hard
        assert "禁止新建仓BUY" not in hard
        assert "新开做T将被拒绝" not in quotes
        _invariants(prompt)


class TestDailyFillsNotTLedger:
    def test_round_trip_shows_buys_and_sells(self):
        engine = _engine()
        engine._trading_engine = type("T", (), {
            "today_fills": [
                _fill(ActionType.SELL, 200, "17.21", 9, 32),
                _fill(ActionType.BUY, 200, "17.32", 10, 10),
            ],
        })()
        prompt = engine._build_prompt(
            _snap(shares=200, sellable=0, nav="10032.48"),
            {"002185": _quote(last=Decimal("17.28"), ask1=Decimal("17.28"))},
            RiskState.NORMAL,
        )
        hold = _sec(prompt, "持仓")
        assert "今日已卖200股/已买200股" in hold
        assert "接回已闭环" not in hold
        _invariants(prompt)
