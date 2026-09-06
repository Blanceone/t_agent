"""
统一领域模型（Domain Model）

所有模块只能使用本文件定义的模型。
禁止使用裸 dict 传递业务数据、禁止重复定义、禁止字段名不一致。
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict


# ==================== 枚举 ====================


class RiskState(Enum):
    """三级风控状态"""
    NORMAL = "NORMAL"
    HALT = "HALT"
    LIQUIDATE = "LIQUIDATE"


class PositionState(Enum):
    """持仓状态机"""
    ACTIVE = "ACTIVE"
    PENDING_CLEAR = "PENDING_CLEAR"
    CLEARING = "CLEARING"
    LIQ_FAIL = "LIQ_FAIL"


class ActionType(Enum):
    """交易动作"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class OrderSource(Enum):
    """订单来源"""
    DECISION = "DECISION"
    STOP_LOSS = "STOP_LOSS"
    LIQUIDATE = "LIQUIDATE"
    USER_REMOVE = "USER_REMOVE"


class MemoryType(Enum):
    """记忆类型"""
    LONG = "LONG"
    SHORT = "SHORT"
    MARKET = "MARKET"
    PORTFOLIO = "PORTFOLIO"
    REFLECTION = "REFLECTION"
    TRADE = "TRADE"
    HOLDING = "HOLDING"


class MarketRegime(Enum):
    """市场状态四态"""
    TREND = "TREND"
    RANGE = "RANGE"
    HIGH_VOL = "HIGH_VOL"
    LOW_VOL = "LOW_VOL"


class RejectReason(Enum):
    """拒单原因码"""
    LIMIT_BOARD = "REASON_LIMIT_BOARD"
    NO_QUOTE = "REASON_NO_QUOTE"
    SUSPENDED = "REASON_SUSPENDED"
    INSUFFICIENT_SELLABLE = "REASON_INSUFFICIENT_SELLABLE"
    INVALID_LOT = "REASON_INVALID_LOT"
    ODD_LOT = "REASON_ODD_LOT"
    COOLDOWN = "REASON_COOLDOWN"
    CASH_RESERVE = "REASON_CASH_RESERVE"
    POSITION_LIMIT = "REASON_POSITION_LIMIT"
    HALT = "REASON_HALT"
    LOW_CONFIDENCE = "REASON_LOW_CONFIDENCE"
    STALE_QUOTE = "REASON_STALE_QUOTE"
    INTRADAY_BUY_LIMIT = "REASON_INTRADAY_BUY_LIMIT"
    LOSS_LINK_REJECT = "REASON_LOSS_LINK_REJECT"
    T_BUDGET_EXCEEDED = "REASON_T_BUDGET_EXCEEDED"


class SystemEvent(Enum):
    """系统事件枚举"""
    # 调度与生命周期
    SCHEDULER_DAY_START = "SCHEDULER_DAY_START"
    TRADING_SESSION_START = "TRADING_SESSION_START"
    SESSION_SUSPEND = "SESSION_SUSPEND"
    DAY_CLOSE_FINISHED = "DAY_CLOSE_FINISHED"

    # 行情与 Feature
    MARKET_UPDATED = "MARKET_UPDATED"
    FEATURE_UPDATED = "FEATURE_UPDATED"
    SKIP_STALE = "SKIP_STALE"

    # 决策链路
    CONTEXT_ASSEMBLED = "CONTEXT_ASSEMBLED"
    CONTEXT_FALLBACK = "CONTEXT_FALLBACK"
    DECISION_FINISHED = "DECISION_FINISHED"
    LLM_TIMEOUT = "LLM_TIMEOUT"

    # 风控
    RISK_PASSED = "RISK_PASSED"
    RISK_REJECTED = "RISK_REJECTED"
    STOP_LOSS_TRIGGERED = "STOP_LOSS_TRIGGERED"
    HALT_TRIGGERED = "HALT_TRIGGERED"
    LIQUIDATE_TRIGGERED = "LIQUIDATE_TRIGGERED"

    # 交易执行
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_REJECTED = "ORDER_REJECTED"
    EXECUTION_FINISHED = "EXECUTION_FINISHED"

    # Tick
    TICK_STARTED = "TICK_STARTED"
    TICK_FINISHED = "TICK_FINISHED"

    # 记忆与复盘
    MEMORY_WRITTEN = "MEMORY_WRITTEN"
    MEMORY_UPDATE_FINISHED = "MEMORY_UPDATE_FINISHED"
    REFLECTION_STATS_READY = "REFLECTION_STATS_READY"
    REFLECTION_FINISHED = "REFLECTION_FINISHED"

    # 计划与理解（第二阶段）
    MARKET_UNDERSTANDING_FINISHED = "MARKET_UNDERSTANDING_FINISHED"
    PLANNER_FINISHED = "PLANNER_FINISHED"

    # Replay
    REPLAY_PACKAGE_SAVED = "REPLAY_PACKAGE_SAVED"

    # 系统
    WATCHDOG_RESTART = "WATCHDOG_RESTART"
    CONFIG_LOADED = "CONFIG_LOADED"


# ==================== 行情与 Feature ====================


@dataclass(frozen=True)
class Quote:
    """实时行情快照（不可变）"""
    code: str
    name: str
    last: Decimal
    bid1: Optional[Decimal]
    ask1: Optional[Decimal]
    high: Decimal
    low: Decimal
    open: Decimal
    pre_close: Decimal
    limit_up: Decimal
    limit_down: Decimal
    volume: int
    turnover: Decimal
    vwap: Decimal
    is_suspended: bool
    is_st: bool
    timestamp: datetime
    bid1_volume: Optional[int] = None  # 买一量（手）
    ask1_volume: Optional[int] = None  # 卖一量（手）

    @property
    def mark_price(self) -> Decimal:
        """盯市价格回退：bid1 → last → pre_close"""
        if self.bid1 is not None:
            return self.bid1
        if self.last is not None:
            return self.last
        return self.pre_close


@dataclass(frozen=True)
class FeatureSnapshot:
    """基础市场 Feature（schema: feature.v1）"""
    code: str
    pre_close: Decimal
    open: Decimal
    high: Decimal
    low: Decimal
    last: Decimal
    open_chg_pct: float
    chg_pct_1d: float
    chg_pct_5d: Optional[float]
    chg_pct_10d: Optional[float]
    vwap: Decimal
    amplitude: float
    volume: int
    volume_ratio: Optional[float]
    turnover_rate: Optional[float]
    round_trip_fee_est: Decimal
    schema_version: str = "feature.v1"


# ==================== 账户与持仓 ====================


@dataclass
class Position:
    """持仓实体"""
    code: str
    total_shares: int
    sellable_shares: int
    today_bought: int
    cost_price: Decimal
    stop_loss_price: Decimal
    stop_breach_count: int = 0
    position_state: PositionState = PositionState.ACTIVE
    exit_reason: Optional[str] = None


@dataclass
class WatchlistEntry:
    """股票池条目"""
    code: str
    added_at: str
    cooldown_until_date: Optional[str] = None


@dataclass
class Cash:
    """现金管理"""
    available: Decimal
    reserved_min_ratio: Decimal = Decimal("0.20")


@dataclass
class AccountSnapshot:
    """账户不可变快照（Tick 内使用）"""
    account_id: str
    nav_mark: Decimal
    cash_available: Decimal
    peak_nav: Decimal
    last_nav: Decimal
    risk_state: RiskState
    positions: Dict[str, Position]
    realized_pnl_today: Decimal
    liquidation_queue: List["LiquidationTask"]
    snapshot_time: datetime


# ==================== 订单与成交 ====================


@dataclass
class OrderIntent:
    """订单意图（Risk 校验前）"""
    intent_id: str
    action: ActionType
    code: str
    shares: int
    source: OrderSource
    confidence: Optional[float] = None
    decision_id: Optional[str] = None


@dataclass
class FeeDetail:
    """费用明细"""
    commission: Decimal
    stamp_tax: Decimal
    transfer_fee: Decimal

    @property
    def total(self) -> Decimal:
        return self.commission + self.stamp_tax + self.transfer_fee


@dataclass
class Fill:
    """成交记录"""
    fill_id: str
    order_id: str
    code: str
    action: ActionType
    shares: int
    price: Decimal
    amount: Decimal
    fee: Decimal
    fee_detail: FeeDetail
    realized_pnl: Optional[Decimal]
    timestamp: datetime
    tick_id: str


@dataclass
class LiquidationTask:
    """清仓任务"""
    task_id: str
    code: str
    remaining_shares: int
    exit_reason: str
    attempts: int = 0
    created_at: str = ""


@dataclass
class RejectResult:
    """拒单结果"""
    intent_id: str
    code: str
    action: ActionType
    reason: RejectReason
    detail: str = ""


# ==================== 决策 ====================


@dataclass
class DecisionItem:
    """单条决策（schema: decision.v1）"""
    action: ActionType
    code: str
    shares: int
    confidence: float
    reason: str
    risk_level: str  # LOW/MEDIUM/HIGH
    referenced_memory: List[str] = field(default_factory=list)


@dataclass
class DecisionOutput:
    """完整决策输出"""
    thought_process: str
    decisions: List[DecisionItem]
    schema_version: str = "decision.v1"
    prompt_id: str = ""
    prompt_version: str = ""
    prompt_render_hash: str = ""
    context_id: str = ""
    timestamp: str = ""


# ==================== 风控 ====================


@dataclass
class RiskVerdict:
    """风控校验结果"""
    passed: bool
    reason_code: Optional[RejectReason] = None
    detail: Optional[str] = None


@dataclass
class RiskSnapshot:
    """风控状态快照（注入 Context）"""
    risk_state: RiskState
    day_loss_ratio: float
    drawdown_ratio: float
    realized_pnl_today: Decimal
    halt_count_today: int
    stop_loss_count_today: int


# ==================== 记忆 ====================


@dataclass
class MemoryItem:
    """记忆条目（schema: memory.v1）"""
    memory_id: str
    type: MemoryType
    codes: List[str]
    created_at: str
    ttl_days: Optional[int]
    tags: List[str]
    content: str
    source: str
    importance: float
    schema_version: str = "memory.v1"
    compressed: bool = False
    original_ref: Optional[str] = None


# ==================== Replay ====================


@dataclass
class TickRecord:
    """单 Tick 完整记录（schema: replay.v1）"""
    tick_id: str
    timestamp: str
    account_snapshot_hash: str
    quotes_snapshot: Dict[str, dict]
    risk_state: str
    context_id: str
    prompt_id: str
    prompt_version: str
    prompt_render_hash: str
    feature_snapshot: dict
    feature_hash: str
    memory_ids: List[str]
    decision_output: Optional[dict]
    confidence: Optional[float]
    reason: Optional[str]
    risk_level: Optional[str]
    referenced_memory: List[str]
    market_regime: Optional[str]
    risk_verdicts: List[dict]
    executions: List[dict]
    latency_ms: dict
    schema_version: str = "replay.v1"


# ==================== 基准组合 ====================


@dataclass
class EqualWeightBenchmark:
    """等权基准组合"""
    nav: Decimal
    constituents: Dict[str, Decimal]  # code -> shares
    last_rebuild_date: str = ""


@dataclass
class CSI300Benchmark:
    """沪深300基准"""
    nav: Decimal
    index_value: Decimal
    last_index_close: Decimal


@dataclass
class BenchmarkPortfolio:
    """基准组合"""
    equal_weight: EqualWeightBenchmark
    csi300: CSI300Benchmark
