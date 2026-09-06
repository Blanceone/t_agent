"""冒烟测试：验证 decision.v2.9 Prompt（浮动盈亏/仓位比例/预算剩余 预计算）"""
import sys
sys.path.insert(0, "src")

from decimal import Decimal
from agent.config.schema import AppConfig
from agent.market.service import MarketService
from agent.decision.engine import DecisionEngine
from agent.decision.planner import TodayPlan, StockPlan
from agent.common.models import RiskState, MarketRegime, Position
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
    today_fills = []


def build_prompt(with_position: bool) -> str:
    engine = DecisionEngine(config, FakeLLM())
    plan = TodayPlan(
        date="2026-08-24", market_regime=MarketRegime.RANGE,
        plans=[StockPlan(code="002185", t_strategy="SELL_FIRST_THEN_BUY_BACK",
                         max_trades_hint=3, target_position_ratio=0.25)],
    )
    engine.set_daily_context(["002185"], plan, market,
                             trading_engine=FakeTrading(), memory_retriever=None,
                             regime="RANGE", market_summary="震荡市")
    snap = Account(initial_cash=Decimal("10000")).snapshot(quotes)
    if with_position:
        snap.positions["002185"] = Position(
            code="002185", total_shares=200, sellable_shares=200,
            today_bought=0, cost_price=Decimal("17.20"),
            stop_loss_price=Decimal("15.82"),
        )
    return engine._build_prompt(snap, quotes, RiskState.NORMAL)


checks = []

# 持仓场景：三项预计算
p_hold = build_prompt(with_position=True)
hold_line = next((l for l in p_hold.splitlines() if l.startswith("- 002185") and "持仓" in l), "")
checks.append(("持仓行含浮动盈亏(元)", "浮动盈亏" in hold_line and "元" in hold_line))
checks.append(("持仓行含盈亏比例%", hold_line.count("%") >= 2))
checks.append(("持仓行含仓位比例", "仓位比例" in hold_line))
checks.append(("持仓行含目标仓位", "目标25.0%" in hold_line))
checks.append(("持仓行保留风控线距离", "现价距风控线" in hold_line))

# 数值正确性抽查（浮动盈亏方向：现价>成本应为+）
q = quotes["002185"]
expect_sign = "+" if q.last > Decimal("17.20") else "-"
checks.append((f"浮动盈亏符号正确(现价{q.last} vs 成本17.20)",
               f"浮动盈亏{expect_sign}" in hold_line))

# 计划区块：剩余笔数
plan_line = next((l for l in p_hold.splitlines() if "已交易0笔/上限3笔" in l), "")
checks.append(("计划行含剩余笔数", "（剩余3笔）" in plan_line))

# 空仓场景：不回归
p_flat = build_prompt(with_position=False)
checks.append(("空仓: v2.8注入仍在", "计划中的卖出步骤不可执行" in p_flat))
checks.append(("空仓: 预计算行仍在", "预计算:" in p_flat))
checks.append(("版本号 v2.9", config.prompt.decision_version == "decision.v2.9"))

print("=" * 50)
ok = True
for name, passed in checks:
    print(f"[{'OK' if passed else 'FAIL'}] {name}")
    ok = ok and passed
print("=" * 50)
print("持仓行示例:", hold_line)
print("计划行示例:", plan_line)
print("全部通过" if ok else "存在失败项")
sys.exit(0 if ok else 1)
