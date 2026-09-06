"""
工具函数（时间、哈希、ID 生成等）
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any

# 东八区
TZ_CST = timezone(timedelta(hours=8))


def now_cst() -> datetime:
    """当前东八区时间"""
    return datetime.now(TZ_CST)


def today_str() -> str:
    """今日日期字符串 YYYY-MM-DD"""
    return now_cst().strftime("%Y-%m-%d")


def gen_tick_id() -> str:
    """生成 Tick ID: tick_YYYYMMDD_HHMMSS"""
    return f"tick_{now_cst().strftime('%Y%m%d_%H%M%S')}"


def gen_id(prefix: str = "") -> str:
    """生成唯一 ID"""
    uid = uuid.uuid4().hex[:12]
    return f"{prefix}_{uid}" if prefix else uid


def gen_fill_id() -> str:
    return gen_id("fill")


def gen_order_id() -> str:
    return gen_id("order")


def gen_task_id() -> str:
    return gen_id("task")


def gen_memory_id(date: str, seq: int) -> str:
    """生成 Memory ID: mem_YYYYMMDD_SEQ"""
    return f"mem_{date.replace('-', '')}_{seq:03d}"


def gen_context_id() -> str:
    """生成 Context ID: ctx_YYYYMMDD_HHMMSS"""
    return f"ctx_{now_cst().strftime('%Y%m%d_%H%M%S')}"


def compute_hash(data: Any) -> str:
    """计算对象的 SHA256 哈希（用于 Replay 校验）"""
    if isinstance(data, (dict, list)):
        content = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    else:
        content = str(data)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def decimal_round(value: Decimal, places: int = 2) -> Decimal:
    """Decimal 四舍五入到指定小数位"""
    quantize_str = "0." + "0" * places
    return value.quantize(Decimal(quantize_str))


def pct_change(current: Decimal, previous: Decimal) -> float:
    """计算百分比变化"""
    if previous == 0:
        return 0.0
    return float((current - previous) / previous)
