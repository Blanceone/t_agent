"""
Context Assembler（统一上下文组装）

为 Planner / Decision / Reflection 提供统一、可版本化、可 Replay 的 Context。
所有 LLM Prompt 统一引用 Context 切片，禁止把完整账本与历史原文反复硬编码进 Prompt。

schema: context.v1
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional

from agent.common.models import (
    AccountSnapshot,
    FeatureSnapshot,
    MemoryItem,
    Quote,
    RiskSnapshot,
    RiskState,
)
from agent.common.logger import get_logger
from agent.common.utils import compute_hash, gen_context_id

logger = get_logger("decision.context")


@dataclass
class SystemContext:
    """系统上下文"""
    date: str
    session: str  # "AM" / "PM"
    risk_state: str
    system_mode: str  # "NORMAL" / "PAUSE"
    schema_version: str = "context.v1"


@dataclass
class MarketContext:
    """市场上下文（第一阶段简化）"""
    market_regime: str = "RANGE"  # 第一阶段默认
    risk_level: str = "MEDIUM"
    trading_suggestion: str = "ACTIVE_T"


@dataclass
class PortfolioContext:
    """账户上下文"""
    nav_mark: Decimal = Decimal("0")
    cash_available: Decimal = Decimal("0")
    day_pnl: Decimal = Decimal("0")
    realized_pnl_today: Decimal = Decimal("0")
    peak_nav: Decimal = Decimal("0")
    excess_vs_benchmark: Decimal = Decimal("0")


@dataclass
class HoldingContext:
    """单票持仓上下文"""
    code: str = ""
    total_shares: int = 0
    sellable_shares: int = 0
    cost_price: Decimal = Decimal("0")
    stop_loss_price: Decimal = Decimal("0")
    stop_loss_distance_pct: float = 0.0
    position_state: str = "ACTIVE"
    last_price: Decimal = Decimal("0")
    chg_pct_1d: float = 0.0
    round_trip_fee_est: Decimal = Decimal("0")


@dataclass
class MemoryContext:
    """记忆上下文"""
    items: List[MemoryItem] = field(default_factory=list)
    memory_ids: List[str] = field(default_factory=list)
    truncated: bool = False


@dataclass
class Context:
    """统一上下文（schema: context.v1）"""
    context_id: str = ""
    schema_version: str = "context.v1"
    system: Optional[SystemContext] = None
    market: Optional[MarketContext] = None
    portfolio: Optional[PortfolioContext] = None
    holdings: List[HoldingContext] = field(default_factory=list)
    memory: Optional[MemoryContext] = None
    token_budget_used: int = 0
    token_budget_max: int = 4000
    context_hash: str = ""


class ContextAssembler:
    """统一上下文组装器"""

    def __init__(self, max_tokens: int = 4000):
        self._max_tokens = max_tokens

    def assemble(
        self,
        snapshot: AccountSnapshot,
        quotes: Dict[str, Quote],
        risk_snapshot: Optional[RiskSnapshot] = None,
        memory_items: Optional[List[MemoryItem]] = None,
        date: str = "",
        session: str = "AM",
    ) -> Context:
        """
        组装完整 Context。

        按重要性截断：System > Portfolio > Holdings > Memory > Market
        """
        context_id = gen_context_id()

        # System
        system = SystemContext(
            date=date,
            session=session,
            risk_state=snapshot.risk_state.value,
            system_mode="NORMAL",
        )

        # Market（第一阶段简化）
        market = MarketContext()

        # Portfolio
        day_pnl = snapshot.nav_mark - snapshot.last_nav
        portfolio = PortfolioContext(
            nav_mark=snapshot.nav_mark,
            cash_available=snapshot.cash_available,
            day_pnl=day_pnl,
            realized_pnl_today=snapshot.realized_pnl_today,
            peak_nav=snapshot.peak_nav,
        )

        # Holdings
        holdings = []
        for code, pos in snapshot.positions.items():
            q = quotes.get(code)
            last_price = q.last if q else Decimal("0")
            chg_1d = float((last_price - q.pre_close) / q.pre_close) if q and q.pre_close > 0 else 0.0
            stop_dist = float((last_price - pos.stop_loss_price) / pos.stop_loss_price) if pos.stop_loss_price > 0 else 0.0

            holdings.append(HoldingContext(
                code=code,
                total_shares=pos.total_shares,
                sellable_shares=pos.sellable_shares,
                cost_price=pos.cost_price,
                stop_loss_price=pos.stop_loss_price,
                stop_loss_distance_pct=stop_dist,
                position_state=pos.position_state.value,
                last_price=last_price,
                chg_pct_1d=chg_1d,
            ))

        # Memory
        mem_ctx = MemoryContext()
        if memory_items:
            mem_ctx.items = memory_items
            mem_ctx.memory_ids = [m.memory_id for m in memory_items]

        ctx = Context(
            context_id=context_id,
            system=system,
            market=market,
            portfolio=portfolio,
            holdings=holdings,
            memory=mem_ctx,
            token_budget_max=self._max_tokens,
        )

        # 计算哈希（用于 Replay 校验）
        ctx.context_hash = compute_hash({
            "context_id": ctx.context_id,
            "nav": str(snapshot.nav_mark),
            "risk_state": snapshot.risk_state.value,
            "holdings_count": len(holdings),
            "memory_ids": mem_ctx.memory_ids,
        })

        return ctx

    def render_for_prompt(self, ctx: Context) -> str:
        """将 Context 渲染为 Prompt 文本片段"""
        parts = []

        if ctx.system:
            parts.append(f"[系统] 日期={ctx.system.date} 风控={ctx.system.risk_state}")

        if ctx.portfolio:
            p = ctx.portfolio
            parts.append(f"[账户] 净值={p.nav_mark} 现金={p.cash_available} 日盈亏={p.day_pnl}")

        if ctx.holdings:
            for h in ctx.holdings:
                parts.append(
                    f"[持仓] {h.code}: {h.total_shares}股 可卖{h.sellable_shares} "
                    f"成本{h.cost_price} 现价{h.last_price} 止损距{h.stop_loss_distance_pct:.1%}"
                )

        if ctx.memory and ctx.memory.items:
            for m in ctx.memory.items[:5]:
                parts.append(f"[记忆] {m.content[:80]}")

        return "\n".join(parts)
