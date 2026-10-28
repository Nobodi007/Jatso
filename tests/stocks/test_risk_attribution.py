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


def test_execution_and_fees_are_split_but_still_reconcile():
    trades, cal, px, nav = _setup()
    out = A.attribution(trades, cal, px, nav)
    assert out["execution_and_fees"]["value"] == pytest.approx(out["execution"]["value"] + out["fees"]["value"], abs=1e-15)
    assert out["fees"]["value"] < 0                                   # มีค่าธรรมเนียมจริงในสถานการณ์ทดสอบ
    sc = out["sum_check"]
    assert sc["ok"] and sc["execution"] == out["execution"]["value"] and sc["fees"] == out["fees"]["value"]
    # ไม่มีค่าธรรมเนียม: fees = 0 และผลรวมยังตรง
    free = [L.Trade(t.id, t.symbol, t.side, t.qty, t.price, 0.0, t.ts, t.session_date) for t in trades]
    nav0, _ = L.build_nav(free, 100000.0, cal, {s: dict(zip(cal, v)) for s, v in px.items()})
    z = A.attribution(free, cal, px, nav0)
    assert z["fees"]["value"] == 0.0 and z["sum_check"]["ok"]


def test_cash_drag_simple_case_and_fully_invested_identity():
    cal = _cal(3)
    prices = {"AAA": [100.0, 110.0, 110.0]}
    closes = {"AAA": dict(zip(cal, prices["AAA"]))}
    rows = [{"id": 1, "symbol": "AAA", "side": "buy", "qty": 5, "fee": 0, "price": 100.0,
             "ts": f"{cal[0].isoformat()}T15:00:00+00:00"}]
    trades = L.to_trades(rows)
    nav, _ = L.build_nav(trades, 1000.0, cal, closes)
    out = A.attribution(trades, cal, {"AAA": prices["AAA"]}, nav)
    # วันที่ 1: เงินสด 50% ของ NAV หุ้นขึ้น 10% → ส่วนร่วมของหุ้น +5pp, cash drag −5pp
    assert out["positions"][0]["contribution"] == pytest.approx(0.05)
    assert out["cash_drag"]["value"] == pytest.approx(-0.05) and out["cash_drag"]["memo"] is True
    assert 0.47 < out["cash_drag"]["avg_cash_weight"] < 0.5
    # ถ้าลงทุนเต็ม: ส่วนร่วม = positions − cash_drag = ผลตอบแทนหุ้น 10%
    assert out["positions"][0]["contribution"] - out["cash_drag"]["value"] == pytest.approx(0.10)
    assert out["sum_check"]["ok"]


def test_pnl_breakdown_reconciles_to_nav_change():
    trades, cal, px, nav = _setup()
    prices = {s: v[-1] for s, v in px.items()}
    out = A.pnl_breakdown(L.positions(trades), prices, 100000.0, nav[-1].nav)
    assert out["check"]["ok"] and abs(out["check"]["difference"]) < 0.01
    assert out["total_net"] == pytest.approx(out["realized_gross"] + out["unrealized"] - out["fees_paid"])
    by = {r["symbol"]: r for r in out["symbols"]}
    assert by["BBB"]["unrealized"] == 0.0 and by["BBB"]["open_qty"] == 0 and by["BBB"]["avg_cost"] is None   # ขายหมดแล้ว
    assert by["AAA"]["unrealized"] is not None and by["AAA"]["fees"] == pytest.approx(1.5 + 2 + 2)


def test_pnl_breakdown_missing_price_is_incomplete_not_guessed():
    trades, cal, px, nav = _setup()
    prices = {s: v[-1] for s, v in px.items()}
    prices["AAA"] = None
    out = A.pnl_breakdown(L.positions(trades), prices, 100000.0, nav[-1].nav)
    assert out["incomplete_symbols"] == ["AAA"] and "check" not in out
    assert {r["symbol"]: r["unrealized"] for r in out["symbols"]}["AAA"] is None


def test_by_sector_sums_to_position_total_and_buckets_unknown():
    trades, cal, px, nav = _setup()
    out = A.attribution(trades, cal, px, nav)
    sec = A.by_sector(out["positions"], {"AAA": "Tech", "CCC": "Tech", "BBB": None})
    assert {r["sector"] for r in sec} == {"Tech", "Unknown"}
    assert sum(r["contribution"] for r in sec) == pytest.approx(out["sum_check"]["positions"], abs=1e-12)
    assert next(r for r in sec if r["sector"] == "Tech")["symbols"] == ["AAA", "CCC"]
    assert sec[0]["contribution"] >= sec[-1]["contribution"]
