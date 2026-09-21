"""decision.v2.29：取消 50% 单票仓位上限，仓位由模型自控；现金预留 20% 仍在。"""
from decimal import Decimal

from agent.config.schema import AppConfig, RiskConfig
from agent.common.models import RiskState
from tests.unit.test_prompt_v213 import _engine, _quote, _sec, _snap
from tests.unit.test_prompt_v222 import _invariants


class TestVersion:
    def test_ratio_still_one(self):
        assert RiskConfig().max_single_position_ratio == Decimal("1.00")
        assert AppConfig().risk.max_single_position_ratio == Decimal("1.00")


class TestNoFiftyPercentCap:
    def test_held_200_can_still_buy(self):
        prompt = _engine()._build_prompt(
            _snap(), {"002185": _quote()}, RiskState.NORMAL)
        hard = _sec(prompt, "硬性约束")
        rules = _sec(prompt, "规则")
        assert "单票上限剩余不足100股，禁止加仓BUY" not in prompt
        assert "最多可买" in hard
        assert "现金预留" in rules
        assert "不是必须加减仓" in rules
        _invariants(prompt)
