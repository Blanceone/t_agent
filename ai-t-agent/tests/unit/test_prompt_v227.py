"""decision.v2.27 / planner.v1.8：提示词去掉策略硬逻辑，硬约束只留账户事实。"""
from decimal import Decimal

from agent.common.models import ActionType, MarketRegime, RiskState
from agent.decision.planner import Planner
from agent.market.understanding import MarketUnderstandingOutput
from tests.unit.test_prompt_v213 import FakeLLM, _engine, _empty_snap, _fill, _quote, _sec, _snap
from tests.unit.test_prompt_v222 import _invariants


FORCE = (
    "仅允许接回BUY",
    "完成本次做T",
    "仅可执行计划中的买入建仓部分",
    "高抛低吸",
    "首次建仓不超过",
    "累计不超过目标仓位",
    "低于目标仓位比例时允许买入",
)


def _instruction(prompt: str) -> str:
    """文首 + 硬约束 + 规则，不含当日计划正文。"""
    return (
        prompt.split("## 硬性约束", 1)[0]
        + _sec(prompt, "硬性约束")
        + _sec(prompt, "规则")
    )


class TestNoStrategyForce:
    def test_held_prompt_has_no_force(self):
        prompt = _engine()._build_prompt(
            _snap(), {"002185": _quote()}, RiskState.NORMAL)
        inst = _instruction(prompt)
        for kw in FORCE:
            assert kw not in inst, kw
        assert "不是必须加减仓" in _sec(prompt, "规则")
        assert "可以买卖或继续持有" in _sec(prompt, "规则")
        _invariants(prompt)

    def test_budget_done_pending_is_fact_not_must_buyback(self):
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
        inst = _instruction(prompt)
        for kw in FORCE:
            assert kw not in inst, kw
        assert "禁止发出SELL和新建仓BUY" not in hard
        assert "仍可BUY" in hard
        assert "接回BUY仍可执行" not in hard
        assert "不强制今日接回" not in hard
        assert "新开做T将被拒绝" not in quotes
        assert "次数已用尽，禁止再卖" in quotes
        _invariants(prompt)

    def test_true_empty_not_told_must_jiancang(self):
        prompt = _engine()._build_prompt(
            _empty_snap(cash="6682.26", nav="6682.26"),
            {"002185": _quote()},
            RiskState.NORMAL,
        )
        hard = _sec(prompt, "硬性约束")
        inst = _instruction(prompt)
        for kw in FORCE:
            assert kw not in inst, kw
        assert "无持仓，无股可卖，禁止发出SELL" in hard
        assert "买入建仓或观望（无持仓）" in _sec(prompt, "今日计划")
        _invariants(prompt)


class TestPlannerLessForce:
    def test_no_must_obey_or_low_print(self):
        llm = FakeLLM()
        planner = Planner(llm)
        mu = MarketUnderstandingOutput(
            date="2026-09-15", market_regime=MarketRegime.LOW_VOL,
            today_risk_level="LOW", today_strategy_preference="CONSERVATIVE",
            today_market_summary="低波动",
        )
        planner.generate(
            "2026-09-15", mu, _snap(), {"002185": _quote()}, ["002185"],
        )
        p = llm.prompt
        assert p is not None
        assert "必须遵守" not in p
        assert "合适低位" not in p
        assert "仓位相对目标是数据" in p
        assert "不要写成必须立刻加仓或减仓" in p
        assert "买入可以是接回" in p
        assert "禁止「卖出300股」" in p
