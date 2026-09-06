"""冒烟测试：验证 decision.v2.1 Prompt 渲染（量价 + 日内轨迹 + 加仓规则）"""
import sys
sys.path.insert(0, "src")

from decimal import Decimal
from agent.config.schema import AppConfig
from agent.market.service import MarketService
from agent.decision.engine import DecisionEngine
from agent.common.models import RiskState

config = AppConfig()
market = MarketService(config)
market.set_watchlist(["002185", "600584"])

quotes = market.refresh()
assert quotes, "行情拉取失败"
# 模拟记录两次轨迹
market._record_intraday(quotes)

# 构造决策引擎（无 LLM，仅测 prompt 构建）
class FakeLLM:
    last_error = None
engine = DecisionEngine(config, FakeLLM())
engine.set_daily_context(["002185", "600584"], None, market)

# 构造快照（模拟 002185 持有 T+1 锁定仓：可卖=0）
from agent.trading.account import Account
from agent.common.models import Position, PositionState
account = Account(initial_cash=Decimal("10000"))
account.positions["002185"] = Position(
    code="002185", total_shares=200, sellable_shares=0, today_bought=200,
    cost_price=Decimal("18.66"), stop_loss_price=Decimal("17.17"),
    position_state=PositionState.ACTIVE,
)
snap = account.snapshot(quotes)

prompt = engine._build_prompt(snap, quotes, RiskState.NORMAL)
print(prompt)
print("=" * 50)
checks = ["成交", "日内均价", "日内走势", "最多可买", "加仓", "禁止发出BUY",
          "T+1锁定，禁止发出SELL"]
for c in checks:
    print(f"[{'OK' if c in prompt else 'MISS'}] {c}")
