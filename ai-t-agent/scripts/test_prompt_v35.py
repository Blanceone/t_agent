"""冒烟测试：decision.v2.15（时钟/购买力/买卖一档数据）"""
import sys
sys.path.insert(0, "src")

from datetime import datetime
from decimal import Decimal
from agent.config.schema import AppConfig
from agent.market.service import MarketService
from agent.decision.engine import DecisionEngine
from agent.decision.planner import TodayPlan, StockPlan
from agent.common.models import (
    RiskState, MarketRegime, Position,
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


def make_engine():
    engine = DecisionEngine(config, FakeLLM())
    plan = TodayPlan(
        date="2026-08-27", market_regime=MarketRegime.RANGE,
        plans=[StockPlan(code="002185", t_strategy="SELL_FIRST_THEN_BUY_BACK",
                         max_trades_hint=2, target_position_ratio=0.25)],
    )
    engine.set_daily_context(
        ["002185"], plan, market,
        trading_engine=FakeTrading(), memory_retriever=None,
        regime="RANGE", market_summary="低波动",
    )
    return engine


def locked_pos():
    return Position(
        code="002185", total_shares=200, sellable_shares=0,
        today_bought=200, cost_price=Decimal("17.18"),
        stop_loss_price=Decimal("15.81"),
    )


checks = []
engine_a = make_engine()
snap_a = Account(initial_cash=Decimal("10000")).snapshot(quotes)
snap_a.positions["002185"] = locked_pos()
prompt_a = engine_a._build_prompt(snap_a, quotes, RiskState.NORMAL)
ha = prompt_a[prompt_a.find("## 硬性约束"):prompt_a.find("## 市场环境")]
checks.append(("A: T+1 仍在", "T+1锁定" in ha))
checks.append(("购买力已扣预留", "购买力" in prompt_a and "已扣现金预留" in prompt_a))
checks.append(("时钟/停止下单", "停止下单" in prompt_a))
checks.append(("买卖一档", "买一" in prompt_a and "卖一" in prompt_a))
checks.append(("成交口径卖一买一", "买入按卖一成交" in prompt_a and "卖出按买一成交" in prompt_a))
checks.append(("未锁只允许SELL", "若本分钟交易，只允许SELL" not in prompt_a))
checks.append(("接回不是加仓", "不是加仓" in prompt_a))
checks.append(("计划是参考", "不是本分钟必须成交的价格" in prompt_a))
checks.append(("版本号 v2.15", config.prompt.decision_version == "decision.v2.15"))

print("=" * 50)
ok = True
for name, passed in checks:
    print(f"[{'OK' if passed else 'FAIL'}] {name}")
    ok = ok and passed
print("=" * 50)
print("全部通过" if ok else "存在失败项")
sys.exit(0 if ok else 1)
