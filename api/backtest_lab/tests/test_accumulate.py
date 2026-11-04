"""DCA / Buy-the-dip (engine/accumulate.py)"""
import datetime as dt
import math
from datetime import date

import pytest

from backtest_lab.engine.accum_spec import AccumError, accumulate_warmup, spec_warmup, validate_accumulate
from backtest_lab.engine.accumulate import is_period_start, run_accumulation, xirr
from backtest_lab.engine.dispatch import run_any
from backtest_lab.engine.runner import run_backtest
from backtest_lab.engine.spec import SpecError, spec_hash, validate_spec
from backtest_lab.tests.helpers import mk_bars, spec

TODAY = date(2026, 1, 1)
NB = 460
BARS0 = mk_bars("2023-01-02", NB, lambda i: 100.0)
DATES = [b["date"] for b in BARS0]
BENCH_FLAT = mk_bars("2023-01-02", NB, lambda i: 4000.0)
I0 = 60                                                   # วันเริ่มทดสอบ = แท่งที่ 60 (มีประวัติก่อนหน้าให้ lookback)


def path(fn):
    return mk_bars("2023-01-02", NB, fn)


def vs(acc, positions=None, i0=I0, i1=NB - 1, **kw):
    pos = positions or [{"symbol": "AAA", "weight": 1.0}]
    return validate_spec(spec(pos, DATES[i0], DATES[i1], accumulate=acc, **kw), today=TODAY)


def run(sp, bars=None, bench=None, rates=None):
    return run_accumulation(sp, bars or {"AAA": BARS0}, bench or BENCH_FLAT, rates=rates)


def buys(r, reason=None):
    return [t for t in r["trades"] if t["side"] == "buy" and (reason is None or t["reason"] == reason)]


def month_starts(cal):
    return [cal[k] for k in range(len(cal)) if is_period_start(cal, k, "monthly")]


# ------------------------------------------------------------------ validation
def test_validate_accepts_full_and_rejects_bad():
    ok = validate_accumulate({"schedule": {"amount": 500, "frequency": "monthly"}, "dip": {"drop_pct": 20, "amount": 1000},
                              "when": {"op": "<", "left": {"price": "close"}, "right": {"ind": "ema", "period": 200}},
                              "contribution": {"amount": 300, "frequency": "weekly"}, "max_invested_per_stock": 5000})
    assert ok["dip"]["lookback_days"] == 252 and ok["dip"]["cooldown_days"] == 21 and ok["initial_invest_pct"] == 0.0
    for bad in ({}, {"contribution": {"amount": 100, "frequency": "monthly"}},          # ไม่มีอะไรให้ซื้อ
                {"schedule": {"amount": 100, "frequency": "daily"}}, {"schedule": {"amount": -5, "frequency": "monthly"}},
                {"dip": {"drop_pct": 0, "amount": 100}}, {"dip": {"drop_pct": 95, "amount": 100}},
                {"dip": {"drop_pct": 20, "amount": 100, "lookback_days": 5}}, {"schedule": {"amount": 1, "frequency": "monthly"}, "x": 1},
                {"schedule": {"amount": 100, "frequency": "monthly"}, "when": {"op": "??", "left": {"value": 1}, "right": {"value": 2}}},
                {"schedule": {"amount": 100, "frequency": "monthly"}, "max_invested_per_stock": 0},
                {"schedule": {"amount": 100, "frequency": "monthly"}, "initial_invest_pct": 101}):
        with pytest.raises(AccumError):
            validate_accumulate(bad)
    assert validate_accumulate({"initial_invest_pct": 50})["initial_invest_pct"] == 50.0     # ลงก้อนแรกอย่างเดียวได้


def test_spec_rules_and_hash_unchanged():
    base = validate_spec(spec([{"symbol": "AAA", "weight": 1.0}], DATES[I0], DATES[-1]), today=TODAY)
    assert "accumulate" not in base
    sp = vs({"schedule": {"amount": 500, "frequency": "monthly"}})
    assert sp["accumulate"]["schedule"]["amount"] == 500 and spec_hash(sp) != spec_hash(base)
    strat = {"entry": {"op": ">", "left": {"price": "close"}, "right": {"value": 1}}}
    with pytest.raises(SpecError):
        vs({"schedule": {"amount": 500, "frequency": "monthly"}}, strategy=strat)
    with pytest.raises(SpecError):
        vs({"schedule": {"amount": 500, "frequency": "monthly"}}, rebalance={"mode": "calendar", "frequency": "monthly"})
    with pytest.raises(SpecError):
        vs({"schedule": {"amount": 0, "frequency": "monthly"}})


def test_warmup_counts_lookback_and_indicator():
    a = validate_accumulate({"dip": {"drop_pct": 20, "amount": 1, "lookback_days": 252},
                             "when": {"op": "<", "left": {"price": "close"}, "right": {"ind": "ema", "period": 200}}})
    assert accumulate_warmup(a) >= 5 * 200
    assert spec_warmup({"accumulate": a}) == accumulate_warmup(a)
    assert spec_warmup({}) == 0


# ------------------------------------------------------------------ DCA
def test_dca_buys_first_trading_day_of_each_month_exact_amount_at_open():
    sp = vs({"schedule": {"amount": 1000, "frequency": "monthly"}}, costs={"commission_bps": 10, "slippage_bps": 20})
    r = run(sp)
    b = buys(r, "schedule")
    cal = [x["date"] for x in r["series"]]
    assert [t["date"] for t in b] == month_starts(cal)
    for t in b:
        assert t["notional"] + t["commission"] == pytest.approx(1000.0)          # ใช้เงินรวมค่าคอมพอดี
        assert t["price"] == pytest.approx(100 * 1.002)                          # เปิด + slippage
    assert r["stats"]["total_contributed"] == 0 and r["stats"]["profit"] == pytest.approx(r["stats"]["final_value"] - 100000)


def test_dca_first_buy_is_first_day_and_quarterly_weekly_calendars():
    r = run(vs({"schedule": {"amount": 1000, "frequency": "monthly"}}))
    assert buys(r)[0]["date"] == DATES[I0]                                      # ต้นการทดสอบถือเป็นต้นงวด
    q = run(vs({"schedule": {"amount": 1000, "frequency": "quarterly"}}))
    firsts = [DATES[I0]] + [next(d for d in DATES if d >= f"{y}-{m:02d}-01") for y, m in ((2023, 4), (2023, 7), (2023, 10), (2024, 1), (2024, 4), (2024, 7), (2024, 10))]
    got = [t["date"] for t in buys(q)]
    assert got == [d for d in firsts if DATES[I0] <= d <= DATES[-1]][:len(got)] and len(got) >= 6
    w = run(vs({"schedule": {"amount": 1000, "frequency": "weekly"}}))
    wd = [dt.date.fromisoformat(t["date"]).isocalendar()[:2] for t in buys(w)]
    assert len(set(wd)) == len(wd) and len(wd) > 50                              # สัปดาห์ละครั้งไม่ซ้ำ


def test_first_day_buy_when_window_is_inside_one_month():
    i0, i1 = DATES.index("2023-05-01"), DATES.index("2023-05-31")
    r = run(vs({"schedule": {"amount": 1000, "frequency": "monthly"}}, i0=i0, i1=i1))
    assert [t["date"] for t in buys(r)] == ["2023-05-01"]


def test_cap_counts_commission_in_invested():
    sp = vs({"dip": {"drop_pct": 20, "lookback_days": 30, "amount": 1000, "cooldown_days": 1}, "max_invested_per_stock": 2500},
            costs={"commission_bps": 100, "slippage_bps": 0})
    r = run(sp, {"AAA": dip_path()})
    b = buys(r)
    assert sum(t["notional"] + t["commission"] for t in b) == pytest.approx(2500.0)
    assert sum(t["notional"] for t in b) < 2500.0
    assert r["accumulate_result"]["per_stock"][0]["invested"] == pytest.approx(2500.0)


def test_baseline_lump_sum_uses_normalized_weights_for_contributions():
    rising = path(lambda i: 100 * 1.001 ** i)
    pos = [{"symbol": "AAA", "weight": 0.3}, {"symbol": "BBB", "weight": 0.2}]
    sp = vs({"contribution": {"amount": 1000, "frequency": "monthly"}, "initial_invest_pct": 100}, positions=pos)
    r = run(sp, {"AAA": rising, "BBB": rising})
    cal = [x["date"] for x in r["series"]]
    px = {b["date"]: b for b in rising}
    last = px[cal[-1]]["close"]
    exp = 100000 * 0.5 / px[cal[0]]["open"] * last + 100000 * 0.5            # ส่วนที่ไม่ได้ลงทุนเป็นเงินสด
    for d in month_starts(cal)[1:]:
        exp += 1000 / px[d]["open"] * last
    assert r["stats"]["buy_hold_final_value"] == pytest.approx(exp)


def test_dca_amount_split_by_weight_and_cash_runs_out_is_reported():
    pos = [{"symbol": "AAA", "weight": 0.6}, {"symbol": "BBB", "weight": 0.4}]
    sp = vs({"schedule": {"amount": 1000, "frequency": "monthly"}}, positions=pos)
    r = run(sp, {"AAA": BARS0, "BBB": BARS0})
    a = [t for t in buys(r) if t["symbol"] == "AAA"][0]
    b = [t for t in buys(r) if t["symbol"] == "BBB"][0]
    assert a["notional"] == pytest.approx(600) and b["notional"] == pytest.approx(400)
    tiny = vs({"schedule": {"amount": 30000, "frequency": "monthly"}})              # ใช้เงินช่อง 100k หมดใน 4 งวด
    r2 = run(tiny)
    assert len(buys(r2)) == 4 and r2["accumulate_result"]["blocked"]["no_cash"] > 0
    assert [round(t["notional"]) for t in buys(r2)] == [30000, 30000, 30000, 10000]        # งวดที่ 4 ซื้อได้เท่าที่เหลือ
    assert r2["accumulate_result"]["per_stock"][0]["cash_left"] == pytest.approx(0.0, abs=1e-6)


def test_contribution_is_not_counted_as_return_flat_price():
    """ราคานิ่ง ไม่มีต้นทุน: มูลค่าพอร์ตโตตามเงินเติมแต่ผลตอบแทนถ่วงเวลาต้องเป็น 0 ทุกวัน"""
    sp = vs({"contribution": {"amount": 700, "frequency": "monthly"}, "schedule": {"amount": 700, "frequency": "monthly"}})
    r = run(sp)
    st = r["stats"]
    n_contrib = len(month_starts([x["date"] for x in r["series"]])) - 1
    assert st["total_contributed"] == pytest.approx(700 * n_contrib) and n_contrib > 5
    assert st["final_value"] == pytest.approx(100000 + 700 * n_contrib)
    assert all(abs(x["portfolio"]) < 1e-12 for x in r["series"])
    assert st["profit"] == pytest.approx(0, abs=1e-6) and st["benchmark_profit"] == pytest.approx(0, abs=1e-6)
    assert r["analysis"]["performance"]["portfolio_return"]["value"] == pytest.approx(0, abs=1e-12)
    inv = [x["invested"] for x in r["series"]]
    assert inv[0] == 100000 and inv[-1] == pytest.approx(100000 + 700 * n_contrib) and inv == sorted(inv)


def test_contribution_splits_to_sleeves_by_normalized_weight():
    pos = [{"symbol": "AAA", "weight": 0.3}, {"symbol": "BBB", "weight": 0.2}]
    sp = vs({"contribution": {"amount": 1000, "frequency": "monthly"}, "initial_invest_pct": 100}, positions=pos)
    r = run(sp, {"AAA": BARS0, "BBB": BARS0})
    ps = {p["symbol"]: p for p in r["accumulate_result"]["per_stock"]}
    k = r["accumulate_result"]["contribution_events"]
    assert ps["AAA"]["cash_left"] == pytest.approx(1000 * k * 0.6) and ps["BBB"]["cash_left"] == pytest.approx(1000 * k * 0.4)


def test_all_in_first_day_equals_buy_and_hold_exactly():
    rising = path(lambda i: 100 * 1.001 ** i)
    bench = path(lambda i: 4000 * 1.0004 ** i)
    sp = vs({"initial_invest_pct": 100}, costs={"commission_bps": 5, "slippage_bps": 5})
    r = run(sp, {"AAA": rising}, bench)
    assert r["stats"]["final_value"] == pytest.approx(r["stats"]["buy_hold_final_value"])
    assert [x["portfolio"] for x in r["series"]] == pytest.approx([x["buy_hold"] for x in r["series"]])
    assert r["analysis"]["performance"]["portfolio_return"]["value"] == pytest.approx(r["comparison"]["buy_hold"]["total_return"]["value"])


def test_dca_on_rising_market_lags_lump_sum_by_cash_drag():
    rising = path(lambda i: 100 * 1.001 ** i)
    sp = vs({"schedule": {"amount": 10000, "frequency": "monthly"}})
    r = run(sp, {"AAA": rising})
    assert r["stats"]["final_value"] < r["stats"]["buy_hold_final_value"]          # ตลาดขึ้นตลอด: ทยอยซื้อแพ้ลงทันที (เงินสดไม่มีดอกเบี้ย)
    assert r["stats"]["time_in_market"] < 1.0


# ------------------------------------------------------------------ IRR / benchmark flows
def test_xirr_known_values():
    d0, d1 = date(2020, 1, 1), date(2022, 1, 1)
    r = xirr([(d0, -100.0), (d1, 121.0)])
    assert 100 * (1 + r) ** ((d1 - d0).days / 365.25) == pytest.approx(121.0, rel=1e-9)
    assert xirr([(d0, -100.0), (d1, 100.0)]) == pytest.approx(0.0, abs=1e-9)
    assert xirr([(d0, -100.0), (d1, 40.0)]) < 0
    assert xirr([(d0, -100.0)]) is None and xirr([]) is None


def test_mwr_none_under_one_year_and_benchmark_uses_same_flows():
    short = vs({"contribution": {"amount": 500, "frequency": "monthly"}, "schedule": {"amount": 500, "frequency": "monthly"}}, i1=I0 + 120)
    assert run(short)["stats"]["money_weighted_return"] is None
    bench = path(lambda i: (4000 * 1.0005 ** i, 4000 * 1.0005 ** i * 1.01))          # เปิด != ปิด
    sp = vs({"contribution": {"amount": 1000, "frequency": "monthly"}, "initial_invest_pct": 100})
    r = run(sp, bench=bench)
    cal = [x["date"] for x in r["series"]]
    bmap = {b["date"]: b for b in bench}
    units = 100000 / bmap[cal[0]]["open"] + sum(1000 / bmap[d]["open"] for d in month_starts(cal)[1:])
    assert r["stats"]["benchmark_final_value"] == pytest.approx(units * bmap[cal[-1]]["close"])
    assert r["stats"]["money_weighted_return"] is not None


# ------------------------------------------------------------------ dip
DIP_AT = 150                                                        # ปิดวัน index 150 = 75 (ลง 25% จาก 100)


def dip_path():
    return path(lambda i: 100.0 if i < DIP_AT else 75.0)


def test_dip_buys_next_open_after_trigger_close_no_lookahead():
    sp = vs({"dip": {"drop_pct": 20, "lookback_days": 30, "amount": 1000, "cooldown_days": 5}})
    r = run(sp, {"AAA": dip_path()})
    d = buys(r, "dip")
    assert d and d[0]["date"] == DATES[DIP_AT + 1]                 # สัญญาณจากปิดวัน 150 -> ซื้อเปิดวัน 151 (ไม่ใช่วัน 150)
    assert d[0]["price"] == pytest.approx(75.0)
    assert all(t["date"] > DATES[DIP_AT] for t in d)
    assert not any(t["date"] <= DATES[DIP_AT] for t in buys(r, "dip"))


def test_dip_cooldown_spacing_and_amounts():
    sp = vs({"dip": {"drop_pct": 20, "lookback_days": 30, "amount": 1000, "cooldown_days": 7}})
    r = run(sp, {"AAA": dip_path()})
    idx = [DATES.index(t["date"]) for t in buys(r, "dip")]
    assert all(b - a >= 7 for a, b in zip(idx, idx[1:])) and len(idx) >= 3
    assert all(t["notional"] == pytest.approx(1000) for t in buys(r, "dip"))


def test_dip_window_forgets_old_high():
    """สูงสุดเก่านอกหน้าต่าง lookback ต้องไม่ถูกนับ: ราคา 100 -> 75 ค้างนานเกิน lookback แล้วไม่ถือว่าลงจากสูงสุดอีก"""
    sp = vs({"dip": {"drop_pct": 20, "lookback_days": 30, "amount": 1000, "cooldown_days": 1}})
    r = run(sp, {"AAA": dip_path()})
    last_idx = max(DATES.index(t["date"]) for t in buys(r, "dip"))
    assert last_idx <= DIP_AT + 30 + 1


def test_dip_cap_limits_total_invested_and_counts_blocked():
    sp = vs({"dip": {"drop_pct": 20, "lookback_days": 30, "amount": 1000, "cooldown_days": 1}, "max_invested_per_stock": 2500})
    r = run(sp, {"AAA": dip_path()})
    ps = r["accumulate_result"]["per_stock"][0]
    assert ps["invested"] == pytest.approx(2500.0)
    assert [round(t["notional"]) for t in buys(r)] == [1000, 1000, 500]
    assert r["accumulate_result"]["blocked"]["cap"] > 0


def test_dip_never_triggers_when_drop_not_deep_enough():
    sp = vs({"dip": {"drop_pct": 30, "lookback_days": 30, "amount": 1000}})
    r = run(sp, {"AAA": dip_path()})
    assert buys(r) == [] and r["stats"]["final_value"] == pytest.approx(100000.0)
    assert r["accumulate_result"]["buy_counts"] == {"initial": 0, "schedule": 0, "dip": 0}


# ------------------------------------------------------------------ when (indicator condition)
def test_when_condition_gates_dip_and_schedule():
    below = {"op": "<", "left": {"price": "close"}, "right": {"value": 90}}
    above = {"op": ">", "left": {"price": "close"}, "right": {"value": 90}}
    dip = {"drop_pct": 20, "lookback_days": 30, "amount": 1000, "cooldown_days": 5}
    assert buys(run(vs({"dip": dip, "when": below}), {"AAA": dip_path()}), "dip")
    assert buys(run(vs({"dip": dip, "when": above}), {"AAA": dip_path()}), "dip") == []
    sched = {"amount": 1000, "frequency": "monthly"}
    r = run(vs({"schedule": sched, "when": above}), {"AAA": dip_path()})
    assert all(t["price"] > 90 for t in buys(r, "schedule")) and buys(r, "schedule")                # ก่อนราคาตก ซื้อได้
    assert not any(DATES.index(t["date"]) > DIP_AT for t in buys(r, "schedule"))                    # หลังตก when เป็นเท็จ = ไม่ซื้อ


def test_when_uses_previous_close_not_same_day():
    """when ใช้ปิดวันก่อนหน้า: วันที่ราคาเพิ่งตก (index 150) เงื่อนไข close<90 ยังไม่เป็นจริงตอนเปิดวัน 150"""
    r = run(vs({"schedule": {"amount": 1000, "frequency": "weekly"}, "when": {"op": "<", "left": {"price": "close"}, "right": {"value": 90}}}),
            {"AAA": dip_path()})
    first = min(DATES.index(t["date"]) for t in buys(r, "schedule"))
    assert first > DIP_AT                                           # ซื้อครั้งแรกหลังปิดวัน 150
    assert DATES[first] >= DATES[DIP_AT + 1]


def test_when_with_ema_indicator_buys_only_below_ema():
    wavy = path(lambda i: 100 + 20 * math.sin(i / 15))
    ema = {"op": "<", "left": {"price": "close"}, "right": {"ind": "ema", "period": 20}}
    sp = vs({"schedule": {"amount": 500, "frequency": "weekly"}, "when": ema})
    r = run(sp, {"AAA": wavy})
    from backtest_lab.engine import indicators as I
    e = I.compute(wavy, "ema", {"period": 20, "source": "close"}, "value")
    assert buys(r)
    for t in buys(r):
        j = DATES.index(t["date"]) - 1                              # ปิดวันก่อนหน้า
        assert wavy[j]["close"] < e[j]


# ------------------------------------------------------------------ attribution / ตัวเลขรวม
def check_money(r):
    a, st = r["attribution"], r["stats"]
    money_in = st["initial_capital"] + st["total_contributed"]
    assert abs(a["totals"]["reconciliation_error"]) < 1e-6
    assert a["totals"]["net_pnl"] == pytest.approx(st["final_value"] - money_in, abs=1e-6)
    assert st["profit"] == pytest.approx(st["final_value"] - money_in)
    assert a["totals"]["sum_contribution"] == pytest.approx(st["profit"] / money_in, abs=1e-12)
    assert a["totals"]["pct_risk_sum"] == pytest.approx(1.0, abs=1e-9)
    assert sum(p["commission"] for p in a["positions"]) == pytest.approx(st["commission_paid"])


def test_attribution_reconciles_with_flows_costs_dip_and_schedule():
    wavy_a = path(lambda i: 100 + 25 * math.sin(i / 20) + 0.05 * i)
    wavy_b = path(lambda i: 50 + 12 * math.cos(i / 17))
    pos = [{"symbol": "AAA", "weight": 0.5}, {"symbol": "BBB", "weight": 0.4}]
    sp = vs({"contribution": {"amount": 800, "frequency": "monthly"}, "schedule": {"amount": 1200, "frequency": "monthly"},
             "dip": {"drop_pct": 10, "lookback_days": 40, "amount": 3000, "cooldown_days": 10},
             "max_invested_per_stock": 60000}, positions=pos, costs={"commission_bps": 4, "slippage_bps": 6})
    r = run(sp, {"AAA": wavy_a, "BBB": wavy_b}, path(lambda i: 4000 * 1.0003 ** i))
    assert r["accumulate_result"]["buy_counts"]["dip"] > 0 and r["accumulate_result"]["buy_counts"]["schedule"] > 0
    check_money(r)


def test_attribution_reconciles_pure_dca_flat_and_with_initial():
    check_money(run(vs({"schedule": {"amount": 1000, "frequency": "monthly"}}, costs={"commission_bps": 5, "slippage_bps": 5})))
    check_money(run(vs({"contribution": {"amount": 100, "frequency": "weekly"}, "initial_invest_pct": 50, "schedule": {"amount": 100, "frequency": "weekly"}}),
                    {"AAA": path(lambda i: 100 + 10 * math.sin(i / 9))}))


def test_existing_modes_unchanged_by_flows_param():
    """ATT.build ที่ไม่ส่ง flows ต้องได้ผลเหมือนเดิม (กัน regression ของโหมดเดิม)"""
    a = mk_bars("2023-12-28", 330, lambda i: 100 * (1 + 0.0008 * i + 0.04 * math.sin(i / 7)))
    be = mk_bars("2023-12-28", 330, lambda i: 4000 * 1.0004 ** i)
    sp = validate_spec(spec([{"symbol": "AAA", "weight": 1.0}], "2024-01-02", "2024-12-13", costs={"commission_bps": 3, "slippage_bps": 5}), today=TODAY)
    r = run_backtest(sp, {"AAA": a}, be)
    assert r["attribution"]["totals"]["money_in"] == sp["initial_capital"] and abs(r["attribution"]["totals"]["reconciliation_error"]) < 1e-6


def test_dispatch_routes_by_spec():
    sp = vs({"schedule": {"amount": 1000, "frequency": "monthly"}})
    assert run_any(sp, {"AAA": BARS0}, BENCH_FLAT)["mode"] == "accumulate"
    plain = validate_spec(spec([{"symbol": "AAA", "weight": 1.0}], DATES[I0], DATES[-1]), today=TODAY)
    assert "mode" not in run_any(plain, {"AAA": BARS0}, BENCH_FLAT)


# ------------------------------------------------------------------ service
def test_service_builds_accumulate_result_with_warnings():
    from backtest_lab.data.price_store import MemoryBackend, PriceStore
    from backtest_lab.service import build_result

    class Prov:
        name = "fake"

        def get_bars(self, sym, s, e):
            return {"AAA": dip_path(), "^GSPC": BENCH_FLAT}[sym]
    sp = vs({"contribution": {"amount": 500, "frequency": "monthly"}, "dip": {"drop_pct": 20, "lookback_days": 30, "amount": 1000}})
    res = build_result(sp, PriceStore(Prov(), MemoryBackend()))
    codes = {w["code"] for w in res["warnings"]}
    assert res["mode"] == "accumulate" and {"hindsight_risk", "dca_cash_idle", "dca_flows"} <= codes
    assert res["spec_hash"] == spec_hash(sp)
    none = vs({"dip": {"drop_pct": 60, "lookback_days": 30, "amount": 1000}})
    assert "no_buys" in {w["code"] for w in build_result(none, PriceStore(Prov(), MemoryBackend()))["warnings"]}
