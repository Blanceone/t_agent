"""
Planner（开盘前计划）

每日 09:20 市场理解完成后触发，为 watchlist 中每只股票生成 Today Plan。
受 Market Regime 约束：做T频率上限、目标仓位带、风险等级默认值。
失败则使用保守默认计划。
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional

from agent.common.models import (
    AccountSnapshot,
    MarketRegime,
    MemoryItem,
    Quote,
)
from agent.common.logger import get_logger
from agent.common.utils import now_cst
from agent.llm.client import LLMClient
from agent.market.understanding import MarketUnderstandingOutput

logger = get_logger("planner")


@dataclass
class StockPlan:
    """单票计划"""
    code: str
    trade_plan: str = ""
    target_position_ratio: float = 0.25
    t_strategy: str = "SELL_FIRST_THEN_BUY_BACK"  # SELL_FIRST_THEN_BUY_BACK / BUY_FIRST_THEN_SELL / WAIT
    risk_level: str = "MEDIUM"
    max_trades_hint: int = 4
    notes: str = ""


@dataclass
class TodayPlan:
    """今日计划"""
    date: str
    market_regime: MarketRegime = MarketRegime.RANGE
    plans: List[StockPlan] = field(default_factory=list)
    min_cash_ratio: float = 0.20
    global_bias: str = "BALANCED"  # AGGRESSIVE / BALANCED / CONSERVATIVE
    degraded: bool = False
    generated_at: str = ""  # HH:MM，计划生成时刻
    last_at_plan: Dict[str, Decimal] = field(default_factory=dict)


def _plan_quote_snapshot(
    watchlist: List[str], quotes: Optional[Dict[str, Quote]]
) -> tuple:
    """记录计划生成时刻与当时现价，供分钟决策对照。"""
    last_at: Dict[str, Decimal] = {}
    for code in watchlist:
        q = quotes.get(code) if quotes else None
        if q is not None:
            last_at[code] = q.last
    return now_cst().strftime("%H:%M"), last_at


# Regime 对 Planner 的默认约束
REGIME_CONSTRAINTS = {
    MarketRegime.TREND: {
        "max_trades": 6,
        "default_bias": "AGGRESSIVE",
        "default_risk": "MEDIUM",
        "default_strategy": "BUY_FIRST_THEN_SELL",
    },
    MarketRegime.RANGE: {
        "max_trades": 4,
        "default_bias": "BALANCED",
        "default_risk": "MEDIUM",
        "default_strategy": "SELL_FIRST_THEN_BUY_BACK",
    },
    MarketRegime.HIGH_VOL: {
        "max_trades": 2,
        "default_bias": "CONSERVATIVE",
        "default_risk": "HIGH",
        "default_strategy": "WAIT",
    },
    MarketRegime.LOW_VOL: {
        "max_trades": 2,
        "default_bias": "CONSERVATIVE",
        "default_risk": "LOW",
        "default_strategy": "WAIT",
    },
}


class Planner:
    """开盘前计划引擎"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self._llm = llm_client

    def generate(
        self,
        date: str,
        mu_output: MarketUnderstandingOutput,
        snapshot: AccountSnapshot,
        quotes: Dict[str, Quote],
        watchlist: List[str],
        memory_items: Optional[List[MemoryItem]] = None,
        market_service=None,
        yesterday_summary: str = "",
    ) -> TodayPlan:
        """
        生成 Today Plan。

        流程：
        1. 读取 Regime 约束
        2. LLM 为每只票生成计划（可选）
        3. 失败则使用保守默认
        """
        regime = mu_output.market_regime
        constraints = REGIME_CONSTRAINTS.get(regime, REGIME_CONSTRAINTS[MarketRegime.RANGE])

        # 尝试 LLM 生成
        if self._llm:
            try:
                plan = self._llm_generate(date, mu_output, snapshot, quotes, watchlist,
                                          memory_items, market_service, yesterday_summary)
                if plan and plan.plans:
                    return plan
            except Exception as e:
                logger.warning("planner_llm_failed", error=str(e))

        # 降级：保守默认计划
        return self._default_plan(date, regime, watchlist, constraints, quotes)

    def _default_plan(
        self, date: str, regime: MarketRegime, watchlist: List[str], constraints: dict,
        quotes: Optional[Dict[str, Quote]] = None,
    ) -> TodayPlan:
        """保守默认计划"""
        plans = []
        for code in watchlist:
            plans.append(StockPlan(
                code=code,
                trade_plan="条件满足时交易，否则观望",
                target_position_ratio=0.25,
                t_strategy=constraints["default_strategy"],
                risk_level=constraints["default_risk"],
                max_trades_hint=constraints["max_trades"],
                notes="默认计划（LLM降级）",
            ))

        generated_at, last_at_plan = _plan_quote_snapshot(watchlist, quotes)
        return TodayPlan(
            date=date,
            market_regime=regime,
            plans=plans,
            min_cash_ratio=0.20,
            global_bias=constraints["default_bias"],
            degraded=True,
            generated_at=generated_at,
            last_at_plan=last_at_plan,
        )

    def _llm_generate(
        self,
        date: str,
        mu_output: MarketUnderstandingOutput,
        snapshot: AccountSnapshot,
        quotes: Dict[str, Quote],
        watchlist: List[str],
        memory_items: Optional[List[MemoryItem]],
        market_service=None,
        yesterday_summary: str = "",
    ) -> Optional[TodayPlan]:
        """LLM 生成计划"""
        regime = mu_output.market_regime
        constraints = REGIME_CONSTRAINTS.get(regime, REGIME_CONSTRAINTS[MarketRegime.RANGE])

        # 日K技术位
        kline_tech = {}
        if market_service is not None:
            try:
                kline_tech = market_service.kline_tech()
            except Exception:
                pass

        # 构建持仓信息（含技术位）
        holdings_info = []
        for code in watchlist:
            pos = snapshot.positions.get(code)
            q = quotes.get(code)
            tech = ""
            t = kline_tech.get(code)
            if t:
                parts = [f"MA5 {t['ma5']:.2f}"]
                if t.get("ma20"):
                    parts.append(f"MA20 {t['ma20']:.2f}")
                if t.get("support"):
                    parts.append(f"支撑{t['support']:.2f}")
                if t.get("resistance"):
                    parts.append(f"压力{t['resistance']:.2f}")
                tech = ", 技术位: " + "/".join(parts)
            if pos and q:
                holdings_info.append(
                    f"- {code}: 持仓{pos.total_shares}股, 可卖{pos.sellable_shares}, "
                    f"成本{pos.cost_price}, 昨收{q.pre_close}{tech}；"
                    f"竞价快照（尚未形成日内含义，勿当全日锚）: "
                    f"现价{q.last}, 今开{q.open}, 日内均价{q.vwap}, 最高{q.high}, 最低{q.low}"
                )
            elif q:
                pb = (getattr(snapshot, "pending_buyback", None) or {}).get(code)
                pending_note = ""
                if pb is not None and getattr(pb, "shares", 0) > 0:
                    pending_note = (
                        f", 未接回{pb.shares}股, 卖出均价{pb.sell_avg}"
                        f"（账户事实，不是买入上限，也不强制买回）"
                    )
                holdings_info.append(
                    f"- {code}: 无持仓{pending_note}, 昨收{q.pre_close}{tech}；"
                    f"竞价快照（尚未形成日内含义，勿当全日锚）: "
                    f"现价{q.last}, 今开{q.open}, 日内均价{q.vwap}, 最高{q.high}, 最低{q.low}"
                )

        # 大盘环境
        index_text = "无"
        if market_service is not None:
            try:
                idx = market_service.get_index_quote()
                if idx is not None and idx.pre_close > 0:
                    chg = float((idx.last - idx.pre_close) / idx.pre_close) * 100
                    index_text = f"{idx.name} 现价{idx.last} 涨跌{chg:+.2f}%"
            except Exception:
                pass

        memory_text = ""
        if memory_items:
            memory_text = "\n".join(f"- {m.content[:60]}" for m in memory_items[:5])

        prompt = f"""你是A股日内做T交易计划员。根据市场状态和持仓，为每只股票制定今日做T计划。

## 市场状态
- 日期: {date}
- Regime: {regime.value}
- 风险等级: {mu_output.today_risk_level}
- 策略偏好: {mu_output.today_strategy_preference}
- 市场摘要: {mu_output.today_market_summary}
- 大盘指数: {index_text}
- 昨日复盘: {yesterday_summary[:150] if yesterday_summary else "无"}

## 约束
- 最大做T次数: {constraints['max_trades']}
- 最低现金比例: 20%

## 数据口径
当前为开盘前计划时点（09:20），连续竞价尚未开始。下方「现价 / 今开 / 日内均价 / 最高 / 最低」尚未形成有效日内含义，不要把这些数写成全日绝对成交价。昨收、成本、MA、支撑/压力是已收盘或账户事实，可以引用。

## 持仓与技术位
{chr(10).join(holdings_info) if holdings_info else "无持仓"}

## 相关记忆
{memory_text if memory_text else "无"}

## 计划编写规范
1. trade_plan 写成"当<状态条件>且<价格条件>时，执行<动作>"的条件式表述，不要写无前提的触发式语句
2. 仓位相对目标是数据，不要写成必须立刻加仓或减仓。买入可以是接回、加仓或建仓，手数由分钟决策按购买力决定
3. 卖出条件写明持仓前提（如持有可卖仓位）；若无持仓，计划中不要包含卖出动作。未接回是参考，不要写成必须买回或不得超过未接回
4. 价格条件写相对关系，不要写开盘快照上的绝对价区间（不要把此刻现价/均价/最高/最低冻成全日成交门，例如「在a.aa-b.bb时卖出」）。可写较今开、较当时日内最高/最低/均价、较成本、较昨收、较MA/支撑/压力；方向与大致宽窄即可。不要写「卖在偏高一侧」这类无参照的定性句，也不指定必须使用均线。
5. 每条计划需说明：目标仓位、今日最多交易笔数、买卖的相对条件、不满足条件时保持观望。不要输出 fen 级绝对触发价。
6. "今日最多交易笔数"按"做T次数"计：一次做T = 卖出+买回，卖出后的买回不占用新预算；不强制当日买回。max_trades_hint 为整数，不得超过上方「最大做T次数」；输出示例中的数字不是默认值。先卖后买时每笔卖出占1次，分批卖出分别计入；买入不占。不要因此要求一次卖光或必须分批。WAIT或今日不安排做T时，不要把 max_trades_hint 写成 0 来锁死买卖；0 不等于次数已满。空仓时不要全日禁止买入。
7. trade_plan 的动作不要写死持仓/可卖/未接回的全部股数（禁止「卖出300股」「买入200股建仓」）。手数由分钟决策根据可卖/最多可买自定；可写「卖出不超过可卖」。未接回不是买入上限。

## 输出格式（严格JSON）
```json
{{
  "global_bias": "AGGRESSIVE|BALANCED|CONSERVATIVE",
  "plans": [
    {{
      "code": "股票代码",
      "trade_plan": "具体做T策略描述",
      "target_position_ratio": 0.25,
      "t_strategy": "SELL_FIRST_THEN_BUY_BACK|BUY_FIRST_THEN_SELL|WAIT",
      "risk_level": "LOW|MEDIUM|HIGH",
      "max_trades_hint": 2,
      "notes": "补充说明"
    }}
  ]
}}
```"""

        raw = self._llm.call_json(prompt, timeout_ms=45000)
        if not raw:
            return None

        # 解析
        plans = []
        for p in raw.get("plans", []):
            code = str(p.get("code", ""))
            if code not in watchlist:
                continue

            strategy = str(p.get("t_strategy", "WAIT")).upper()
            if strategy not in ("SELL_FIRST_THEN_BUY_BACK", "BUY_FIRST_THEN_SELL", "WAIT"):
                strategy = "WAIT"

            risk = str(p.get("risk_level", "MEDIUM")).upper()
            if risk not in ("LOW", "MEDIUM", "HIGH"):
                risk = "MEDIUM"

            max_trades = int(p.get("max_trades_hint", constraints["max_trades"]))
            max_trades = min(max_trades, constraints["max_trades"])

            ratio = float(p.get("target_position_ratio", 0.25))
            ratio = max(0.0, min(0.5, ratio))

            plans.append(StockPlan(
                code=code,
                trade_plan=str(p.get("trade_plan", "")),
                target_position_ratio=ratio,
                t_strategy=strategy,
                risk_level=risk,
                max_trades_hint=max_trades,
                notes=str(p.get("notes", "")),
            ))

        if not plans:
            return None

        bias = str(raw.get("global_bias", constraints["default_bias"])).upper()
        if bias not in ("AGGRESSIVE", "BALANCED", "CONSERVATIVE"):
            bias = constraints["default_bias"]

        generated_at, last_at_plan = _plan_quote_snapshot(watchlist, quotes)
        return TodayPlan(
            date=date,
            market_regime=regime,
            plans=plans,
            min_cash_ratio=0.20,
            global_bias=bias,
            degraded=False,
            generated_at=generated_at,
            last_at_plan=last_at_plan,
        )

    def render_for_context(self, plan: TodayPlan) -> str:
        """将 Today Plan 渲染为 Context 文本"""
        parts = [f"[计划] Regime={plan.market_regime.value} 偏向={plan.global_bias}"]
        for p in plan.plans:
            parts.append(
                f"  {p.code}: {p.t_strategy} 最多{p.max_trades_hint}次 "
                f"目标仓位{p.target_position_ratio:.0%} 风险{p.risk_level}"
            )
        return "\n".join(parts)
