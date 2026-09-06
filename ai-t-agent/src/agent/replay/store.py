"""
Replay 不可变存储 + 评估

Replay 必须完全可复现：同输入同配置可完整复现决策与成交。
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from decimal import Decimal

from agent.common.models import TickRecord
from agent.common.logger import get_logger

logger = get_logger("replay.store")


class ReplayStore:
    """不可变 Replay 存储"""

    def __init__(self, base_dir: str = "data/replay"):
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def save_tick(self, date: str, tick: TickRecord) -> None:
        """实时追加 Tick 记录"""
        day_dir = self._base_dir / date
        day_dir.mkdir(exist_ok=True)
        ticks_file = day_dir / "ticks.jsonl"

        record = {
            "tick_id": tick.tick_id,
            "timestamp": tick.timestamp,
            "risk_state": tick.risk_state,
            "context_id": tick.context_id,
            "confidence": tick.confidence,
            "reason": tick.reason,
            "market_regime": tick.market_regime,
            "memory_ids": tick.memory_ids,
            "schema_version": tick.schema_version,
        }

        with open(ticks_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def save_decision_tick(self, date: str, record: dict) -> None:
        """实时追加决策全量快照（Prompt + LLM 原始输出 + 解析结果 + 成交）

        根因调查必需：决策链最关键的证据（模型看到了什么、回了什么）
        必须事后可追溯。存 prompts.jsonl，与 ticks.jsonl 分开。
        """
        try:
            day_dir = self._base_dir / date
            day_dir.mkdir(exist_ok=True)
            with open(day_dir / "prompts.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            logger.error("replay_decision_save_failed", error=str(e))

    def save_daily_summary(self, date: str, summary: dict) -> None:
        """日终汇总"""
        day_dir = self._base_dir / date
        day_dir.mkdir(exist_ok=True)
        summary_file = day_dir / "daily_summary.json"

        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

        logger.info("replay_daily_saved", date=date)

    def load_ticks(self, date: str) -> List[dict]:
        """加载某日所有 Tick"""
        ticks_file = self._base_dir / date / "ticks.jsonl"
        if not ticks_file.exists():
            return []

        ticks = []
        with open(ticks_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    ticks.append(json.loads(line))
        return ticks


@dataclass
class DailyEvaluation:
    """日级评估"""
    date: str
    nav: Decimal
    excess_vs_equal_weight: Decimal
    max_drawdown: float
    fee_ratio: float
    t_trading_pnl: Decimal
    trade_count: int
    halt_count: int
    low_confidence_filter_count: int


class Evaluator:
    """评估指标计算"""

    def compute_daily(self, date: str, nav: Decimal, peak_nav: Decimal,
                      fills_count: int, total_fees: Decimal,
                      t_pnl: Decimal, benchmark_nav: Decimal) -> DailyEvaluation:
        drawdown = float((peak_nav - nav) / peak_nav) if peak_nav > 0 else 0.0
        excess = nav - benchmark_nav
        fee_ratio = float(total_fees / nav) if nav > 0 else 0.0

        return DailyEvaluation(
            date=date,
            nav=nav,
            excess_vs_equal_weight=excess,
            max_drawdown=drawdown,
            fee_ratio=fee_ratio,
            t_trading_pnl=t_pnl,
            trade_count=fills_count,
            halt_count=0,
            low_confidence_filter_count=0,
        )
