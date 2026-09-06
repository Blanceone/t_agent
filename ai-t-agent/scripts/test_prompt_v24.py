"""冒烟测试：验证 decision.v2.4 Prompt（无持仓禁卖标注 + 卖出整手规则）"""
import sys
sys.path.insert(0, "src")

from datetime import datetime
from decimal import Decimal
from agent.config.schema import AppConfig
from agent.market.service import MarketService
from agent.decision.engine import DecisionEngine
from agent.common.models import RiskState, Position, PositionState, Fill, FeeDetail, ActionType
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
    def __init__(self):
        self.today_fills = [Fill(
            fill_id="f1", order_id="o1", code="002185", action=ActionType.SELL,
            shares=200, price=Decimal("18.18"), amount=Decimal("3636"),
            fee=Decimal("6.39"),
            fee_detail=FeeDetail(Decimal("5"), Decimal("1.09"), Decimal("0.30")),
            realized_pnl=Decimal("-96"),
            timestamp=datetime(2026, 8, 14, 9, 33), tick_id="t1",
        )]
trading = FakeTradingEngine()

engine.set_daily_context(
    ["002185", "600584"], None, market,
    trading_engine=trading, memory_retriever=None,
    regime="RANGE", market_summary="震荡市",
    yesterday_summary="2026-08-13: 日盈亏-156.04, 交易2笔, Regime=RANGE",
)

# 场景A：无持仓（模拟清仓后）——两票都应标注禁卖
account = Account(initial_cash=Decimal("10000"))
snap = account.snapshot(quotes)
prompt_a = engine._build_prompt(snap, quotes, RiskState.NORMAL)

# 场景B：持仓但 T+1 锁定
account2 = Account(initial_cash=Decimal("10000"))
account2.positions["002185"] = Position(
    code="002185", total_shares=200, sellable_shares=0, today_bought=200,
    cost_price=Decimal("18.66"), stop_loss_price=Decimal("17.17"),
    position_state=PositionState.ACTIVE,
)
snap2 = account2.snapshot(quotes)
prompt_b = engine._build_prompt(snap2, quotes, RiskState.NORMAL)

checks_a = [
    ("无持仓禁卖标注(002185)", "- 002185" in prompt_a and prompt_a.count("禁止发出SELL（无持仓，无股可卖）") == 2),
    ("持仓区显示无持仓", "无持仓" in prompt_a),
    ("规则6卖出前提", "卖出前提" in prompt_a),
    ("规则7卖出整手", "卖出数量必须为100股整数倍" in prompt_a),
    ("已清仓禁卖表述", "已清仓" in prompt_a),
    ("今日已成交", "SELL 002185 200股 @18.18" in prompt_a),
    ("上证指数", "上证指数" in prompt_a),
    ("技术位", "MA5" in prompt_a),
]
checks_b = [
    ("T+1锁定禁卖(保留)", "T+1锁定，禁止发出SELL" in prompt_b),
    ("持仓票不误标无持仓禁卖", "002185: 持仓200股" in prompt_b),
    ("未持仓票仍标禁卖", prompt_b.count("禁止发出SELL（无持仓，无股可卖）") == 1),
]

print("=" * 50)
print("场景A：清仓后（无持仓）")
ok = True
for name, passed in checks_a:
    print(f"[{'OK' if passed else 'FAIL'}] {name}")
    ok = ok and passed
print("=" * 50)
print("场景B：T+1锁定持仓")
for name, passed in checks_b:
    print(f"[{'OK' if passed else 'FAIL'}] {name}")
    ok = ok and passed
print("=" * 50)
print("版本:", config.prompt.decision_version)
print("全部通过" if ok else "存在失败项")
sys.exit(0 if ok else 1)
