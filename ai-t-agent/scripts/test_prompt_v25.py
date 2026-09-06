"""冒烟测试：验证 decision.v2.5 Prompt（硬约束置顶区块）"""
import sys
sys.path.insert(0, "src")

from datetime import datetime
from decimal import Decimal
from agent.config.schema import AppConfig
from agent.market.service import MarketService
from agent.decision.engine import DecisionEngine
from agent.decision.planner import TodayPlan, StockPlan
from agent.common.models import (RiskState, Position, PositionState, Fill, FeeDetail,
                                 ActionType, MarketRegime)
from agent.trading.account import Account

config = AppConfig()
market = MarketService(config)
market.set_watchlist(["002185", "600584"])

quotes = market.refresh()
assert quotes, "行情拉取失败"
market._record_intraday(quotes)
market._fetch_index()
market.refresh_klines()

class FakeLLM:
    last_error = None
engine = DecisionEngine(config, FakeLLM())

class FakeTradingEngine:
    def __init__(self, fills):
        self.today_fills = fills
trading = FakeTradingEngine([])

plan = TodayPlan(
    date="2026-08-18", market_regime=MarketRegime.RANGE,
    plans=[StockPlan(code="002185", max_trades_hint=4),
           StockPlan(code="600584", max_trades_hint=4)],
)
engine.set_daily_context(
    ["002185", "600584"], plan, market,
    trading_engine=trading, memory_retriever=None,
    regime="RANGE", market_summary="震荡市",
    yesterday_summary="2026-08-17: 日盈亏+178.96, 交易2笔, Regime=RANGE",
)

# 场景A：持仓200股T+1锁定（明日解锁场景模拟锁定时）→ 禁卖+可买上限
account = Account(initial_cash=Decimal("10000"))
account.positions["002185"] = Position(
    code="002185", total_shares=200, sellable_shares=0, today_bought=200,
    cost_price=Decimal("18.11"), stop_loss_price=Decimal("16.66"),
    position_state=PositionState.ACTIVE,
)
snap = account.snapshot(quotes)
prompt_a = engine._build_prompt(snap, quotes, RiskState.NORMAL)

# 场景B：无持仓 + 2笔成交（模拟T预算消耗）
fills = [Fill(
    fill_id=f"f{i}", order_id=f"o{i}", code="002185", action=ActionType.BUY,
    shares=100, price=Decimal("18.0"), amount=Decimal("1800"), fee=Decimal("5.02"),
    fee_detail=FeeDetail(Decimal("5"), Decimal("0"), Decimal("0.02")),
    realized_pnl=None, timestamp=datetime(2026, 8, 18, 9, 30), tick_id="t",
) for i in range(4)]
trading2 = FakeTradingEngine(fills)
engine.set_daily_context(
    ["002185", "600584"], plan, market,
    trading_engine=trading2, memory_retriever=None,
    regime="RANGE", market_summary="震荡市",
)
account2 = Account(initial_cash=Decimal("10000"))
snap2 = account2.snapshot(quotes)
prompt_b = engine._build_prompt(snap2, quotes, RiskState.NORMAL)

# 硬约束区块位置检查：必须出现在"市场环境"之前
def block_pos(p):
    return p.find("## 硬性约束"), p.find("## 市场环境")

checks = []
ha, ma = block_pos(prompt_a)
checks.append(("硬约束区块存在且在市场环境之前(A)", ha > 0 and ha < ma))
checks.append(("A: T+1禁卖硬约束", "持仓200股但可卖为0（T+1锁定），禁止发出SELL" in prompt_a))
checks.append(("A: 600584无持仓禁卖", "600584 无持仓，无股可卖，禁止发出SELL" in prompt_a))
checks.append(("A: 可买上限硬约束", "最多可买" in prompt_a[:prompt_a.find('## 市场环境')]))

hb, mb = block_pos(prompt_b)
checks.append(("硬约束区块存在且在市场环境之前(B)", hb > 0 and hb < mb))
checks.append(("B: 无持仓禁卖(两票)", prompt_b.count("无持仓，无股可卖，禁止发出SELL") == 2))
checks.append(("B: T预算达上限停交", "达到上限4笔，停止交易只可HOLD" in prompt_b))
checks.append(("B: 今日已成交4笔渲染", prompt_b.count("@18.0") == 4))

# Planner prompt 条件式规范
import inspect
src = inspect.getsource(engine.__class__)
from agent.decision import planner as pm
psrc = inspect.getsource(pm)
checks.append(("Planner含条件式规范", "条件式表述" in psrc and "禁止写无前提的触发式语句" in psrc))

print("=" * 50)
ok = True
for name, passed in checks:
    print(f"[{'OK' if passed else 'FAIL'}] {name}")
    ok = ok and passed
print("=" * 50)
print("--- 场景B硬约束区块预览 ---")
print(prompt_b[prompt_b.find("## 硬性约束"):prompt_b.find("## 市场环境")])
print("版本:", config.prompt.decision_version)
print("全部通过" if ok else "存在失败项")
sys.exit(0 if ok else 1)
