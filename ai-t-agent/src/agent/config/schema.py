"""
配置 Pydantic Schema 定义

所有 Magic Number 必须配置化，禁止在代码中写死关键阈值。
"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class FeeConfig(BaseModel):
    """费用参数"""
    stamp_tax_rate: Decimal = Decimal("0.0005")       # 印花税 0.05%（仅卖出）
    transfer_fee_rate: Decimal = Decimal("0.00001")   # 过户费 0.001%
    commission_rate: Decimal = Decimal("0.00025")     # 佣金万2.5
    min_commission: Decimal = Decimal("5")            # 最低佣金5元


class RiskConfig(BaseModel):
    """风控参数"""
    stop_loss_ratio: Decimal = Decimal("0.92")
    enable_deep_stop_loss: bool = False
    deep_stop_loss_threshold: Decimal = Decimal("0.98")
    stop_breach_confirm_count: int = 2
    day_loss_halt_ratio: Decimal = Decimal("0.03")
    realized_loss_halt_abs: Decimal = Decimal("500")
    max_drawdown_liquidate: Decimal = Decimal("0.10")
    reserved_min_cash_ratio: Decimal = Decimal("0.20")
    max_single_position_ratio: Decimal = Decimal("1.00")
    decision_confidence_threshold: float = 0.60
    enforce_intraday_buy_limit: bool = False


class TradingConfig(BaseModel):
    """交易参数"""
    initial_cash: Decimal = Decimal("30000")
    watchlist_limit: int = 20
    max_liquidation_attempts: int = 30
    max_liquidation_shares_per_tick: int = 10000
    stale_quote_threshold_sec: int = 5


class SchedulerConfig(BaseModel):
    """调度参数"""
    tick_interval_sec: int = 60
    day_start_time: str = "09:20"
    session_am_start: str = "09:30"
    session_am_end: str = "11:30"
    session_pm_start: str = "13:00"
    session_pm_end: str = "14:57"
    day_close_time: str = "15:05"


class LLMConfig(BaseModel):
    """LLM 参数"""
    provider: str = "openai"
    model: str = "gpt-4o"
    api_key_env: str = "LLM_API_KEY"
    base_url_env: str = "LLM_BASE_URL"
    timeout_ms: int = 30000
    max_retries: int = 1
    temperature: float = 0.1
    extra_body: Optional[dict] = None


class PromptConfig(BaseModel):
    """Prompt 版本"""
    decision_version: str = "decision.v2.30"
    reflection_version: str = "reflection.v1.0"
    planner_version: str = "planner.v1.9"
    market_understanding_version: str = "market_understanding.v1.1"


class MemoryConfig(BaseModel):
    """Memory 参数"""
    memory_top_k: int = 8
    memory_inject_max_tokens: int = 1500
    memory_compress_after_days: int = 30
    db_path: str = "data/memory/memory.db"


class MarketConfig(BaseModel):
    """行情参数"""
    data_source: str = "tencent"  # tencent（主）/ akshare / tushare
    tushare_token_env: str = "TUSHARE_TOKEN"


class FeatureConfig(BaseModel):
    """Feature 计算参数"""
    volume_ratio_lookback_days: int = 5
    chg_pct_5d_lookback: int = 5
    chg_pct_10d_lookback: int = 10
    round_trip_est_shares: int = 100


class DecisionConfig(BaseModel):
    """决策引擎参数"""
    confidence_threshold: float = 0.60
    max_decision_retries: int = 1
    context_max_tokens: int = 4000
    hold_on_failure: bool = True


class ReplayConfig(BaseModel):
    """Replay 参数"""
    retention_days: int = 90
    compress_after_days: int = 30
    save_tick_realtime: bool = True
    evaluation_benchmark: str = "equal_weight"


class ReflectionConfig(BaseModel):
    """复盘参数"""
    enable_llm_analysis: bool = True
    max_memory_candidates: int = 5


class AppConfig(BaseModel):
    """顶层配置"""
    env: str = "dev"
    fee: FeeConfig = Field(default_factory=FeeConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    prompt: PromptConfig = Field(default_factory=PromptConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    market: MarketConfig = Field(default_factory=MarketConfig)
    feature: FeatureConfig = Field(default_factory=FeatureConfig)
    decision: DecisionConfig = Field(default_factory=DecisionConfig)
    replay: ReplayConfig = Field(default_factory=ReplayConfig)
    reflection: ReflectionConfig = Field(default_factory=ReflectionConfig)
    log_level: str = "INFO"
    data_dir: str = "data"
