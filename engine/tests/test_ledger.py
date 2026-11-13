from datetime import date, datetime
from types import SimpleNamespace as NS

import pytest

from app.ledger import upstox
from app.ledger.positions import build_positions


def test_upstox_parse_skips_preamble_and_derivatives(upstox_csv):
    result = upstox.parse(upstox_csv)
    assert [t.symbol for t in result.trades] == ["RELIANCE.NS", "TCS.NS", "RELIANCE.NS"]
    first = result.trades[0]
    assert (first.side, first.quantity, first.price) == ("BUY", 10, 1250.0)
    assert first.traded_at == datetime(2025, 1, 3, 9, 20, 11)  # day-first dates
    assert len(result.skipped) == 1 and "non-equity" in result.skipped[0]


def test_upstox_bse_maps_to_bo_suffix():
    csv = "Date,Exchange,Scrip Code,Side,Quantity,Price\n02-01-2025,BSE,500325,Buy,1,100\n"
    assert upstox.parse(csv).trades[0].symbol == "500325.BO"


def test_upstox_rejects_unrecognised_file():
    with pytest.raises(ValueError):
        upstox.parse("foo,bar\n1,2\n")


def trade(sym, when, side, qty, price):
    return NS(symbol=sym, traded_at=when, side=side, quantity=qty, price=price)


def action(sym, when, kind, value):
    return NS(symbol=sym, ex_date=when, kind=kind, value=value)


def test_split_dividend_and_fifo_sale():
    trades = [
        trade("X", datetime(2025, 1, 1, 10), "BUY", 10, 100.0),
        trade("X", datetime(2025, 4, 1, 10), "SELL", 5, 60.0),
    ]
    actions = [
        action("X", date(2025, 2, 1), "split", 2.0),      # 10 @ 100 -> 20 @ 50
        action("X", date(2025, 3, 1), "dividend", 2.0),   # 20 * 2 = 40
    ]
    pos = build_positions(trades, actions)["X"]
    assert pos.quantity == pytest.approx(15)
    assert pos.avg_cost == pytest.approx(50.0)
    assert pos.realized_pnl == pytest.approx(50.0)        # 5 * (60 - 50)
    assert pos.dividends == pytest.approx(40.0)


def test_bonus_keeps_total_cost_and_fifo_order():
    trades = [
        trade("X", datetime(2025, 1, 1, 10), "BUY", 10, 100.0),
        trade("X", datetime(2025, 1, 2, 10), "BUY", 10, 200.0),
        trade("X", datetime(2025, 3, 1, 10), "SELL", 30, 90.0),
    ]
    actions = [action("X", date(2025, 2, 1), "bonus", 2.0)]  # 1:1 bonus
    pos = build_positions(trades, actions)["X"]
    # lots become 20 @ 50 and 20 @ 100 ; sell 20 @ 50 then 10 @ 100
    assert pos.realized_pnl == pytest.approx(20 * 40 + 10 * -10)
    assert pos.quantity == pytest.approx(10) and pos.avg_cost == pytest.approx(100.0)


def test_action_before_purchase_does_not_apply_and_oversell_warns():
    trades = [
        trade("X", datetime(2025, 3, 1, 10), "BUY", 10, 100.0),
        trade("X", datetime(2025, 3, 2, 10), "SELL", 12, 110.0),
    ]
    actions = [action("X", date(2025, 2, 1), "split", 2.0), action("X", date(2025, 2, 1), "dividend", 5.0)]
    pos = build_positions(trades, actions)["X"]
    assert pos.dividends == 0 and pos.quantity == pytest.approx(0)
    assert pos.realized_pnl == pytest.approx(100.0)
    assert len(pos.warnings) == 1
