"""decision.v2.22 / planner.v1.6：手数与次数口径，多场景自洽。"""
from decimal import Decimal

from agent.common.models import ActionType, Quote, RiskState
from agent.decision.planner import StockPlan, TodayPlan
from tests.unit.test_prompt_v213 import (
    OPEN_JIANCANG,
    TZ,
    FakeTrading,
    _engine,
    _fill,
    _quote,
    _sec,
    _snap,
    _empty_snap,
)


MUST_SELL = ("必须卖", "当前可执行步骤：卖出", "若本分钟交易，只允许SELL")
LOT_FREE = (
    "可以小于可卖或未接回全部",
    "也可以等于全部可卖",
    "不是必须一次做完的手数",
    "不必等于可卖全部或未接回全部",
)
NEG_PENDING = ("未接回-", "未接回−")


def _q918(**kw):
    defaults = dict(
        code="601918", name="新集能源", last=Decimal("10.71"),
        bid1=Decimal("10.70"), ask1=Decimal("10.71"),
        high=Decimal("10.74"), low=Decimal("10.40"),
        open=Decimal("10.71"), pre_close=Decimal("10.63"),
        limit_up=Decimal("11.69"), limit_down=Decimal("9.57"),
        volume=800000, turnover=Decimal("8500000"), vwap=Decimal("10.60"),
        is_suspended=False, is_st=False,
        timestamp=_quote().timestamp,
    )
    defaults.update(kw)
    return Quote(**defaults)


def _engine_strat(strategy, max_trades=2, codes=None, plans=None):
    codes = codes or ["002185"]
    engine = _engine(max_trades=max_trades)
    if plans is None:
        plans = [
            StockPlan(
                code=c, t_strategy=strategy, max_trades_hint=max_trades,
                target_position_ratio=0.25,
                trade_plan="当条件满足时卖出不超过可卖；回落则接回不超过未接回",
            )
            for c in codes
        ]
    engine._today_plan = TodayPlan(
        date="2026-09-04", market_regime=engine._today_plan.market_regime,
        plans=plans, generated_at="09:20",
        last_at_plan={c: Decimal("16.05") for c in codes if c == "002185"}
        | {c: Decimal("10.57") for c in codes if c == "601918"},
        global_bias="BALANCED",
    )
    engine._watchlist = list(codes)
    engine._trading_engine = FakeTrading()
    return engine


def _role(prompt):
    return (
        _sec(prompt, "持仓")
        + _sec(prompt, "硬性约束")
        + _sec(prompt, "今日计划")
        + _sec(prompt, "股票池行情")
    )


def _invariants(prompt):
    hold = _sec(prompt, "持仓")
    for bad in NEG_PENDING:
        assert bad not in hold
    assert "未接回0股" not in hold
    assert "仓位比例相对目标" in prompt
    assert "不是减仓或卖出的硬指令" in prompt
    assert "可以跨分钟分批买卖" in prompt
    for s in LOT_FREE:
        assert s in prompt
    assert "示例中的100只是字段占位" in prompt
    for s in MUST_SELL:
        assert s not in prompt


class TestLotAndTimesWording:
    def test_sell_first_times_note(self):
        prompt = _engine(max_trades=1)._build_prompt(
            _snap(), {"002185": _quote()}, RiskState.NORMAL)
        plan = _sec(prompt, "今日计划")
        assert "每笔SELL占1次，分批各计1次" in plan
        assert "接回买入不计入" in plan
        _invariants(prompt)

    def test_buy_first_no_sell_count_note(self):
        engine = _engine_strat("BUY_FIRST_THEN_SELL")
        prompt = engine._build_prompt(
            _snap(), {"002185": _quote()}, RiskState.NORMAL)
        plan = _sec(prompt, "今日计划")
        assert "策略=BUY_FIRST_THEN_SELL" in plan
        assert "每笔SELL占1次" not in plan
        _invariants(prompt)

    def test_wait_no_sell_count_note(self):
        engine = _engine_strat("WAIT")
        prompt = engine._build_prompt(
            _empty_snap(cash="6682.26", nav="6682.26"),
            {"002185": _quote()}, RiskState.NORMAL)
        plan = _sec(prompt, "今日计划")
        assert "策略=WAIT" in plan
        assert "每笔SELL占1次" not in plan
        assert "买入建仓或观望（无持仓）" in plan


class TestScenarioMatrix:
    """账户角色矩阵：建仓 / 接回 / 加仓 / 闭环 不得串台。"""

    def test_held_sellable_not_must_flatten(self):
        prompt = _engine()._build_prompt(
            _snap(), {"002185": _quote()}, RiskState.NORMAL)
        plan = _sec(prompt, "今日计划")
        hold = _sec(prompt, "持仓")
        assert "可卖200股" in plan
        assert "买入建仓或观望（无持仓）" not in plan
        assert "未接回" not in hold
        assert "本次股数不必等于可卖全部" in prompt
        for kw in OPEN_JIANCANG:
            assert kw not in _role(prompt)
        _invariants(prompt)

    def test_partial_sell_pending(self):
        engine = _engine()
        engine._trading_engine = type("T", (), {
            "today_fills": [_fill(ActionType.SELL, 100, "16.93")],
        })()
        prompt = engine._build_prompt(
            _snap(shares=100, sellable=100, nav="10080"),
            {"002185": _quote(last=Decimal("16.60"), ask1=Decimal("16.60"))},
            RiskState.NORMAL,
        )
        hold = _sec(prompt, "持仓")
        plan = _sec(prompt, "今日计划")
        assert "未接回100股" in hold
        assert "可卖100股" in plan
        assert "接回已闭环" not in hold
        for kw in OPEN_JIANCANG:
            assert kw not in _role(prompt)
        _invariants(prompt)

    def test_flatten_buyback_not_jiancang(self):
        engine = _engine()
        engine._trading_engine = type("T", (), {
            "today_fills": [_fill(ActionType.SELL, 300, "16.27")],
        })()
        prompt = engine._build_prompt(
            _empty_snap(),
            {"002185": _quote(last=Decimal("16.18"), ask1=Decimal("16.18"))},
            RiskState.NORMAL,
        )
        hold = _sec(prompt, "持仓")
        hard = _sec(prompt, "硬性约束")
        plan = _sec(prompt, "今日计划")
        assert "持仓0股" in hold and "未接回300股" in hold
        assert "今日卖出均价16.27" in hold
        assert "买入是接回该笔做T，不是建仓" in hard
        assert "接回买入（未接回300股）" in plan
        assert "## 持仓\n无持仓" not in prompt
        for kw in OPEN_JIANCANG:
            assert kw not in _role(prompt)
        _invariants(prompt)

    def test_closed_round_trip_t1(self):
        engine = _engine(max_trades=1)
        engine._trading_engine = type("T", (), {
            "today_fills": [
                _fill(ActionType.SELL, 300, "16.27", 9, 37),
                _fill(ActionType.BUY, 300, "16.18", 9, 41),
            ],
        })()
        prompt = engine._build_prompt(
            _snap(shares=300, sellable=0, nav="9845.18", cash="5015.18"),
            {"002185": _quote(last=Decimal("16.11"), ask1=Decimal("16.11"))},
            RiskState.NORMAL,
        )
        hold = _sec(prompt, "持仓")
        plan = _sec(prompt, "今日计划")
        hard = _sec(prompt, "硬性约束")
        assert "接回已闭环" in hold
        assert "未接回" not in hold
        assert "HOLD（做T次数已满）" in plan or "HOLD（T+1不可卖）" in plan
        assert "买入是接回该笔做T，不是建仓" not in hard
        assert "停止交易只可HOLD" in hard
        for kw in OPEN_JIANCANG:
            assert kw not in _role(prompt)
        _invariants(prompt)

    def test_buy_only_is_add_not_buyback(self):
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
        hard = _sec(prompt, "硬性约束")
        assert "今日已买100股（今日无卖出，不是接回）" in hold
        assert "未接回" not in hold
        assert "买入是接回该笔做T，不是建仓" not in hard
        _invariants(prompt)

    def test_true_empty_jiancang(self):
        prompt = _engine()._build_prompt(
            _empty_snap(cash="6682.26", nav="6682.26"),
            {"002185": _quote()},
            RiskState.NORMAL,
        )
        hold = _sec(prompt, "持仓")
        hard = _sec(prompt, "硬性约束")
        plan = _sec(prompt, "今日计划")
        assert hold.strip() == "## 持仓\n无持仓"
        assert "仅可执行计划中的买入建仓部分" in hard
        assert "买入建仓或观望（无持仓）" in plan
        assert "买入是接回该笔做T，不是建仓" not in hard
        assert "未接回" not in hold
        _invariants(prompt)

    def test_two_names_flatten_and_empty_not_crosstalk(self):
        engine = _engine_strat(
            "SELL_FIRST_THEN_BUY_BACK",
            codes=["002185", "601918"],
            plans=[
                StockPlan(
                    code="002185", t_strategy="SELL_FIRST_THEN_BUY_BACK",
                    max_trades_hint=1, target_position_ratio=0.25,
                    trade_plan="当持有可卖仓位且较昨收冲高时卖出不超过可卖",
                ),
                StockPlan(
                    code="601918", t_strategy="WAIT",
                    max_trades_hint=1, target_position_ratio=0.25,
                    trade_plan="无持仓时观望或满足条件买入建仓",
                ),
            ],
        )
        engine._trading_engine = type("T", (), {
            "today_fills": [_fill(ActionType.SELL, 300, "16.27")],
        })()
        prompt = engine._build_prompt(
            _empty_snap(),
            {
                "002185": _quote(last=Decimal("16.18"), ask1=Decimal("16.18")),
                "601918": _q918(),
            },
            RiskState.NORMAL,
        )
        hold = _sec(prompt, "持仓")
        hard = _sec(prompt, "硬性约束")
        plan = _sec(prompt, "今日计划")
        assert "002185" in hold and "未接回300股" in hold
        assert "买入是接回该笔做T，不是建仓" in hard
        assert "601918 无持仓" in hard
        assert "601918" in plan and "买入建仓或观望（无持仓）" in plan
        assert "002185" in plan and "接回买入（未接回300股）" in plan
        assert "每笔SELL占1次" in plan
        # 空仓票不得吃到接回句；清仓票不得吃到建仓句
        lines_185 = [ln for ln in (hard + plan).splitlines() if "002185" in ln]
        lines_918 = [ln for ln in (hard + plan).splitlines() if "601918" in ln]
        blob_185 = "\n".join(lines_185)
        blob_918 = "\n".join(lines_918)
        assert "买入建仓或观望（无持仓）" not in blob_185
        assert "接回买入（未接回" not in blob_918
        assert "买入是接回该笔做T" not in blob_918
        _invariants(prompt)

    def test_held_plus_empty_open(self):
        engine = _engine_strat(
            "SELL_FIRST_THEN_BUY_BACK",
            codes=["002185", "601918"],
            plans=[
                StockPlan(
                    code="002185", t_strategy="SELL_FIRST_THEN_BUY_BACK",
                    max_trades_hint=1, target_position_ratio=0.25,
                    trade_plan="当持有可卖仓位且较昨收冲高时卖出不超过可卖",
                ),
                StockPlan(
                    code="601918", t_strategy="WAIT",
                    max_trades_hint=2, target_position_ratio=0.25,
                    trade_plan="无持仓时观望或满足条件买入建仓",
                ),
            ],
        )
        prompt = engine._build_prompt(
            _snap(),
            {"002185": _quote(), "601918": _q918()},
            RiskState.NORMAL,
        )
        plan = _sec(prompt, "今日计划")
        hard = _sec(prompt, "硬性约束")
        assert "可卖200股" in plan
        assert "601918" in plan and "买入建仓或观望（无持仓）" in plan
        assert "002185 无持仓" not in hard
        assert "601918 无持仓" in hard
        lines_185 = [ln for ln in plan.splitlines() if ln.startswith("- 002185")]
        assert lines_185 and "买入建仓或观望（无持仓）" not in lines_185[0]
        assert "每笔SELL占1次" in "".join(lines_185)
        lines_918 = [ln for ln in plan.splitlines() if ln.startswith("- 601918")]
        assert lines_918 and "每笔SELL占1次" not in lines_918[0]
        _invariants(prompt)


class TestBudgetIsolation:
    def test_one_sell_uses_one_t_remaining_zero_if_max_one(self):
        engine = _engine(max_trades=1)
        engine._trading_engine = type("T", (), {
            "today_fills": [_fill(ActionType.SELL, 100, "16.27")],
        })()
        prompt = engine._build_prompt(
            _snap(shares=200, sellable=200, nav="10080"),
            {"002185": _quote(last=Decimal("16.18"), ask1=Decimal("16.18"))},
            RiskState.NORMAL,
        )
        plan = _sec(prompt, "今日计划")
        hard = _sec(prompt, "硬性约束")
        assert "今日已做T 1次/上限1次" in plan
        assert "仅允许接回BUY" in hard
        assert "未接回100股" in _sec(prompt, "持仓")
        # 次数用尽仍允许接回，不要求把剩余可卖再卖掉
        assert "必须卖" not in prompt
        _invariants(prompt)
