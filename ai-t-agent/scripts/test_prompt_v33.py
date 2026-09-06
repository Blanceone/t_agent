"""冒烟测试：decision.v2.13（可执行≠必须卖 / 禁买原因拆开 / 计划为参考 / 预计算今开与回升）"""
import sys
sys.path.insert(0, "src")

from datetime import datetime
from decimal import Decimal
from agent.config.schema import AppConfig
from agent.market.service import MarketService
from agent.decision.engine import DecisionEngine
from agent.decision.planner import TodayPlan, StockPlan
from agent.common.models import (
    ActionType, Fill, FeeDetail, RiskState, MarketRegime, Position,
)
from agent.trading.account import Account

config = AppConfig()
market = MarketService(config)
market.set_watchlist(["002185"])
quotes = market.refresh()
assert quotes, "行情拉取失败"
market._record_intraday(quotes)
market._fetch_index()
try:
    market.refresh_klines()
except Exception as e:
    print("klines失败(不阻塞):", e)


class FakeLLM:
    last_error = None


class FakeTrading:
    def __init__(self, fills=None):
        self.today_fills = fills or []


def mk_fill(action, shares, i):
    return Fill(
        fill_id=f"f{i}", order_id=f"o{i}", code="002185", action=action,
        shares=shares, price=Decimal("17.5"), amount=Decimal("1750"),
        fee=Decimal("5.9"),
        fee_detail=FeeDetail(Decimal("5.9"), Decimal("0"), Decimal("0")),
        realized_pnl=None, timestamp=datetime(2026, 8, 24, 9, 30), tick_id="t",
    )


def make_engine(fills=None, max_trades=2):
    engine = DecisionEngine(config, FakeLLM())
    plan = TodayPlan(
        date="2026-08-27", market_regime=MarketRegime.RANGE,
        plans=[StockPlan(code="002185", t_strategy="SELL_FIRST_THEN_BUY_BACK",
                         max_trades_hint=max_trades, target_position_ratio=0.25)],
    )
    engine.set_daily_context(
        ["002185"], plan, market,
        trading_engine=FakeTrading(fills), memory_retriever=None,
        regime="RANGE", market_summary="低波动",
    )
    return engine


def hard_block(prompt: str) -> str:
    a, b = prompt.find("## 硬性约束"), prompt.find("## 市场环境")
    return prompt[a:b]


def locked_pos():
    return Position(
        code="002185", total_shares=200, sellable_shares=0,
        today_bought=200, cost_price=Decimal("17.18"),
        stop_loss_price=Decimal("15.81"),
    )


def sellable_pos(shares=100):
    return Position(
        code="002185", total_shares=shares, sellable_shares=shares,
        today_bought=0, cost_price=Decimal("17.20"),
        stop_loss_price=Decimal("15.82"),
    )


checks = []

engine_a = make_engine()
snap_a = Account(initial_cash=Decimal("10000")).snapshot(quotes)
snap_a.positions["002185"] = locked_pos()
prompt_a = engine_a._build_prompt(snap_a, quotes, RiskState.NORMAL)
ha = hard_block(prompt_a)
checks.append(("A: T+1 计划卖出步骤不可执行",
               "计划中的卖出步骤不可执行" in ha and "T+1锁定" in ha))

engine_b = make_engine()
prompt_b = engine_b._build_prompt(
    Account(initial_cash=Decimal("10000")).snapshot(quotes), quotes, RiskState.NORMAL)
hb = hard_block(prompt_b)
checks.append(("B: 空仓 v2.8 仍在", "无持仓：计划中的卖出步骤不可执行" in hb))

fills_c = [
    mk_fill(ActionType.SELL, 100, 1),
    mk_fill(ActionType.SELL, 100, 2),
    mk_fill(ActionType.BUY, 200, 3),
]
engine_c = make_engine(fills_c)
snap_c = Account(initial_cash=Decimal("10000")).snapshot(quotes)
snap_c.positions["002185"] = locked_pos()
prompt_c = engine_c._build_prompt(snap_c, quotes, RiskState.NORMAL)
hc = hard_block(prompt_c)
checks.append(("C: 闭环只可HOLD", "停止交易只可HOLD" in hc))
checks.append(("C: 闭环硬约束不再给买入通行证", "最多可买" not in hc))
checks.append(("C: 行情行与硬约束一致禁买", "禁止发出BUY（今日该标的只可HOLD）" in prompt_c))
checks.append(("C: 计划当前可执行=HOLD", "当前可执行=HOLD（做T次数已满）" in prompt_c))
checks.append(("C: 预算仍按卖出计 2/2", "今日已做T 2次/上限2次" in prompt_c))

engine_d = make_engine([mk_fill(ActionType.SELL, 200, 1)], max_trades=1)
prompt_d = engine_d._build_prompt(
    Account(initial_cash=Decimal("10000")).snapshot(quotes), quotes, RiskState.NORMAL)
hd = hard_block(prompt_d)
checks.append(("D: 未接回允许接回BUY", "卖出未接回" in hd and "接回BUY" in hd))
checks.append(("D: 未接回不给通用最多可买", "最多可买" not in hd))

engine_e = make_engine([mk_fill(ActionType.SELL, 100, 1)])
snap_e = Account(initial_cash=Decimal("10000")).snapshot(quotes)
snap_e.positions["002185"] = sellable_pos(100)
prompt_e = engine_e._build_prompt(snap_e, quotes, RiskState.NORMAL)
he = hard_block(prompt_e)
checks.append(("E: 若交易只允许SELL，不是必须卖出",
               "若本分钟交易，只允许SELL（可卖100股），不是必须卖出" in he))
checks.append(("E: 旧句式当前可执行步骤已去掉", "当前可执行步骤：卖出" not in he))
checks.append(("E: 买入须跨分钟", "买入须等卖出成交后的后续分钟" in he))
checks.append(("E: 卖出步骤不再发最多可买通行证", "最多可买" not in he))
checks.append(("E: 行情行买入容量非本分钟通行证",
               "禁止与SELL同时发出BUY" in prompt_e and "本分钟若交易只允许SELL" in prompt_e))
checks.append(("E: 全局同分钟单方向", "只保留当前账户可执行的一条" in he))
checks.append(("E: 计划行不是必须卖出", "不是必须卖出" in prompt_e))
checks.append(("E: 捆在一起的禁买原因已去掉",
               "现金不足或已达仓位上限" not in prompt_e))

checks.append(("预计算含元差", "元）" in prompt_a and "较MA5" in prompt_a))
checks.append(("预计算含较今开", "较今开" in prompt_a))
checks.append(("预计算含自日内最低回升", "自日内最低回升" in prompt_a))
checks.append(("计划降为开盘框架", "不是本分钟必须成交的价格" in prompt_a))
checks.append(("A: T+1 行情行同步禁卖", "禁止发出SELL（T+1锁定）" in prompt_a))
checks.append(("规则10 跨分钟仍在", "跨分钟顺序执行" in prompt_a))
checks.append(("版本号 v2.13", config.prompt.decision_version == "decision.v2.13"))

print("=" * 50)
ok = True
for name, passed in checks:
    print(f"[{'OK' if passed else 'FAIL'}] {name}")
    ok = ok and passed
print("=" * 50)
print("--- C 硬约束 ---")
print(hc)
print("--- E 硬约束 ---")
print(he)
print("全部通过" if ok else "存在失败项")
sys.exit(0 if ok else 1)
