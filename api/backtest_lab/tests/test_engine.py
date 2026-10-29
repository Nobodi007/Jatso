import copy
from datetime import date

import pytest

from backtest_lab.data.validate import DataError
from backtest_lab.engine.runner import run_backtest
from backtest_lab.tests.helpers import mk_bars, spec

N = 140
BENCH = mk_bars("2023-12-28", N + 5, lambda i: 100 * 1.0005 ** i)
S, E = "2024-01-02", "2024-06-28"


def cal_dates(res):
    return [s["date"] for s in res["series"]]


def test_buy_and_hold_single_stock_known_value():
    a = mk_bars("2023-12-28", N + 5, lambda i: 50 * 1.002 ** i)
    r = run_backtest(spec([{"symbol": "AAA", "weight": 1.0}], S, E), {"AAA": a}, BENCH)
    d0 = r["period"]["first_trade_date"]
    p0 = next(b["open"] for b in a if b["date"] == d0)
    pl = next(b["close"] for b in a if b["date"] == r["period"]["last_date"])
    assert r["stats"]["final_value"] == pytest.approx(100000 * pl / p0, rel=1e-12)
    assert r["stats"]["trade_count"] == 0 and r["stats"]["rebalance_count"] == 0
    assert r["stats"]["final_value"] == pytest.approx(r["stats"]["buy_hold_final_value"], rel=1e-12)


def test_costs_exact():
    a = mk_bars("2023-12-28", N + 5, lambda i: 50 * 1.002 ** i)
    sp = spec([{"symbol": "AAA", "weight": 1.0}], S, E, costs={"commission_bps": 10, "slippage_bps": 20})
    r = run_backtest(sp, {"AAA": a}, BENCH)
    p0 = next(b["open"] for b in a if b["date"] == r["period"]["first_trade_date"])
    px = p0 * 1.002
    qty = 100000 / (px * 1.001)
    assert r["trades"][0]["shares"] == pytest.approx(qty, rel=1e-12) and r["trades"][0]["reason"] == "initial"
    assert r["stats"]["commission_paid"] == pytest.approx(qty * px * 0.001, rel=1e-9)
    assert r["stats"]["slippage_cost"] == pytest.approx(qty * p0 * 0.002, rel=1e-9)
    pl = next(b["close"] for b in a if b["date"] == r["period"]["last_date"])
    assert r["stats"]["final_value"] == pytest.approx(qty * pl, rel=1e-9)        # เงินสดเหลือ 0 พอดี
    assert r["stats"]["final_value"] < 100000 * pl / p0                          # ต้นทุนทำให้น้อยกว่า


def test_cash_weight_earns_nothing_and_time_in_market():
    flat = mk_bars("2023-12-28", N + 5, lambda i: 100.0)
    r = run_backtest(spec([{"symbol": "AAA", "weight": 0.6}], S, E), {"AAA": flat}, BENCH)
    assert r["stats"]["final_value"] == pytest.approx(100000, rel=1e-12)
    assert r["stats"]["time_in_market"] == pytest.approx(0.6, rel=1e-9)


def test_benchmark_first_day_uses_open_to_close():
    bench = mk_bars("2023-12-28", N + 5, lambda i: (100, 110) if i == 3 else 110)       # i=3 คือ 2024-01-02
    flat = mk_bars("2023-12-28", N + 5, lambda i: 100.0)
    r = run_backtest(spec([{"symbol": "AAA", "weight": 1.0}], S, E), {"AAA": flat}, bench)
    assert r["period"]["first_trade_date"] == "2024-01-02"
    assert r["series"][0]["benchmark"] == pytest.approx(0.10, rel=1e-12)
    last_close = next(b["close"] for b in bench if b["date"] == r["period"]["last_date"])
    open0 = next(b["open"] for b in bench if b["date"] == "2024-01-02")
    assert r["comparison"]["benchmark"]["total_return"]["value"] == pytest.approx(last_close / open0 - 1, rel=1e-12)
    assert r["series"][-1]["benchmark"] == pytest.approx(last_close / open0 - 1, rel=1e-12)


def two_assets(b_fn=lambda i: 100 * 1.01 ** i, a_fn=lambda i: 100.0):
    return {"AAA": mk_bars("2023-12-28", N + 5, a_fn), "BBB": mk_bars("2023-12-28", N + 5, b_fn)}


def test_mode_none_equals_buy_and_hold():
    sp = spec([{"symbol": "AAA", "weight": 0.5}, {"symbol": "BBB", "weight": 0.5}], S, E)
    r = run_backtest(sp, two_assets(), BENCH)
    assert r["stats"]["rebalance_count"] == 0
    assert r["stats"]["final_value"] == pytest.approx(r["stats"]["buy_hold_final_value"], rel=1e-12)


def reference_monthly(bars, spec_, cal):
    """อ้างอิงแยกอิสระ: ปรับกลับเป็นสัดส่วนเป้าหมายที่ราคาเปิดวันทำการแรกของเดือนใหม่ (ไม่มีต้นทุน)"""
    w = {p["symbol"]: p["weight"] for p in spec_["positions"]}
    px = {s: {b["date"]: b for b in bars[s]} for s in w}
    sh = {s: 100000 * w[s] / px[s][cal[0]]["open"] for s in w}
    for k in range(1, len(cal)):
        if cal[k][:7] != cal[k - 1][:7]:
            v = sum(sh[s] * px[s][cal[k]]["open"] for s in w)
            sh = {s: v * w[s] / px[s][cal[k]]["open"] for s in w}
    return sum(sh[s] * px[s][cal[-1]]["close"] for s in w)


def test_calendar_monthly_matches_independent_reference():
    bars = two_assets(b_fn=lambda i: (100 * 1.01 ** i * 0.995, 100 * 1.01 ** i))        # open ≠ close
    sp = spec([{"symbol": "AAA", "weight": 0.5}, {"symbol": "BBB", "weight": 0.5}], S, E,
              rebalance={"mode": "calendar", "frequency": "monthly"})
    r = run_backtest(sp, bars, BENCH)
    assert r["stats"]["final_value"] == pytest.approx(reference_monthly(bars, sp, cal_dates(r)), rel=1e-9)
    assert r["stats"]["rebalance_count"] == 5                                            # ก.พ.-มิ.ย.
    firsts = {c[:7]: c for c in reversed(cal_dates(r))}                                   # วันทำการแรกของแต่ละเดือน
    assert {t["date"] for t in r["trades"] if t["reason"] == "rebalance"} == {firsts[m] for m in
            ("2024-02", "2024-03", "2024-04", "2024-05", "2024-06")}


def test_rebalance_executes_at_next_open_with_slippage():
    bars = two_assets(b_fn=lambda i: (100 * 1.01 ** i * 0.99, 100 * 1.01 ** i))
    sp = spec([{"symbol": "AAA", "weight": 0.5}, {"symbol": "BBB", "weight": 0.5}], S, E,
              rebalance={"mode": "calendar", "frequency": "monthly"}, costs={"commission_bps": 0, "slippage_bps": 10})
    r = run_backtest(sp, bars, BENCH)
    t = next(t for t in r["trades"] if t["reason"] == "rebalance")
    assert t["date"] == "2024-02-01"                                                      # ไม่ใช่วันสิ้นเดือน ม.ค.
    op = next(b["open"] for b in bars[t["symbol"]] if b["date"] == t["date"])
    assert t["price"] == pytest.approx(op * (0.999 if t["side"] == "sell" else 1.001), rel=1e-12)


def test_threshold_triggers_only_after_drift_exceeds():
    jump = lambda i: 100.0 if i < 43 else 125.0                                           # หลังวันที่ index 43 B +25%
    sp = spec([{"symbol": "AAA", "weight": 0.5}, {"symbol": "BBB", "weight": 0.5}], S, E,
              rebalance={"mode": "threshold", "threshold_pct": 5})
    r = run_backtest(sp, two_assets(b_fn=jump), BENCH)
    assert r["stats"]["rebalance_count"] == 1
    j = next(b["date"] for b in two_assets(b_fn=jump)["BBB"][3:] if b["close"] == 125.0)    # วันแรกที่ราคากระโดด
    nxt = cal_dates(r)[cal_dates(r).index(j) + 1]
    assert r["rebalances"][0]["date"] == nxt                                              # ตัดสินใจจากปิดวัน j ทำที่เปิดวันถัดไป
    small = lambda i: 100.0 if i < 43 else 104.0                                          # drift < 5pp -> ไม่ปรับ
    assert run_backtest(sp, two_assets(b_fn=small), BENCH)["stats"]["rebalance_count"] == 0


def test_hybrid_waits_for_period_end_and_requires_drift():
    jump = lambda i: 100.0 if i < 43 else 125.0
    sp = spec([{"symbol": "AAA", "weight": 0.5}, {"symbol": "BBB", "weight": 0.5}], S, E,
              rebalance={"mode": "hybrid", "frequency": "monthly", "threshold_pct": 5})
    r = run_backtest(sp, two_assets(b_fn=jump), BENCH)
    assert r["stats"]["rebalance_count"] == 1
    assert r["rebalances"][0]["date"][8:] in ("01", "02", "03", "04", "05") and r["rebalances"][0]["date"][5:7] != "01"
    flat = run_backtest(sp, two_assets(b_fn=lambda i: 100 * 1.0001 ** i), BENCH)
    assert flat["stats"]["rebalance_count"] == 0                                          # สิ้นงวดแต่ drift ต่ำ


def test_no_lookahead_future_prices_do_not_change_past():
    sp = spec([{"symbol": "AAA", "weight": 0.5}, {"symbol": "BBB", "weight": 0.5}], S, E,
              rebalance={"mode": "hybrid", "frequency": "monthly", "threshold_pct": 1}, costs={"commission_bps": 5, "slippage_bps": 5})
    base = two_assets(b_fn=lambda i: 100 * 1.01 ** i * (1 + 0.02 * ((i % 5) - 2)))
    r1 = run_backtest(sp, base, BENCH)
    cal = cal_dates(r1)
    T = cal[70]
    cut = cal[72]                                                                         # เปลี่ยนราคาตั้งแต่หลัง T+2 เป็นต้นไป
    alt = copy.deepcopy(base)
    for sym in alt:
        for b in alt[sym]:
            if b["date"] > cut:
                b["open"] *= 3; b["close"] *= 0.4; b["high"] *= 3; b["low"] *= 0.4
    alt_bench = copy.deepcopy(BENCH)
    for b in alt_bench:
        if b["date"] > cut:
            b["open"] *= 2; b["close"] *= 0.5
    r2 = run_backtest(sp, alt, alt_bench)
    assert r1["series"][:73] == r2["series"][:73]
    t1 = [t for t in r1["trades"] if t["date"] <= cut]
    t2 = [t for t in r2["trades"] if t["date"] <= cut]
    assert t1 == t2 and t1                                                               # มีการซื้อขายจริงในช่วงนั้น


def test_late_start_symbol_rejected_not_silently_reweighted():
    late = mk_bars("2024-02-01", 100, lambda i: 100.0)
    sp = spec([{"symbol": "AAA", "weight": 0.5}, {"symbol": "LATE", "weight": 0.5}], S, E)
    with pytest.raises(DataError) as e:
        run_backtest(sp, {"AAA": two_assets()["AAA"], "LATE": late}, BENCH)
    assert e.value.code == "late_start" and "LATE" in e.value.message


def test_short_gap_filled_long_gap_rejected():
    full = mk_bars("2023-12-28", N + 5, lambda i: 100.0)
    short = [b for j, b in enumerate(full) if not (50 <= j < 53)]                          # ขาด 3 วัน
    r = run_backtest(spec([{"symbol": "AAA", "weight": 1.0}], S, E), {"AAA": short}, BENCH)
    assert r["data_quality"]["filled_days"]["AAA"] == 3
    longg = [b for j, b in enumerate(full) if not (50 <= j < 58)]                          # ขาด 8 วัน
    with pytest.raises(DataError) as e:
        run_backtest(spec([{"symbol": "AAA", "weight": 1.0}], S, E), {"AAA": longg}, BENCH)
    assert e.value.code == "data_gap"


def test_too_short_and_benchmark_history_errors():
    with pytest.raises(DataError) as e:
        run_backtest(spec([{"symbol": "AAA", "weight": 1.0}], "2024-01-02", "2024-01-10"),
                     {"AAA": two_assets()["AAA"]}, BENCH)
    assert e.value.code == "too_short"
    with pytest.raises(DataError) as e:
        run_backtest(spec([{"symbol": "AAA", "weight": 1.0}], "2023-12-28", E), {"AAA": two_assets()["AAA"]}, BENCH)
    assert e.value.code == "benchmark_history"


def test_result_shape_labels_and_extremes():
    sp = spec([{"symbol": "AAA", "weight": 0.5}, {"symbol": "BBB", "weight": 0.5}], S, E,
              rebalance={"mode": "calendar", "frequency": "quarterly"}, risk_free_annual=0.04)
    bbb = lambda i: 100 * 1.01 ** i * (1 + 0.03 * ((i % 4) - 1.5))
    r = run_backtest(sp, two_assets(b_fn=bbb), BENCH)
    assert "hypothetical_backtest" in r["labels"] and "not_a_forecast" in r["labels"]
    d = r["extremes"]["days"]
    assert d["worst"][0]["portfolio"] <= d["worst"][1]["portfolio"] and d["best"][0]["portfolio"] >= d["best"][1]["portfolio"]
    assert all("benchmark" in x and "active" in x for x in d["worst"] + d["best"])
    assert r["comparison"]["portfolio"]["sharpe"]["status"] in ("ok", "limited_sample")  # ระบุ rf แล้ว
    assert {"portfolio", "buy_hold", "benchmark"} <= set(r["comparison"])
    assert r["calendar_years"][0]["year"] == 2024
    nof = run_backtest(spec([{"symbol": "AAA", "weight": 1.0}], S, E), {"AAA": two_assets()["AAA"]}, BENCH)
    assert nof["comparison"]["portfolio"]["sharpe"]["status"] == "unavailable"            # ไม่สมมติ rf เอง


def test_cash_never_negative_with_high_costs():
    sp = spec([{"symbol": "AAA", "weight": 0.5}, {"symbol": "BBB", "weight": 0.5}], S, E,
              rebalance={"mode": "threshold", "threshold_pct": 0.1}, costs={"commission_bps": 200, "slippage_bps": 500})
    r = run_backtest(sp, two_assets(b_fn=lambda i: 100 * (1 + 0.03 * ((i % 4) - 1.5))), BENCH)
    assert r["stats"]["final_value"] > 0 and all(t["shares"] > 0 for t in r["trades"])
    assert sum(t["notional"] * (1 if t["side"] == "sell" else -1) - (t["commission"]) for t in r["trades"]) > -100000 * 1.01
