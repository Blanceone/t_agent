"""冒烟测试：验证 decision.v2.6 Prompt（做T预算语义：接回不占预算、不强制当日接回）"""
import sys
sys.path.insert(0, "src")

from datetime import datetime
from decimal import Decimal
from agent.config.schema import AppConfig
from agent.market.service import MarketService
from agent.decision.engine import DecisionEngine
from agent.decision.planner import TodayPlan, StockPlan
from agent.common.models import (RiskState, ActionType, Fill, FeeDetail, MarketRegime)
from agent.trading.account import Account

config = AppConfig()
market = MarketService(config)
market.set_watchlist(["002185"])
quotes = market.refresh()
assert quotes, "行情拉取失败"
market._record_intraday(quotes)
market._fetch_index()

class FakeLLM:
    last_error = None

engine = DecisionEngine(config, FakeLLM())

def mk_fill(action, shares, i):
    return Fill(
        fill_id=f"f{i}", order_id=f"o{i}", code="002185", action=action,
        shares=shares, price=Decimal("19.0"), amount=Decimal("3800"),
        fee=Decimal("6.94"),
        fee_detail=FeeDetail(Decimal("6.9"), Decimal("0"), Decimal("0.04")),
        realized_pnl=None, timestamp=datetime(2026, 8, 19, 9, 30), tick_id="t",
    )

# 计划：T预算=1次（8/18实际场景：卖出一笔后预算即显示用完）
plan = TodayPlan(
    date="2026-08-19", market_regime=MarketRegime.RANGE,
    plans=[StockPlan(code="002185", max_trades_hint=1)],
)

checks = []

# 场景C：已卖200股、未接回 → 应允许接回BUY，且不强制当日
trading_c = type("T", (), {"today_fills": [mk_fill(ActionType.SELL, 200, 1)]})()
engine.set_daily_context(["002185"], plan, market,
                         trading_engine=trading_c, memory_retriever=None,
                         regime="RANGE", market_summary="震荡市")
snap_c = Account(initial_cash=Decimal("10000")).snapshot(quotes)
prompt_c = engine._build_prompt(snap_c, quotes, RiskState.NORMAL)
hc = prompt_c[prompt_c.find("## 硬性约束"):prompt_c.find("## 市场环境")]
checks.append(("C: 未接回提示存在", "尚有200股卖出未接回" in hc))
checks.append(("C: 仅允许接回BUY", "仅允许在合适低位发出接回BUY完成本次做T" in hc))
checks.append(("C: 不强制当日接回", "不强制今日接回" in hc))
checks.append(("C: 不出现一刀切停交", "停止交易只可HOLD" not in hc))

# 场景D：卖200股+买回200股（做T闭环）→ 正常停交
trading_d = type("T", (), {"today_fills": [
    mk_fill(ActionType.SELL, 200, 1), mk_fill(ActionType.BUY, 200, 2)]})()
engine.set_daily_context(["002185"], plan, market,
                         trading_engine=trading_d, memory_retriever=None,
                         regime="RANGE", market_summary="震荡市")
snap_d = Account(initial_cash=Decimal("10000")).snapshot(quotes)
prompt_d = engine._build_prompt(snap_d, quotes, RiskState.NORMAL)
hd = prompt_d[prompt_d.find("## 硬性约束"):prompt_d.find("## 市场环境")]
checks.append(("D: 闭环后停交", "达到上限1笔，停止交易只可HOLD" in hd))
checks.append(("D: 不再出现接回例外", "卖出未接回" not in hd))

# 规则与Planner规范检查
checks.append(("决策规则含做T含义", "做T含义：一次做T = 先高位卖出、再低位买回" in prompt_c))
checks.append(("决策规则: 接回不占预算", "不占用新的交易笔数预算" in prompt_c))
checks.append(("决策规则: 可等后续交易日", "可等后续交易日" in prompt_c))

import inspect
from agent.decision import planner as pm
psrc = inspect.getsource(pm)
checks.append(("Planner规范含做T计数语义", "按\"做T次数\"计" in psrc))
checks.append(("Planner规范禁止当日必须买回", "不得要求\"当日必须买回\"" in psrc))

print("=" * 50)
ok = True
for name, passed in checks:
    print(f"[{'OK' if passed else 'FAIL'}] {name}")
    ok = ok and passed
print("=" * 50)
print("--- 场景C硬约束区块预览 ---")
print(hc)
print("版本:", config.prompt.decision_version)
print("全部通过" if ok else "存在失败项")
sys.exit(0 if ok else 1)
