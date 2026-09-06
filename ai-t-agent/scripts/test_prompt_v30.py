"""冒烟测试：验证 decision.v2.10 Prompt（T+1计划失配注入 / 做T次数按卖出计 / 跨分钟做T）"""
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


def make_engine(fills=None):
    engine = DecisionEngine(config, FakeLLM())
    plan = TodayPlan(
        date="2026-08-25", market_regime=MarketRegime.RANGE,
        plans=[StockPlan(code="002185", t_strategy="SELL_FIRST_THEN_BUY_BACK",
                         max_trades_hint=2, target_position_ratio=0.25)],
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


checks = []

# --- 场景A：T+1 锁仓（8/24 买回后）---
engine_a = make_engine()
snap_a = Account(initial_cash=Decimal("10000")).snapshot(quotes)
snap_a.positions["002185"] = locked_pos()
prompt_a = engine_a._build_prompt(snap_a, quotes, RiskState.NORMAL)
ha = hard_block(prompt_a)
checks.append(("A: T+1 含计划卖出步骤不可执行",
               "计划中的卖出步骤不可执行" in ha and "T+1锁定" in ha))
checks.append(("A: 仍禁止发出SELL", "禁止发出SELL" in ha))

# --- 场景B：空仓 + 先卖后买（v2.8 不回归）---
engine_b = make_engine()
snap_b = Account(initial_cash=Decimal("10000")).snapshot(quotes)
prompt_b = engine_b._build_prompt(snap_b, quotes, RiskState.NORMAL)
hb = hard_block(prompt_b)
checks.append(("B: 空仓 v2.8 注入仍在",
               "无持仓：计划中的卖出步骤不可执行" in hb))

# --- 场景C：2卖+1买 闭环（8/24 口径：应显示 2/2 而非 3/2）---
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
plan_c = next((l for l in prompt_c.splitlines() if "002185" in l and "已做T" in l), "")
checks.append(("C: 计划行按卖出计 2/2", "已做T 2次/上限2次" in plan_c))
checks.append(("C: 剩余0且注明接回不计入", "剩余0次" in plan_c and "接回买入不计入" in plan_c))
checks.append(("C: 不出现 3笔/2笔 口径", "已交易3笔" not in prompt_c and "上限2笔" not in prompt_c))
checks.append(("C: 闭环后停交按次数", "做T已完成2次" in hc and "上限2次" in hc))
checks.append(("C: 闭环后不再走接回例外", "卖出未接回" not in hc))
checks.append(("C: T+1 与预算同时在硬约束", "计划中的卖出步骤不可执行" in hc))

# --- 场景D：1卖未接回、上限1（v2.6 接回例外不回归）---
engine_d = make_engine([mk_fill(ActionType.SELL, 200, 1)])
# 上限改为 1
engine_d._today_plan.plans[0].max_trades_hint = 1
snap_d = Account(initial_cash=Decimal("10000")).snapshot(quotes)
prompt_d = engine_d._build_prompt(snap_d, quotes, RiskState.NORMAL)
hd = hard_block(prompt_d)
checks.append(("D: 未接回允许接回BUY", "卖出未接回" in hd and "接回BUY" in hd))
checks.append(("D: 未接回不走一刀切停交", "停止交易只可HOLD" not in hd))

# --- 规则与版本 ---
checks.append(("规则10 跨分钟", "跨分钟顺序执行" in prompt_a))
checks.append(("规则10 禁止同分钟两腿", "禁止同一分钟同时输出SELL和BUY" in prompt_a))
checks.append(("v2.9 持仓预计算仍在", "浮动盈亏" in prompt_a and "仓位比例" in prompt_a))
checks.append(("版本号 v2.10", config.prompt.decision_version == "decision.v2.10"))

print("=" * 50)
ok = True
for name, passed in checks:
    print(f"[{'OK' if passed else 'FAIL'}] {name}")
    ok = ok and passed
print("=" * 50)
print("--- A 硬约束 ---")
print(ha)
print("计划行C:", plan_c)
print("--- D 硬约束 ---")
print(hd)
print("全部通过" if ok else "存在失败项")
sys.exit(0 if ok else 1)
