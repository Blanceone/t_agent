"""
统一错误码（Error Code）

所有模块统一返回 Error Code，方便日志、测试、排查。
规则：
- 所有异常必须携带 ErrorCode
- 错误码不可复用
- 扩展按模块段递增（通用 0xx、交易 1xx、风控 2xx、调度 3xx、记忆 4xx、复盘 5xx）
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ErrorCode(Enum):
    """统一错误码"""

    # === 通用 ===
    E001 = "SCHEMA_VALIDATION_FAILED"
    E002 = "LLM_TIMEOUT"
    E003 = "RISK_REJECT"
    E004 = "REPLAY_FAILED"
    E005 = "QUOTE_TIMEOUT"
    E006 = "MEMORY_RETRIEVE_FAILED"
    E007 = "CONFIG_LOAD_FAILED"
    E008 = "ACCOUNT_PERSIST_FAILED"
    E009 = "CONTEXT_ASSEMBLE_FAILED"
    E010 = "EVENT_EMIT_FAILED"

    # === 交易 ===
    E101 = "MATCH_FAILED"
    E102 = "FEE_CALC_ERROR"
    E103 = "LIQUIDATION_EXHAUSTED"
    E104 = "POSITION_STATE_INVALID"
    E105 = "BENCHMARK_REBUILD_FAILED"

    # === 风控 ===
    E201 = "HALT_TRIGGERED"
    E202 = "LIQUIDATE_TRIGGERED"
    E203 = "STOP_LOSS_TRIGGERED"
    E204 = "CONFIDENCE_TOO_LOW"
    E205 = "CASH_RESERVE_BREACH"
    E206 = "POSITION_LIMIT_BREACH"

    # === 调度 ===
    E301 = "TICK_TIMEOUT"
    E302 = "SCHEDULER_CRASH"
    E303 = "CALENDAR_ERROR"
    E304 = "WATCHDOG_RESTART"

    # === 记忆 ===
    E401 = "MEMORY_WRITE_FAILED"
    E402 = "MEMORY_COMPRESS_FAILED"
    E403 = "MEMORY_STORE_CORRUPT"

    # === 复盘 ===
    E501 = "STATS_MISMATCH"
    E502 = "REFLECTION_LLM_FAILED"
    E503 = "REPORT_GENERATE_FAILED"


@dataclass
class AgentError(Exception):
    """统一异常基类"""
    code: ErrorCode
    message: str
    module: str
    tick_id: Optional[str] = None
    detail: Optional[dict] = field(default=None)

    def __str__(self) -> str:
        parts = [f"[{self.code.name}] {self.module}: {self.message}"]
        if self.tick_id:
            parts.append(f"tick={self.tick_id}")
        if self.detail:
            parts.append(f"detail={self.detail}")
        return " | ".join(parts)

    def __post_init__(self):
        super().__init__(str(self))


class SchemaValidationError(AgentError):
    """Schema 校验失败"""
    def __init__(self, message: str, module: str, **kwargs):
        super().__init__(code=ErrorCode.E001, message=message, module=module, **kwargs)


class LLMTimeoutError(AgentError):
    """LLM 调用超时"""
    def __init__(self, message: str, module: str = "llm", **kwargs):
        super().__init__(code=ErrorCode.E002, message=message, module=module, **kwargs)


class QuoteTimeoutError(AgentError):
    """行情超时/缺失"""
    def __init__(self, message: str, module: str = "market", **kwargs):
        super().__init__(code=ErrorCode.E005, message=message, module=module, **kwargs)


class AccountPersistError(AgentError):
    """账户持久化失败"""
    def __init__(self, message: str, module: str = "trading", **kwargs):
        super().__init__(code=ErrorCode.E008, message=message, module=module, **kwargs)


class MatchFailedError(AgentError):
    """撮合失败"""
    def __init__(self, message: str, module: str = "trading", **kwargs):
        super().__init__(code=ErrorCode.E101, message=message, module=module, **kwargs)


class LiquidationExhaustedError(AgentError):
    """清仓重试耗尽"""
    def __init__(self, message: str, module: str = "trading", **kwargs):
        super().__init__(code=ErrorCode.E103, message=message, module=module, **kwargs)
