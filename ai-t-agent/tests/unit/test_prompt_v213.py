"""decision.v2.13：事实句与禁买原因（不拉行情）。"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from agent.config.schema import AppConfig
from agent.decision.engine import (
    DecisionEngine,
    _buy_unavailable_reason,
    _intraday_lot_note,
    _minutes_until,
    _pct_yuan,
    _session_elapsed_minutes,
)
from agent.decision.planner import Planner, TodayPlan, StockPlan
from agent.common.models import (
    AccountSnapshot, ActionType, FeeDetail, Fill, MarketRegime, Position, Quote, RiskState,
)
from agent.market.understanding import MarketUnderstandingOutput


TZ = timezone(timedelta(hours=8))


class FakeLLM:
    last_error = None

    def __init__(self):
        self.prompt = None

    def call_json(self, prompt, timeout_ms=None):
        self.prompt = prompt
        return {
            "global_bias": "BALANCED",
            "plans": [{
                "code": "002185",
                "trade_plan": "当持有可卖仓位且价格进入你选定的区间时卖出100股",
                "target_position_ratio": 0.25,
                "t_strategy": "SELL_FIRST_THEN_BUY_BACK",
                "risk_level": "MEDIUM",
                "max_trades_hint": 2,
                "notes": "",
            }],
        }


class FakeTrading:
    today_fills = []


def _quote(**kw):
    defaults = dict(
        code="002185", name="华天科技", last=Decimal("16.91"),
        bid1=Decimal("16.90"), ask1=Decimal("16.91"),
        high=Decimal("16.94"), low=Decimal("16.45"),
        open=Decimal("16.91"), pre_close=Decimal("16.84"),
        limit_up=Decimal("18.52"), limit_down=Decimal("15.16"),
        volume=1000000, turnover=Decimal("16800000"), vwap=Decimal("16.71"),
        is_suspended=False, is_st=False,
        timestamp=datetime(2026, 8, 26, 10, 51, tzinfo=TZ),
    )
    defaults.update(kw)
    return Quote(**defaults)


def _snap(cash="6682.26", nav="10064.26", shares=200, sellable=200):
    pos = Position(
        code="002185", total_shares=shares, sellable_shares=sellable,
        today_bought=0, cost_price=Decimal("16.2702"),
        stop_loss_price=Decimal("14.9686"),
    )
    return AccountSnapshot(
        account_id="sim_001", nav_mark=Decimal(nav),
        cash_available=Decimal(cash), peak_nav=Decimal("10127.62"),
        last_nav=Decimal("10050.26"), risk_state=RiskState.NORMAL,
        positions={"002185": pos}, realized_pnl_today=Decimal("0"),
        liquidation_queue=[], snapshot_time=datetime.now(TZ),
    )


def _empty_snap(cash="10117.51", nav="10117.51"):
    return AccountSnapshot(
        account_id="sim_001", nav_mark=Decimal(nav),
        cash_available=Decimal(cash), peak_nav=Decimal("10127.62"),
        last_nav=Decimal("10050.26"), risk_state=RiskState.NORMAL,
        positions={}, realized_pnl_today=Decimal("181.21"),
        liquidation_queue=[], snapshot_time=datetime.now(TZ),
    )


def _engine(max_trades=2):
    engine = DecisionEngine(AppConfig(), FakeLLM())
    plan = TodayPlan(
        date="2026-08-26", market_regime=MarketRegime.RANGE,
        plans=[StockPlan(code="002185", t_strategy="SELL_FIRST_THEN_BUY_BACK",
                         max_trades_hint=max_trades, target_position_ratio=0.25)],
        generated_at="09:20",
        last_at_plan={"002185": Decimal("16.67")},
    )
    engine.set_daily_context(
        ["002185"], plan, market_service=None,
        trading_engine=FakeTrading(), memory_retriever=None,
        regime="RANGE", market_summary="震荡",
    )
    return engine


def _fill(action, shares, price, hour=9, minute=32):
    return Fill(
        fill_id="f1", order_id="o1", code="002185", action=action,
        shares=shares, price=Decimal(str(price)),
        amount=Decimal(str(price)) * shares, fee=Decimal("5"),
        fee_detail=FeeDetail(Decimal("5"), Decimal("0"), Decimal("0")),
        realized_pnl=None,
        timestamp=datetime(2026, 8, 28, hour, minute, tzinfo=TZ),
        tick_id="t",
    )


def _sec(prompt: str, title: str) -> str:
    marker = f"## {title}"
    i = prompt.find(marker)
    if i < 0:
        return ""
    j = prompt.find("\n## ", i + 1)
    return prompt[i:] if j < 0 else prompt[i:j]


OPEN_JIANCANG = (
    "买入建仓或观望（无持仓）",
    "仅可执行计划中的买入建仓部分",
    "请先BUY建仓",
)


class TestIntradayLotNote:
    def test_pending_positive(self):
        assert "未接回100股" in _intraday_lot_note(200, 100, 100)
        assert "未接回-" not in _intraday_lot_note(200, 100, 100)
        assert "今日已卖200股/已买100股" in _intraday_lot_note(200, 100)

    def test_closed_round_trip(self):
        note = _intraday_lot_note(200, 200)
        assert "今日已卖200股/已买200股" in note
        assert "未接回" not in note

    def test_buy_only_not_buyback(self):
        note = _intraday_lot_note(0, 100)
        assert "今日已买100股" in note
        assert "未接回" not in note

    def test_bought_more_than_sold(self):
        note = _intraday_lot_note(200, 300)
        assert "今日已卖200股/已买300股" in note
        assert "未接回" not in note

    def test_no_fills(self):
        assert _intraday_lot_note(0, 0) == ""
        assert _intraday_lot_note(0, 0, 300) == ", 未接回300股"
        note = _intraday_lot_note(0, 100, 200)
        assert "未接回200股" in note
        assert "今日已买100股" in note
        bought = _intraday_lot_note(0, 300, 0, 300)
        assert "今日已买300股" in bought
        assert "未接回" not in bought


class TestBuyUnavailableReason:
    def test_cap_not_cash(self):
        assert "单票上限剩余不足100股" in _buy_unavailable_reason(275, 97)
        assert "购买力不足" not in _buy_unavailable_reason(275, 97)

    def test_cash_not_cap(self):
        assert "购买力不足" in _buy_unavailable_reason(50, 400)
        assert "单票上限" not in _buy_unavailable_reason(50, 400)


class TestPctYuan:
    def test_open_distance(self):
        s = _pct_yuan(Decimal("16.66"), Decimal("16.91"), "今开")
        assert s is not None
        assert "较今开" in s and "元）" in s


class TestMinutesUntil:
    def test_before_suspend(self):
        now = datetime(2026, 8, 27, 14, 0, tzinfo=TZ)
        assert _minutes_until(now, "14:57") == 57


class TestSessionElapsed:
    def test_open_plus_two(self):
        now = datetime(2026, 8, 28, 9, 32, tzinfo=TZ)
        assert _session_elapsed_minutes(now, "09:30", "11:30", "13:00") == 2

    def test_lunch_counts_morning_only(self):
        now = datetime(2026, 8, 28, 12, 0, tzinfo=TZ)
        assert _session_elapsed_minutes(now, "09:30", "11:30", "13:00") == 120

    def test_afternoon(self):
        now = datetime(2026, 8, 28, 13, 10, tzinfo=TZ)
        assert _session_elapsed_minutes(now, "09:30", "11:30", "13:00") == 130


class TestDecisionPromptV214:
    def test_plan_is_reference_and_calc_present(self):
        prompt = _engine()._build_prompt(
            _snap(), {"002185": _quote()}, RiskState.NORMAL)
        assert "当前可执行步骤：卖出" not in prompt
        assert "若本分钟交易，只允许SELL" not in prompt
        assert "不是本分钟必须命中的绝对成交价" in prompt
        assert "不要把「现价高于/低于计划价」当成禁止买卖的条件" in prompt
        assert "计划生成于09:20" in prompt
        assert "较计划时" in prompt
        assert "较今开" in prompt
        assert "自日内最低回升" in prompt
        assert "现金不足或已达仓位上限" not in prompt
        assert "未接回不是买入上限" in prompt
        assert "先卖后买必须跨分钟顺序执行" not in prompt
        assert "可以跨分钟分批买卖" in prompt
        assert "买入按卖一成交" in prompt
        assert "买一" in prompt and "卖一" in prompt
        assert "购买力" in prompt and "已扣现金预留" in prompt
        assert "停止下单" in prompt
        assert "最多可买" in prompt
        assert "不等于禁止买入" in prompt
        assert "示例中的100只是字段占位" in prompt
        assert "振幅" in prompt
        assert "今开较昨收" in prompt
        assert "往返费用约" in prompt
        assert "元/股）" in prompt
        assert "元/股打平" not in prompt

    def test_overweight_cap_reason(self):
        prompt = _engine()._build_prompt(
            _snap(), {"002185": _quote()}, RiskState.NORMAL)
        assert "单票上限剩余不足100股" not in prompt
        assert "最多可买" in prompt
        assert "现金不足或已达仓位上限" not in prompt

    def test_partial_sell_allows_buyback_next_minute(self):
        from agent.common.models import ActionType, Fill, FeeDetail
        fill = Fill(
            fill_id="f1", order_id="o1", code="002185", action=ActionType.SELL,
            shares=100, price=Decimal("16.93"), amount=Decimal("1693"),
            fee=Decimal("5"),
            fee_detail=FeeDetail(Decimal("5"), Decimal("0"), Decimal("0")),
            realized_pnl=None, timestamp=datetime(2026, 8, 26, 10, 41, tzinfo=TZ),
            tick_id="t",
        )
        engine = _engine()
        engine._trading_engine = type("T", (), {"today_fills": [fill]})()
        prompt = engine._build_prompt(
            _snap(shares=100, sellable=100, nav="10080"),
            {"002185": _quote(last=Decimal("16.60"), ask1=Decimal("16.60"))},
            RiskState.NORMAL,
        )
        assert "未接回100股" in prompt
        assert "若本分钟交易，只允许SELL" not in prompt
        assert "买入须等卖出成交后的后续分钟" not in prompt
        assert "同一分钟只能选一个方向" in prompt or "同一标的同一分钟只能输出一个方向" in prompt

    def test_flatten_is_buyback_not_jiancang(self):
        from agent.common.models import ActionType, Fill, FeeDetail
        fill = Fill(
            fill_id="f1", order_id="o1", code="002185", action=ActionType.SELL,
            shares=200, price=Decimal("17.21"), amount=Decimal("3442"),
            fee=Decimal("6.75"),
            fee_detail=FeeDetail(Decimal("6.75"), Decimal("0"), Decimal("0")),
            realized_pnl=None, timestamp=datetime(2026, 8, 28, 9, 32, tzinfo=TZ),
            tick_id="t",
        )
        engine = _engine()
        engine._trading_engine = type("T", (), {"today_fills": [fill]})()
        prompt = engine._build_prompt(
            _empty_snap(),
            {"002185": _quote(last=Decimal("17.32"), ask1=Decimal("17.32"),
                              bid1=Decimal("17.31"))},
            RiskState.NORMAL,
        )
        assert "未接回200股" in prompt
        assert "今日卖出均价17.21" in prompt or "卖出均价17.21" in prompt
        assert "较今日卖出均价" in prompt or "较卖出均价" in prompt
        assert "买入是接回该笔做T，不是建仓" not in prompt
        assert "可买或观望" in prompt
        assert "仅可执行计划中的买入建仓部分" not in prompt
        assert "如需重新参与请先BUY建仓" not in prompt
        assert "买入建仓或观望（无持仓）" not in prompt
        assert "持仓0股" in prompt and "可卖0股" in prompt
        assert "## 持仓\n无持仓" not in prompt
        hold = _sec(prompt, "持仓")
        hard = _sec(prompt, "硬性约束")
        plan = _sec(prompt, "今日计划")
        quotes = _sec(prompt, "股票池行情")
        role = hold + hard + plan + quotes
        for kw in OPEN_JIANCANG:
            assert kw not in role
        assert "无持仓，无股可卖，禁止发出SELL" in hard
        assert "仓位比例相对目标" in prompt
        assert "不是减仓或卖出的硬指令" in prompt

    def test_true_empty_still_jiancang(self):
        prompt = _engine()._build_prompt(
            _empty_snap(cash="6682.26", nav="6682.26"),
            {"002185": _quote()},
            RiskState.NORMAL,
        )
        assert "无持仓，无股可卖，禁止发出SELL" in prompt
        assert "仅可执行计划中的买入建仓部分" not in prompt
        assert "买入建仓或观望（无持仓）" in prompt
        assert "未接回200股" not in prompt
        assert "002185 今日已卖" not in prompt
        assert "## 持仓\n无持仓" in prompt


class TestRoleKeywordMatrix:
    """正向路径必须出现的词 vs 逆向不得串台的词。"""

    def test_held_sellable_not_must_sell(self):
        prompt = _engine()._build_prompt(
            _snap(), {"002185": _quote()}, RiskState.NORMAL)
        plan = _sec(prompt, "今日计划")
        hard = _sec(prompt, "硬性约束")
        assert "可卖200股" in plan
        assert "当前可执行步骤：卖出" not in prompt
        assert "若本分钟交易，只允许SELL" not in prompt
        assert "必须卖" not in prompt
        assert "买入建仓或观望（无持仓）" not in plan
        assert "仓位比例相对目标" in prompt
        assert "不是减仓或卖出的硬指令" in prompt
        assert "最多可买" in hard
        assert "单票上限剩余不足100股，禁止加仓BUY" not in hard
        assert "不等于禁止买入" in prompt

    def test_partial_sell_can_buyback_or_sell(self):
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
        assert "若本分钟交易，只允许SELL" not in prompt
        assert "买入建仓或观望（无持仓）" not in plan
        for kw in OPEN_JIANCANG:
            assert kw not in _sec(prompt, "硬性约束") + plan + hold

    def test_t1_after_closed_round_trip(self):
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
        plan = _sec(prompt, "今日计划")
        hold = _sec(prompt, "持仓")
        hard = _sec(prompt, "硬性约束")
        assert "禁止发出SELL（T+1锁定）" in prompt
        assert "HOLD（T+1不可卖）" in plan
        assert "今日已卖200股/已买200股" in hold
        assert "未接回" not in hold
        assert "买入建仓或观望（无持仓）" not in plan
        assert "买入是接回该笔做T，不是建仓" not in hard
        for kw in OPEN_JIANCANG:
            assert kw not in hard + plan + hold

    def test_budget_done_pending_is_buyback_only(self):
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
        plan = _sec(prompt, "今日计划")
        hold = _sec(prompt, "持仓")
        assert "仍可BUY" in hard
        assert "禁止发出SELL" in hard
        assert "禁止发出SELL和新建仓BUY" not in hard
        assert "完成本次做T" not in hard
        assert "仅允许接回BUY" not in hard
        assert "可买或观望" in plan
        assert "接回买入（未接回200股）" not in plan
        assert "买入建仓部分" not in hard
        assert "买入建仓或观望（无持仓）" not in plan
        assert "## 持仓\n无持仓" not in prompt
        assert "持仓0股" in hold
        for kw in OPEN_JIANCANG:
            assert kw not in hard + plan + hold

    def test_buy_only_is_not_pending_buyback(self):
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
        plan = _sec(prompt, "今日计划")
        assert "今日已买100股" in hold
        assert "未接回" not in hold
        assert "接回已闭环" not in hold
        assert "买入是接回该笔做T，不是建仓" not in hard
        assert "未接回不是买入上限" in prompt
        assert "买入建仓或观望（无持仓）" not in plan

    def test_bought_over_sold_is_closed_not_negative_pending(self):
        engine = _engine()
        engine._trading_engine = type("T", (), {
            "today_fills": [
                _fill(ActionType.SELL, 200, "17.21", 9, 32),
                _fill(ActionType.BUY, 300, "16.49", 10, 33),
            ],
        })()
        prompt = engine._build_prompt(
            _snap(shares=300, sellable=100, cash="5000.72", nav="9956.72"),
            {"002185": _quote(last=Decimal("16.52"), ask1=Decimal("16.52"))},
            RiskState.NORMAL,
        )
        hold = _sec(prompt, "持仓")
        assert "今日已卖200股/已买300股" in hold
        assert "未接回" not in hold

    def test_true_empty_jiancang_not_buyback(self):
        prompt = _engine()._build_prompt(
            _empty_snap(cash="6682.26", nav="6682.26"),
            {"002185": _quote()},
            RiskState.NORMAL,
        )
        hold = _sec(prompt, "持仓")
        hard = _sec(prompt, "硬性约束")
        plan = _sec(prompt, "今日计划")
        assert hold.strip() == "## 持仓\n无持仓"
        assert "无持仓，无股可卖，禁止发出SELL" in hard
        assert "仅可执行计划中的买入建仓部分" not in hard
        assert "买入建仓或观望（无持仓）" in plan
        assert "今日卖出均价" not in hold
        assert "未接回200股" not in prompt
        assert "买入是接回该笔做T，不是建仓" not in hard


class TestPlannerPromptV13:
    def test_relative_price_not_frozen_band(self):
        llm = FakeLLM()
        planner = Planner(llm)
        q = _quote()
        snap = _snap()
        mu = MarketUnderstandingOutput(
            date="2026-08-26", market_regime=MarketRegime.RANGE,
            today_risk_level="MEDIUM", today_strategy_preference="BALANCED",
            today_market_summary="震荡",
        )
        plan = planner.generate(
            "2026-08-26", mu, snap, {"002185": q}, ["002185"],
        )
        p = llm.prompt
        assert p is not None
        assert "连续竞价尚未开始" in p
        assert "不要把这些数写成全日绝对成交价" in p
        assert "价格条件写相对关系" in p
        assert "不要输出 fen 级绝对触发价" in p
        assert "触发价格区间" not in p
        assert "写成有上下沿的区间" not in p
        assert "今开" in p and "日内均价" in p
        assert "尚未形成日内含义" in p
        assert "不得超过上方「最大做T次数」" in p
        assert "反弹至压力位/MA5附近时卖出" not in p
        assert "回调至支撑/MA20附近时买入" not in p
        assert "不指定必须使用均线" in p
        assert "不要写「卖在偏高一侧」" in p
        assert "买入可以是接回、加仓或建仓" in p
        assert "卖在当日偏高一侧" not in p
        assert "接回低于卖出价" not in p
        assert "不要写死持仓/可卖/未接回的全部股数" in p
        assert "禁止「卖出300股」" in p
        assert "未接回不是买入上限" in p
        assert "每笔卖出占1次" in p
        assert "不要因此要求一次卖光或必须分批" in p
        assert "不要把 max_trades_hint 写成 0" in p
        assert "0 不等于次数已满" in p
        assert "空仓时不要全日禁止买入" in p
        assert "若已达目标仓位，计划中不得再包含买入动作" not in p
        assert plan.last_at_plan.get("002185") == q.last
        assert plan.generated_at


class TestMuSummaryDataOnly:
    def test_overwrites_llm_advice(self):
        from agent.market.understanding import MarketUnderstandingEngine

        class LLM:
            last_error = None

            def __init__(self):
                self.prompt = None

            def call_json(self, prompt, timeout_ms=None):
                self.prompt = prompt
                return {
                    "market_regime": "LOW_VOL",
                    "today_risk_level": "LOW",
                    "today_trading_suggestion": "REDUCE_T",
                    "today_strategy_preference": "CONSERVATIVE",
                    "today_market_summary": "建议减少做T频率，控制仓位，等待方向选择",
                    "confidence": 0.8,
                }

        llm = LLM()
        out = MarketUnderstandingEngine(llm).run(
            "2026-08-27", {"002185": _quote()}, ["002185"])
        assert "建议" not in out.today_market_summary
        assert "控制仓位" not in out.today_market_summary
        assert "指数涨跌" in out.today_market_summary
        assert "量比" in out.today_market_summary
        assert llm.prompt is not None
        assert "不要写操作建议" in llm.prompt


class TestQuoteFeatureHelpers:
    def test_path_10m_high_first(self):
        from agent.market.service import path_10m_label, avg_volume_5d_shares
        assert path_10m_label([10, 12, 11, 9, 9.5]) == "近10分钟高点早于低点"
        assert path_10m_label([10, 8, 9, 12, 11]) == "近10分钟低点早于高点"
        bars = [
            {"date": "2026-08-20", "volume": 1000},
            {"date": "2026-08-21", "volume": 1000},
            {"date": "2026-08-24", "volume": 1000},
            {"date": "2026-08-25", "volume": 1000},
            {"date": "2026-08-26", "volume": 1000},
            {"date": "2026-08-27", "volume": 99999},
        ]
        # 均量 1000手 = 100000股，不含当天
        assert avg_volume_5d_shares(bars, "20260827") == 100000.0

