"""冒烟测试：验证 decision.v2.8 Prompt（空仓+先卖后买计划 → 卖出步骤不可执行事实注入）"""
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


def build_prompt(strategy: str, with_position: bool) -> str:
    engine = DecisionEngine(config, FakeLLM())
    plan = TodayPlan(
        date="2026-08-21", market_regime=MarketRegime.RANGE,
        plans=[StockPlan(code="002185", t_strategy=strategy, max_trades_hint=3)],
    )
    engine.set_daily_context(["002185"], plan, market,
                             trading_engine=FakeTrading(), memory_retriever=None,
                             regime="RANGE", market_summary="震荡市")
    snap = Account(initial_cash=Decimal("10000")).snapshot(quotes)
    if with_position:
        snap.positions["002185"] = Position(
            code="002185", total_shares=200, sellable_shares=200,
            today_bought=0, cost_price=Decimal("17.96"),
            stop_loss_price=Decimal("16.0"),
        )
    return engine._build_prompt(snap, quotes, RiskState.NORMAL)


checks = []
KEY = "计划中的卖出步骤不可执行"

# 场景1（核心）：空仓 + SELL_FIRST 计划 → 必须注入事实说明
p1 = build_prompt("SELL_FIRST_THEN_BUY_BACK", with_position=False)
checks.append(("空仓+SELL_FIRST: 注入卖出步骤不可执行", KEY in p1))
checks.append(("空仓+SELL_FIRST: 保留禁止SELL约束", "禁止发出SELL" in p1))

# 场景2：持仓 + SELL_FIRST 计划 → 不注入（有股可卖，计划卖出步骤可执行）
p2 = build_prompt("SELL_FIRST_THEN_BUY_BACK", with_position=True)
checks.append(("持仓+SELL_FIRST: 不注入", KEY not in p2))

# 场景3：空仓 + BUY_FIRST 计划 → 不注入（买入步骤本就可执行，无矛盾）
p3 = build_prompt("BUY_FIRST_THEN_SELL", with_position=False)
checks.append(("空仓+BUY_FIRST: 不注入", KEY not in p3))

# 场景4：空仓 + WAIT 计划 → 不注入
p4 = build_prompt("WAIT", with_position=False)
checks.append(("空仓+WAIT: 不注入", KEY not in p4))

# 基础结构不回归
ha, ma = p1.find("## 硬性约束"), p1.find("## 市场环境")
checks.append(("硬约束仍在市场环境之前", ha > 0 and ha < ma))
checks.append(("预计算区块保留(v2.7)", "预计算:" in p1))
checks.append(("版本号 v2.8", config.prompt.decision_version == "decision.v2.8"))

print("=" * 50)
ok = True
for name, passed in checks:
    print(f"[{'OK' if passed else 'FAIL'}] {name}")
    ok = ok and passed
print("=" * 50)
for line in p1.splitlines():
    if KEY in line:
        print("注入示例:", line)
print("全部通过" if ok else "存在失败项")
sys.exit(0 if ok else 1)
