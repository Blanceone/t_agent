"""冒烟测试：decision.v2.16 / planner.v1.3（计划对照与相对价）"""
import sys
sys.path.insert(0, "src")

from datetime import datetime
from decimal import Decimal
from agent.config.schema import AppConfig
from agent.market.service import MarketService
from agent.decision.engine import DecisionEngine
from agent.decision.planner import TodayPlan, StockPlan, Planner
from agent.common.models import (
    RiskState, MarketRegime, Position,
)
from agent.market.understanding import MarketUnderstandingOutput
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

    def __init__(self):
        self.prompt = None

    def call_json(self, prompt, timeout_ms=None):
        self.prompt = prompt
        return {
            "global_bias": "BALANCED",
            "plans": [{
                "code": "002185",
                "trade_plan": "当持有可卖仓位且价格处于当日偏高一侧时可卖出",
                "target_position_ratio": 0.25,
                "t_strategy": "SELL_FIRST_THEN_BUY_BACK",
                "risk_level": "MEDIUM",
                "max_trades_hint": 2,
                "notes": "",
            }],
        }


class FakeTrading:
    def __init__(self, fills=None):
        self.today_fills = fills or []


def make_engine():
    engine = DecisionEngine(config, FakeLLM())
    q = quotes.get("002185")
    last = q.last if q else Decimal("16.67")
    plan = TodayPlan(
        date="2026-08-27", market_regime=MarketRegime.RANGE,
        plans=[StockPlan(code="002185", t_strategy="SELL_FIRST_THEN_BUY_BACK",
                         max_trades_hint=2, target_position_ratio=0.25)],
        generated_at="09:20",
        last_at_plan={"002185": last},
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
checks.append(("计划非绝对成交价", "不是本分钟必须命中的绝对成交价" in prompt_a))
checks.append(("高于计划价非禁令", "不要把「现价高于/低于计划价」当成禁止买卖的条件" in prompt_a))
checks.append(("计划对照行", "计划生成于09:20" in prompt_a and "较计划时" in prompt_a))
checks.append(("版本号 v2.16", config.prompt.decision_version == "decision.v2.16"))
checks.append(("planner 版本 v1.3", config.prompt.planner_version == "planner.v1.3"))

pllm = FakeLLM()
planner = Planner(pllm)
mu = MarketUnderstandingOutput(
    date="2026-08-27", market_regime=MarketRegime.RANGE,
    today_risk_level="MEDIUM", today_strategy_preference="BALANCED",
    today_market_summary="震荡",
)
plan = planner.generate(
    "2026-08-27", mu, snap_a, quotes, ["002185"],
)
pp = pllm.prompt or ""
checks.append(("Planner 竞价口径", "连续竞价尚未开始" in pp))
checks.append(("Planner 禁绝对价带", "价格条件写相对关系" in pp and "触发价格区间" not in pp))
checks.append(("Planner 记录当时现价", "002185" in plan.last_at_plan))

print("=" * 50)
ok = True
for name, passed in checks:
    print(f"[{'OK' if passed else 'FAIL'}] {name}")
    ok = ok and passed
print("=" * 50)
print("全部通过" if ok else "存在失败项")
sys.exit(0 if ok else 1)
