import datetime as dt
import random

import pytest

from stocks import ledger as L
from stocks import risk_attribution as A


def _cal(n):
    out, d = [], dt.date(2026, 1, 5)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def _setup(seed=11, n=120):
    random.seed(seed)
    cal = _cal(n)
    prices = {}
    for s, p0, sd in (("AAA", 100, .012), ("BBB", 40, .02), ("CCC", 250, .015)):
        p = [float(p0)]
        for _ in range(1, n):
            p.append(p[-1] * (1 + random.gauss(0.0003, sd)))
        prices[s] = p
    closes = {s: dict(zip(cal, v)) for s, v in prices.items()}

    def tr(i, s, side, q, k, fee, hour=15):
        return {"id": i, "symbol": s, "side": side, "qty": q, "fee": fee,
                "price": prices[s][k] * (1 + random.uniform(-0.01, 0.01)),
                "ts": f"{cal[k].isoformat()}T{hour:02d}:00:00+00:00"}

    rows = [tr(1, "AAA", "buy", 100, 0, 1.5), tr(2, "BBB", "buy", 300, 0, 0), tr(3, "AAA", "buy", 50, 20, 2),
            tr(4, "CCC", "buy", 20, 30, 1), tr(5, "BBB", "sell", 300, 50, 3),
            tr(6, "CCC", "buy", 10, 50, 0), tr(7, "CCC", "sell", 10, 50, 1),      # same-day round trip
            tr(8, "AAA", "sell", 60, 90, 2)]
    trades = L.to_trades(rows)
    nav, issues = L.build_nav(trades, 100000.0, cal, closes)
    assert issues == []
    px = {s: [closes[s].get(c) for c in cal] for s in prices}
    return trades, cal, px, nav


def test_attribution_reconciles_to_portfolio_return():
    trades, cal, px, nav = _setup()
    out = A.attribution(trades, cal, px, nav)
    sc = out["sum_check"]
    assert sc["ok"] and abs(sc["residual"]) < 1e-9
    assert out["portfolio_return"] == pytest.approx(nav[-1].nav / nav[0].nav - 1, rel=1e-12)
    assert out["partial"] is True
    assert {r["symbol"] for r in out["positions"]} == {"AAA", "BBB", "CCC"}


def test_attribution_flags_held_now():
    trades, cal, px, nav = _setup()
    held = {r["symbol"]: r["held_now"] for r in A.attribution(trades, cal, px, nav)["positions"]}
    assert held == {"AAA": True, "BBB": False, "CCC": True}   # BBB fully sold; CCC round trip left 20 held


def test_attribution_rejects_missing_price_and_bad_nav():
    trades, cal, px, nav = _setup()
    bad = dict(px)
    bad["AAA"] = [None] * len(cal)
    with pytest.raises(ValueError):
        A.attribution(trades, cal, bad, nav)
    with pytest.raises(ValueError):
        A.attribution(trades, cal[:1], px, nav[:1])
