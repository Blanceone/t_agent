"""decision.v2.26：分钟结论写入当日历史，供下一分钟连贯（数据，非硬指令）。"""
from agent.common.models import ActionType, DecisionItem, DecisionOutput, RiskState
from agent.decision.validator import DecisionValidator, clip_conclusion
from tests.unit.test_prompt_v213 import _engine, _quote, _sec, _snap
from tests.unit.test_prompt_v222 import _invariants


FORCE = (
    "必须照做上一分钟",
    "必须遵守先前结论",
    "禁止改变结论",
)


def _hold_out(conclusion="此时卖是杀跌，等较昨收偏高再卖"):
    return DecisionOutput(
        thought_process="...",
        decisions=[DecisionItem(
            action=ActionType.HOLD, code="002185", shares=0,
            confidence=0.75, reason="开盘杀跌不卖", risk_level="LOW",
        )],
        minute_conclusion=conclusion,
    )


class TestClipConclusion:
    def test_strips_and_caps(self):
        assert clip_conclusion("  a   b  ") == "a b"
        long = "x" * 90
        out = clip_conclusion(long)
        assert len(out) <= 81
        assert out.endswith("…")

    def test_empty(self):
        assert clip_conclusion("") == ""
        assert clip_conclusion(None) == ""


class TestPriorConclusionPrompt:
    def test_first_minute_empty(self):
        prompt = _engine()._build_prompt(
            _snap(), {"002185": _quote()}, RiskState.NORMAL)
        prior = _sec(prompt, "今日先前结论")
        assert "无（开盘后尚未记录）" in prior
        assert "不是硬指令" in prior
        assert "可以改变结论" in prior
        assert "minute_conclusion" in prompt
        assert "不是必须执行的硬指令" in prompt
        for kw in FORCE:
            assert kw not in prompt
        _invariants(prompt)

    def test_next_minute_sees_last_conclusion(self):
        engine = _engine()
        engine._remember_conclusion(_hold_out())
        prompt = engine._build_prompt(
            _snap(), {"002185": _quote()}, RiskState.NORMAL)
        prior = _sec(prompt, "今日先前结论")
        assert "无（开盘后尚未记录）" not in prior
        assert "HOLD 002185：此时卖是杀跌，等较昨收偏高再卖" in prior
        for kw in FORCE:
            assert kw not in prompt
        _invariants(prompt)

    def test_missing_field_falls_back_to_reason(self):
        engine = _engine()
        engine._remember_conclusion(DecisionOutput(
            thought_process="",
            decisions=[DecisionItem(
                action=ActionType.SELL, code="002185", shares=100,
                confidence=0.7, reason="区间90%高抛100股", risk_level="LOW",
            )],
            minute_conclusion="",
        ))
        prompt = engine._build_prompt(
            _snap(), {"002185": _quote()}, RiskState.NORMAL)
        assert "SELL 002185：区间90%高抛100股" in prompt

    def test_day_start_clears(self):
        engine = _engine()
        engine._remember_conclusion(_hold_out())
        engine.set_daily_context(
            ["002185"], engine._today_plan, trading_engine=engine._trading_engine,
        )
        prompt = engine._build_prompt(
            _snap(), {"002185": _quote()}, RiskState.NORMAL)
        assert "无（开盘后尚未记录）" in _sec(prompt, "今日先前结论")
        assert "此时卖是杀跌" not in prompt

    def test_keep_last_30(self):
        engine = _engine()
        for i in range(35):
            engine._remember_conclusion(_hold_out(f"结论{i:02d}"))
        prompt = engine._build_prompt(
            _snap(), {"002185": _quote()}, RiskState.NORMAL)
        prior = _sec(prompt, "今日先前结论")
        assert "结论00" not in prior
        assert "结论04" not in prior
        assert "结论05" in prior
        assert "结论34" in prior

    def test_validator_keeps_missing_field(self):
        out = DecisionValidator().validate({
            "thought_process": "x",
            "decisions": [{
                "action": "HOLD", "code": "002185", "shares": 0,
                "confidence": 0.8, "reason": "wait",
            }],
        })
        assert out is not None
        assert out.minute_conclusion == ""
