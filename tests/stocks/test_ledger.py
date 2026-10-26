import asyncio
from datetime import date

import pytest

from stocks import ledger as L

row = lambda i, s, side, q, p, f, ts: dict(id=i, symbol=s, side=side, qty=q, price=p, fee=f, ts=ts)

def test_session_cutoff_et():
    assert L.session_date(L.parse_ts("2026-10-22T18:28:11.94+00:00")) == date(2026, 10, 22)
    assert L.session_date(L.parse_ts("2026-10-22T20:30:00+00:00")) == date(2026, 10, 23)

def test_naive_ts_rejected():
    with pytest.raises(L.LedgerError):
        L.to_trades([row(1, "A", "buy", 1, 1, 0, "2026-01-01T10:00:00")])

def test_split_adjustment():
    t = L.to_trades([row(1, "NVDA", "buy", 10, 1000, 0, "2024-06-03T15:00:00Z")])
    a = L.adjust_for_splits(t, {"NVDA": [(date(2024, 6, 10), 10.0)]})[0]
    assert a.qty == pytest.approx(100) and a.price == pytest.approx(100)
    t2 = L.to_trades([row(2, "NVDA", "buy", 10, 120, 0, "2024-06-10T15:00:00Z")])
    assert L.adjust_for_splits(t2, {"NVDA": [(date(2024, 6, 10), 10.0)]})[0].qty == 10

def test_split_after_hours_before_exdate():
    t = L.to_trades([row(1, "X", "buy", 1, 1000, 0, "2026-10-22T21:00:00Z")])   # 17:00 ET, pre-split price
    a = L.adjust_for_splits(t, {"X": [(date(2026, 10, 23), 10.0)]})[0]
    assert a.qty == pytest.approx(10) and a.price == pytest.approx(100)

def test_nav_series():
    t = L.to_trades([row(1, "AAA", "buy", 5, 100, 1, "2026-03-03T15:00:00Z")])
    cal = [date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 4)]
    pts, issues = L.build_nav(t, 1000.0, cal, {"AAA": {cal[1]: 110.0, cal[2]: 121.0}})
    assert [p.nav for p in pts] == [pytest.approx(1000), pytest.approx(1049), pytest.approx(1104)]
    assert issues == []

def test_missing_price_marks_nav_unavailable():
    t = L.to_trades([row(1, "AAA", "buy", 1, 100, 0, "2026-03-03T15:00:00Z")])
    pts, issues = L.build_nav(t, 1000.0, [date(2026, 3, 3)], {})
    assert pts[0].nav is None and issues[0]["code"] == "missing_price"

def test_oversell_raises():
    t = L.to_trades([row(1, "A", "buy", 1, 10, 0, "2026-03-03T15:00:00Z"),
                     row(2, "A", "sell", 2, 10, 0, "2026-03-03T16:00:00Z")])
    with pytest.raises(L.LedgerError):
        L.positions(t)

def test_replay_cash():
    t = L.to_trades([row(1, "A", "buy", 2, 10, 1, "2026-03-03T15:00:00Z"),
                     row(2, "A", "sell", 1, 12, 1, "2026-03-04T15:00:00Z")])
    assert L.replay_cash(t, 100.0) == pytest.approx(100 - 21 + 11)

def test_active_trades_user_scoped(monkeypatch):
    from stocks import risk_data as rd
    calls = []
    async def fake_sb(method, table, params=None, json=None):
        calls.append((method, table, params)); return []
    monkeypatch.setattr(rd, "sb", fake_sb)
    asyncio.run(rd.active_trades("a@example.com"))
    _, table, p = calls[0]
    assert table == "stock_trades" and p["email"] == "eq.a@example.com" and p["voided_at"] == "is.null"
