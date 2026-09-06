"""
CLI `agent status` 报告：账户/持仓/股票池现价 + 最近成交。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from agent.common.utils import TZ_CST
from agent.config.schema import AppConfig

RECENT_TRADE_LIMIT = 10
_TRADE_EVENTS = {"order_filled"}
_ACTION_LABEL = {"BUY": "买入", "SELL": "卖出"}


@dataclass(frozen=True)
class TradeOp:
    timestamp: str
    code: str
    action: str
    shares: int
    price: str
    result: str


def format_cst(ts: str) -> str:
    """ISO 时间戳转为东八区 `YYYY-MM-DD HH:MM:SS`。解析失败则原样返回。"""
    raw = (ts or "").strip()
    if not raw:
        return "-"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ_CST)
        return dt.astimezone(TZ_CST).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return raw


def parse_trade_record(rec: dict) -> Optional[TradeOp]:
    if rec.get("event") not in _TRADE_EVENTS:
        return None
    code = rec.get("code")
    action = rec.get("action")
    price = rec.get("price")
    if not code or not action or price in (None, ""):
        return None
    try:
        shares = int(rec.get("shares") or 0)
    except (TypeError, ValueError):
        shares = 0
    fee = rec.get("fee")
    result = "成交成功"
    if fee not in (None, ""):
        result = f"成交成功 费用{fee}"
    return TradeOp(
        timestamp=format_cst(str(rec.get("timestamp") or "")),
        code=str(code),
        action=_ACTION_LABEL.get(str(action), str(action)),
        shares=shares,
        price=str(price),
        result=result,
    )


def parse_recent_trades(lines: Iterable[str], limit: int = RECENT_TRADE_LIMIT) -> List[TradeOp]:
    """从旧到新的 JSONL 行中取最近 limit 笔成交（输入可为任意顺序，结果按时间正序）。"""
    found: List[TradeOp] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        op = parse_trade_record(rec)
        if op is None:
            continue
        found.append(op)
    return found[-limit:]


def _iter_lines_reversed(path: Path, chunk_size: int = 65536):
    with open(path, "rb") as f:
        f.seek(0, 2)
        remaining = f.tell()
        leftover = b""
        while remaining > 0:
            read_size = min(chunk_size, remaining)
            remaining -= read_size
            f.seek(remaining)
            data = f.read(read_size) + leftover
            parts = data.split(b"\n")
            leftover = parts[0]
            for line in reversed(parts[1:]):
                if line.strip():
                    yield line.decode("utf-8", errors="replace")
        if leftover.strip():
            yield leftover.decode("utf-8", errors="replace")


def load_recent_trades(log_path: Path, limit: int = RECENT_TRADE_LIMIT) -> List[TradeOp]:
    if not log_path.is_file():
        return []
    found: List[TradeOp] = []
    for line in _iter_lines_reversed(log_path):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        op = parse_trade_record(rec)
        if op is None:
            continue
        found.append(op)
        if len(found) >= limit:
            break
    found.reverse()
    return found


def quote_last(quotes: dict, code: str) -> str:
    q = quotes.get(code) if quotes else None
    if q is None:
        return "-"
    last = getattr(q, "last", None)
    return str(last) if last is not None else "-"


def fetch_quotes(config: AppConfig, codes: List[str]) -> dict:
    """拉取股票清单现价；失败返回空 dict，不阻断 status。"""
    if not codes:
        return {}
    try:
        from agent.market.service import MarketService
        market = MarketService(config)
        market.set_watchlist(codes)
        return market.refresh() or {}
    except Exception:
        return {}


def format_status(account, quotes: Optional[dict] = None, trades: Optional[List[TradeOp]] = None) -> str:
    quotes = quotes or {}
    trades = trades or []
    lines = [
        "=" * 50,
        f"账户: {account.account_id}",
        f"可用现金: {account.cash.available}",
        f"上次净值: {account.last_nav}",
        f"峰值净值: {account.peak_nav}",
        f"风控状态: {account.risk_state.value}",
        "股票池:",
    ]
    if account.watchlist:
        for code in account.watchlist:
            lines.append(f"  {code}: 现价{quote_last(quotes, code)}")
    else:
        lines.append("  （空）")

    lines.append("持仓:")
    if account.positions:
        for code, pos in account.positions.items():
            lines.append(
                f"  {code}: {pos.total_shares}股, 可卖{pos.sellable_shares}, "
                f"成本{pos.cost_price}, 现价{quote_last(quotes, code)}, "
                f"状态{pos.position_state.value}"
            )
    else:
        lines.append("  （无持仓）")

    if account.liquidation_queue:
        lines.append(f"清仓队列: {[t.code for t in account.liquidation_queue]}")

    lines.append("最近交易:")
    if trades:
        for op in trades:
            lines.append(
                f"  {op.timestamp}  {op.code}  {op.action}  "
                f"{op.shares}股 @{op.price}  结果:{op.result}"
            )
    else:
        lines.append("  （暂无成交记录）")
    lines.append("=" * 50)
    return "\n".join(lines)
