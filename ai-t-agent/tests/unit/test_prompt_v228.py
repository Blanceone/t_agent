"""decision.v2.28：推理前先对照今日历史；认真对待，不是必须照做。"""
from agent.common.models import RiskState
from tests.unit.test_prompt_v213 import _engine, _quote, _sec, _snap
from tests.unit.test_prompt_v222 import _invariants
from tests.unit.test_prompt_v226 import FORCE as NO_STICKY, _hold_out


WEIGHT = (
    "开始本分钟推理前，先读",
    "对照自己已经写下的判断",
    "事实未变时不要无故推翻",
    "thought_process 先对照今日先前结论与已成交",
    "推理前先读",
    "推理前先看",
)


class TestHistoryWeight:
    def test_instructs_read_history_before_reasoning(self):
        prompt = _engine()._build_prompt(
            _snap(), {"002185": _quote()}, RiskState.NORMAL)
        prior = _sec(prompt, "今日先前结论")
        fills = _sec(prompt, "今日已成交")
        for s in WEIGHT:
            assert s in prompt, s
        assert "不是必须执行的硬指令" in prompt
        assert "可以改变结论" in prior
        assert "不是硬指令" in prior
        assert "推理前先看" in fills
        for kw in NO_STICKY:
            assert kw not in prompt, kw
        _invariants(prompt)

    def test_next_minute_still_sees_last(self):
        engine = _engine()
        engine._remember_conclusion(_hold_out())
        prompt = engine._build_prompt(
            _snap(), {"002185": _quote()}, RiskState.NORMAL)
        prior = _sec(prompt, "今日先前结论")
        assert "HOLD 002185：此时卖是杀跌，等较昨收偏高再卖" in prior
        assert "推理前先读" in prior
        for kw in NO_STICKY:
            assert kw not in prompt
        _invariants(prompt)
