"""冒烟测试：验证 decision.v2.7 Prompt（预计算数据行：纯数值、无判断词）"""
import sys
sys.path.insert(0, "src")

from decimal import Decimal
from agent.config.schema import AppConfig
from agent.market.service import MarketService
from agent.decision.engine import DecisionEngine
from agent.decision.planner import TodayPlan, StockPlan
from agent.common.models import RiskState, MarketRegime
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

engine = DecisionEngine(config, FakeLLM())
plan = TodayPlan(
    date="2026-08-20", market_regime=MarketRegime.RANGE,
    plans=[StockPlan(code="002185", max_trades_hint=2)],
)
engine.set_daily_context(["002185"], plan, market,
                         trading_engine=FakeTrading(), memory_retriever=None,
                         regime="RANGE", market_summary="震荡市")

snap = Account(initial_cash=Decimal("10000")).snapshot(quotes)
prompt = engine._build_prompt(snap, quotes, RiskState.NORMAL)

checks = []
# 预计算数据行
checks.append(("预计算区块存在", "预计算:" in prompt))
checks.append(("日内区间位置", "日内区间位置" in prompt))
checks.append(("较日内均价", "较日内均价" in prompt))
checks.append(("开盘至今窗口", "开盘至今" in prompt))
checks.append(("近10分钟窗口", "近10分钟" in prompt))
# MA偏离（若k线技术位可用）
if "技术位:" in prompt:
    checks.append(("较MA偏离数据", "较MA5" in prompt or "较MA20" in prompt))
# 无判断性标签（只给数据原则）
for word in ("急跌", "缓跌", "横盘判定", "上涨判定", "下跌中"):
    checks.append((f"无判断词'{word}'", word not in prompt))
# 硬约束位置不变
ha, ma = prompt.find("## 硬性约束"), prompt.find("## 市场环境")
checks.append(("硬约束仍在市场环境之前", ha > 0 and ha < ma))

print("=" * 50)
ok = True
for name, passed in checks:
    print(f"[{'OK' if passed else 'FAIL'}] {name}")
    ok = ok and passed
print("=" * 50)
# 行情行预览
for line in prompt.splitlines():
    if line.startswith("- 002185") and "预计算" in line:
        print(line)
print("版本:", config.prompt.decision_version)
print("全部通过" if ok else "存在失败项")
sys.exit(0 if ok else 1)
