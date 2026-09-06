"""冒烟测试：验证 decision.v2.3 Prompt 渲染（历史上下文 + 大盘 + 技术位 + 反馈闭环）"""
import sys
sys.path.insert(0, "src")

from datetime import datetime
from decimal import Decimal
from agent.config.schema import AppConfig
from agent.market.service import MarketService
from agent.decision.engine import DecisionEngine
from agent.common.models import RiskState, Position, PositionState, Fill, FeeDetail, ActionType

config = AppConfig()
market = MarketService(config)
market.set_watchlist(["002185", "600584"])

quotes = market.refresh()
assert quotes, "行情拉取失败"
market._record_intraday(quotes)
market._fetch_index()       # 大盘指数
market.refresh_klines()     # 日K技术位

# 构造决策引擎（无 LLM，仅测 prompt 构建）
class FakeLLM:
    last_error = None
engine = DecisionEngine(config, FakeLLM())


# 模拟交易引擎（今日成交流水）
class FakeTradingEngine:
    def __init__(self):
        self.today_fills = [Fill(
            fill_id="f1", order_id="o1", code="002185", action=ActionType.BUY,
            shares=100, price=Decimal("18.65"), amount=Decimal("1865"),
            fee=Decimal("5.02"),
            fee_detail=FeeDetail(Decimal("5"), Decimal("0"), Decimal("0.02")),
            realized_pnl=None,
            timestamp=datetime(2026, 8, 14, 9, 31), tick_id="t1",
        )]
trading = FakeTradingEngine()

# 模拟昨日复盘 + Regime
engine.set_daily_context(
    ["002185", "600584"], None, market,
    trading_engine=trading, memory_retriever=None,
    regime="RANGE", market_summary="震荡市，控制节奏",
    yesterday_summary="2026-08-13: 日盈亏-156.04, 交易2笔, Regime=RANGE",
)
engine.record_feedback("SELL 002185 100股 被风控拒绝: insufficient_sellable")

# 构造快照（002185 持有 T+1 锁定仓：可卖=0）
from agent.trading.account import Account
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
checks = [
    "成交", "日内均价", "日内走势", "最多可买", "加仓",
    "禁止发出BUY", "T+1锁定，禁止发出SELL",           # v2.2 禁令
    "今日已成交", "BUY 002185 100股 @18.65",           # P0-1 成交流水
    "insufficient_sellable", "最近风控反馈",           # P0-2 反馈闭环
    "距风控线", "距涨停", "当日已付费用", "回撤状态",    # P0-3
    "市场状态: RANGE", "昨日复盘",                      # P0-3 Regime + P1-5
    "技术位", "MA5",                                    # P2-6 日K
    "同一分钟只能输出一个方向",                          # 互斥规则
]
idx = market.get_index_quote()
if idx is not None:
    checks.append("上证指数")
miss = [c for c in checks if c not in prompt]
for c in checks:
    print(f"[{'OK' if c in prompt else 'MISS'}] {c}")
print("指数拉取:", "OK" if idx is not None else "FAIL")
print("技术位拉取:", market.kline_tech().keys() if market.kline_tech() else "FAIL")
sys.exit(1 if miss or idx is None else 0)
