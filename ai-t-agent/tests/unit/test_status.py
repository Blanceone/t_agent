"""CLI status：持仓现价 + 最近10笔成交"""

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from agent.common.models import Position, PositionState, Quote, WatchlistEntry
from agent.trading.account import Account
from agent.trading.status import (
    format_cst,
    format_status,
    load_recent_trades,
    parse_recent_trades,
    parse_trade_record,
    quote_last,
)


def _fill_line(ts, action="BUY", code="002185", shares=100, price="16.49", fee="5.02"):
    return json.dumps({
        "module": "trading.engine",
        "code": code,
        "action": action,
        "shares": shares,
        "price": price,
        "fee": fee,
        "event": "order_filled",
        "timestamp": ts,
    }, ensure_ascii=False)


def _account():
    acc = Account(account_id="sim_001", initial_cash=Decimal("10000"))
    acc.watchlist["002185"] = WatchlistEntry(code="002185", added_at="2026-08-01")
    acc.watchlist["601918"] = WatchlistEntry(code="601918", added_at="2026-08-01")
    acc.positions["002185"] = Position(
        code="002185",
        total_shares=300,
        sellable_shares=0,
        today_bought=100,
        cost_price=Decimal("16.1968"),
        stop_loss_price=Decimal("14.90"),
        position_state=PositionState.ACTIVE,
    )
    return acc


def _quote(code, last):
    return Quote(
        code=code, name="", last=Decimal(str(last)),
        bid1=Decimal(str(last)), ask1=Decimal(str(last)),
        high=Decimal(str(last)), low=Decimal(str(last)),
        open=Decimal(str(last)), pre_close=Decimal(str(last)),
        limit_up=Decimal("20"), limit_down=Decimal("10"),
        volume=0, turnover=Decimal("0"), vwap=Decimal(str(last)),
        is_suspended=False, is_st=False,
        timestamp=datetime(2026, 9, 4, 10, 0, 0),
    )


class TestParseTrades:
    def test_utc_to_cst(self):
        assert format_cst("2026-08-25T01:30:07.934493Z") == "2026-08-25 09:30:07"

    def test_parse_fill(self):
        op = parse_trade_record(json.loads(_fill_line("2026-09-04T02:33:00Z")))
        assert op is not None
        assert op.code == "002185"
        assert op.action == "买入"
        assert op.shares == 100
        assert op.price == "16.49"
        assert op.result == "成交成功 费用5.02"
        assert op.timestamp == "2026-09-04 10:33:00"

    def test_ignore_non_fill(self):
        rec = {"event": "decision_risk_rejected", "code": "002185", "action": "SELL"}
        assert parse_trade_record(rec) is None

    def test_keep_last_10(self):
        lines = [
            _fill_line(f"2026-09-01T01:{i:02d}:00Z", shares=100 + i)
            for i in range(12)
        ]
        trades = parse_recent_trades(lines, limit=10)
        assert len(trades) == 10
        assert trades[0].shares == 102
        assert trades[-1].shares == 111

    def test_skip_bad_json(self):
        lines = ["not json", _fill_line("2026-09-04T01:30:00Z")]
        trades = parse_recent_trades(lines)
        assert len(trades) == 1
        assert trades[0].action == "买入"


class TestLoadRecentTrades:
    def test_from_file_tail(self, tmp_path: Path):
        log = tmp_path / "agent.log"
        rows = ["{\"event\":\"tick\"}"]
        for i in range(15):
            rows.append(_fill_line(
                f"2026-09-04T01:{i:02d}:00Z",
                action="SELL" if i % 2 else "BUY",
                shares=100 + i,
                price=f"16.{i:02d}",
            ))
        log.write_text("\n".join(rows) + "\n", encoding="utf-8")
        trades = load_recent_trades(log, limit=10)
        assert len(trades) == 10
        assert trades[0].shares == 105
        assert trades[-1].shares == 114
        assert trades[-1].action == "买入"

    def test_missing_file(self, tmp_path: Path):
        assert load_recent_trades(tmp_path / "nope.log") == []


class TestFormatStatus:
    def test_positions_and_watchlist_show_last_price(self):
        acc = _account()
        quotes = {
            "002185": _quote("002185", "16.36"),
            "601918": _quote("601918", "8.21"),
        }
        text = format_status(acc, quotes, [])
        assert "002185: 现价16.36" in text
        assert "601918: 现价8.21" in text
        assert "成本16.1968, 现价16.36, 状态ACTIVE" in text
        assert "（暂无成交记录）" in text

    def test_missing_quote_shows_dash(self):
        acc = _account()
        text = format_status(acc, {}, [])
        assert "现价-" in text
        assert quote_last({}, "002185") == "-"

    def test_recent_trades_section(self):
        acc = _account()
        trades = parse_recent_trades([
            _fill_line("2026-09-04T01:30:00Z", "SELL", shares=200, price="16.50", fee="6.68"),
            _fill_line("2026-09-04T02:33:00Z", "BUY", shares=100, price="16.49", fee="5.02"),
        ])
        text = format_status(acc, {}, trades)
        assert "2026-09-04 09:30:00  002185  卖出  200股 @16.50  结果:成交成功 费用6.68" in text
        assert "2026-09-04 10:33:00  002185  买入  100股 @16.49  结果:成交成功 费用5.02" in text
