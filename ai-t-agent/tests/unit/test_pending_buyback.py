"""跨日未接回：成交维护、落盘、日切不丢。"""
from decimal import Decimal
from pathlib import Path

from agent.common.models import ActionType, FeeDetail, Fill, OrderIntent, OrderSource
from agent.config.schema import AppConfig
from agent.trading.account import Account
from agent.trading.engine import TradingEngine
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))


def _fill(action, shares, price, code="002185"):
    px = Decimal(str(price))
    return Fill(
        fill_id="f1", order_id="o1", code=code, action=action,
        shares=shares, price=px, amount=px * shares, fee=Decimal("5"),
        fee_detail=FeeDetail(Decimal("5"), Decimal("0"), Decimal("0")),
        realized_pnl=None,
        timestamp=datetime(2026, 9, 7, 9, 36, tzinfo=TZ),
        tick_id="t",
    )


def test_sell_then_partial_buy_keeps_avg(tmp_path: Path):
    acc = Account()
    acc.apply_fill_to_pending(_fill(ActionType.SELL, 300, "15.88"))
    rec = acc.pending_buyback["002185"]
    assert rec.shares == 300
    assert rec.sell_avg == Decimal("15.88")
    acc.apply_fill_to_pending(_fill(ActionType.BUY, 100, "15.80"))
    rec = acc.pending_buyback["002185"]
    assert rec.shares == 200
    assert rec.sell_avg == Decimal("15.88")
    assert acc.buyback_bought_today["002185"] == 100
    acc.apply_fill_to_pending(_fill(ActionType.BUY, 200, "15.70"))
    assert "002185" not in acc.pending_buyback
    assert acc.buyback_bought_today["002185"] == 300


def test_pending_survives_save_load_and_day_start(tmp_path: Path):
    path = tmp_path / "state.json"
    acc = Account()
    acc.apply_fill_to_pending(_fill(ActionType.SELL, 300, "15.88"))
    acc.save(str(path))

    loaded = Account()
    assert loaded.load(str(path))
    rec = loaded.pending_buyback["002185"]
    assert rec.shares == 300
    assert rec.sell_avg == Decimal("15.88")

    engine = TradingEngine(AppConfig())
    engine.account = loaded
    engine.today_fills = [_fill(ActionType.SELL, 300, "15.88")]
    engine.on_day_start("2026-09-08", {}, watchlist_changed=False)
    assert engine.today_fills == []
    assert engine.account.pending_buyback["002185"].shares == 300
    assert engine.account.buyback_bought_today == {}


def test_decision_sell_updates_pending_stop_loss_clears():
    engine = TradingEngine(AppConfig())
    fill = _fill(ActionType.SELL, 300, "15.88")
    intent = OrderIntent(
        intent_id="i1", action=ActionType.SELL, code="002185",
        shares=300, source=OrderSource.DECISION,
    )
    engine._update_pending(fill, intent)
    assert engine.account.pending_buyback["002185"].shares == 300
    sl = OrderIntent(
        intent_id="i2", action=ActionType.SELL, code="002185",
        shares=300, source=OrderSource.STOP_LOSS,
    )
    engine._update_pending(fill, sl)
    assert "002185" not in engine.account.pending_buyback
