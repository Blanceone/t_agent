"""代码层闸：同分钟冲突仲裁、做T预算、可卖为0去重。"""

from types import SimpleNamespace
from decimal import Decimal

from agent.common.models import ActionType, DecisionItem, RejectReason
from agent.config.schema import RiskConfig
from agent.decision.validator import DecisionValidator
from agent.risk.engine import RiskEngine
from agent.scheduler.order_filter import (
    OncePerDay,
    conflict_drop_actions,
    is_impossible_sell,
    keep_action_on_conflict,
)
from tests.acceptance.test_acceptance_02 import make_quote, make_snapshot


def _item(action, shares=100, code="002185"):
    return DecisionItem(
        action=action, code=code, shares=shares,
        confidence=0.9, reason="test", risk_level="LOW",
    )


class TestConflictArbitration:
    def test_sellable_keeps_sell(self):
        assert keep_action_on_conflict(100) == ActionType.SELL
        decisions = [_item(ActionType.SELL), _item(ActionType.BUY)]
        drop = conflict_drop_actions(
            decisions, {"002185": SimpleNamespace(sellable_shares=100)})
        assert drop["002185"] == ActionType.BUY

    def test_locked_keeps_buy(self):
        decisions = [_item(ActionType.SELL, 200), _item(ActionType.BUY, 200)]
        drop = conflict_drop_actions(
            decisions, {"002185": SimpleNamespace(sellable_shares=0)})
        assert drop["002185"] == ActionType.SELL

    def test_no_conflict_empty(self):
        drop = conflict_drop_actions(
            [_item(ActionType.SELL)], {"002185": SimpleNamespace(sellable_shares=100)})
        assert drop == {}


class TestImpossibleSell:
    def test_t1_locked(self):
        assert is_impossible_sell(
            _item(ActionType.SELL), SimpleNamespace(sellable_shares=0))

    def test_buy_not_blocked(self):
        assert not is_impossible_sell(
            _item(ActionType.BUY), SimpleNamespace(sellable_shares=0))


class TestOncePerDay:
    def test_second_call_false(self):
        gate = OncePerDay()
        assert gate.first_time("2026-08-24", "002185", "NO_SELLABLE")
        assert not gate.first_time("2026-08-24", "002185", "NO_SELLABLE")
        assert gate.first_time("2026-08-25", "002185", "NO_SELLABLE")


class TestTBudgetRisk:
    def test_hold_only_rejects_buy_and_sell(self):
        risk = RiskEngine(RiskConfig())
        snapshot = make_snapshot()
        quote = make_quote()
        buy = _item(ActionType.BUY, code="600584")
        sell = _item(ActionType.SELL, code="600584")
        vb = risk.validate_decision(buy, snapshot, quote, {}, "2026-07-28",
                                    t_status="hold_only")
        vs = risk.validate_decision(sell, snapshot, quote, {}, "2026-07-28",
                                    t_status="hold_only")
        assert not vb.passed and not vs.passed
        assert vb.reason_code == RejectReason.T_BUDGET_EXCEEDED

    def test_open_still_allows_confident_buy(self):
        risk = RiskEngine(RiskConfig())
        snapshot = make_snapshot()
        quote = make_quote()
        buy = _item(ActionType.BUY, code="600584")
        v = risk.validate_decision(buy, snapshot, quote, {}, "2026-07-28",
                                   t_status="open")
        assert v.passed


class TestValidatorLot:
    def test_does_not_floor_buy_shares(self):
        raw = {
            "thought_process": "x",
            "decisions": [{
                "action": "BUY", "code": "002185", "shares": 150,
                "confidence": 0.8, "reason": "x", "risk_level": "LOW",
            }],
        }
        out = DecisionValidator().validate(raw)
        assert out is not None
        assert out.decisions[0].shares == 150
