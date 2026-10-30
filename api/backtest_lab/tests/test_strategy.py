import copy
import math

import pytest

from backtest_lab.engine import rules
from backtest_lab.engine.rules import RuleError, evaluate, validate_strategy, warmup_bars
from backtest_lab.engine.runner import run_backtest
from backtest_lab.engine.spec import SpecError, spec_hash, validate_spec
from backtest_lab.engine.strategy_runner import run_strategy
from backtest_lab.tests.helpers import mk_bars, spec

N = 140
BENCH = mk_bars("2023-12-28", N + 5, lambda i: 100 * 1.0005 ** i)
S, E = "2024-01-02", "2024-06-28"
ABOVE100 = {"op": ">", "left": {"price": "close"}, "right": {"value": 100}}


def strat_spec(positions, strategy, **kw):
    return spec(positions, S, E, strategy=strategy, **kw)


def mk_ohlc(start, rows):
    """rows: [(open, high, low, close)]"""
    base = mk_bars(start, len(rows), lambda i: 1)
    for b, (o, h, l, c) in zip(base, rows):
        b.update(open=float(o), high=float(h), low=float(l), close=float(c))
    return base


# ------------------------------------------------------------------ validation
def test_validate_accepts_typical_rules():
    s = validate_strategy({
        "entry": {"all": [{"op": ">", "left": {"price": "close"}, "right": {"ind": "ema", "period": 200}},
                          {"op": "<", "left": {"ind": "rsi", "period": 14}, "right": {"value": 70}}]},
        "exit": {"op": "cross_below", "left": {"price": "close"}, "right": {"ind": "sma", "period": 50, "mult": 0.98}},
        "stops": {"stop_loss_pct": 8, "trailing_stop_pct": 15, "max_hold_days": 60}})
    assert s["stops"]["max_hold_days"] == 60 and s["exit"]["op"] == "cross_below"
    assert warmup_bars(s) >= 1000          # EMA200 -> 5×200


@pytest.mark.parametrize("bad", [
    {},                                                                           # ไม่มี entry
    {"entry": ABOVE100, "x": 1},
    {"entry": {"op": "==", "left": {"value": 1}, "right": {"value": 1}}},
    {"entry": {"op": ">", "left": {"ind": "foo"}, "right": {"value": 1}}},
    {"entry": {"op": ">", "left": {"ind": "ema", "period": 1}, "right": {"value": 1}}},
    {"entry": {"op": ">", "left": {"price": "vwap"}, "right": {"value": 1}}},
    {"entry": {"op": ">", "left": {"price": "close", "extra": 1}, "right": {"value": 1}}},
    {"entry": {"op": ">", "left": {"price": "close", "shift": -1}, "right": {"value": 1}}},
    {"entry": {"op": ">", "left": {"price": "close", "of": "weird"}, "right": {"value": 1}}},
    {"entry": {"op": ">", "left": {"value": 1, "shift": 1}, "right": {"value": 1}}},
    {"entry": {"op": ">", "left": {"ind": "macd", "output": "nope"}, "right": {"value": 1}}},
    {"entry": {"all": []}},
    {"entry": {"all": [ABOVE100], "any": [ABOVE100]}},
    {"entry": "close > 100"},
    {"entry": {"op": ">", "left": {"exec_code": "os"}, "right": {"value": 1}}},
    {"entry": ABOVE100, "stops": {"stop_loss_pct": 0}},
    {"entry": ABOVE100, "stops": {"stop_loss_pct": True}},
    {"entry": ABOVE100, "stops": {"max_hold_days": 0}},
    {"entry": ABOVE100, "stops": {"foo": 1}},
])
def test_validate_rejects(bad):
    with pytest.raises(RuleError):
        validate_strategy(bad)


def test_validate_limits_depth_and_nodes():
    c = ABOVE100
    for _ in range(6):
        c = {"not": c}
    with pytest.raises(RuleError):
        validate_strategy({"entry": c})
    many = {"all": [ABOVE100] * 12}
    with pytest.raises(RuleError):
        validate_strategy({"entry": {"all": [many, many, {"any": [ABOVE100] * 3}]}})     # >24 โหนด


def test_spec_without_strategy_unchanged_and_with_strategy_hashed():
    base = {"start": S, "end": E, "initial_capital": 1000, "positions": [{"symbol": "AAA", "weight": 1}]}
    a = validate_spec(base)
    assert "strategy" not in a
    b = validate_spec({**base, "strategy": {"entry": ABOVE100}})
    assert "strategy" in b and spec_hash(a) != spec_hash(b)
    with pytest.raises(SpecError):
        validate_spec({**base, "strategy": {"entry": {"op": "?"}}})


# ------------------------------------------------------------------ evaluation
def test_evaluate_compare_cross_kleene_shift_mult():
    bars = mk_bars("2024-01-01", 12, lambda i: [10, 11, 12, 9, 8, 13, 14, 7, 7, 7, 7, 7][i])
    closes = [b["close"] for b in bars]
    cv = lambda c: validate_strategy({"entry": c})["entry"]
    gt = evaluate(cv({"op": ">", "left": {"price": "close"}, "right": {"value": 10}}), bars)
    assert gt == [c > 10 for c in closes]
    cu = evaluate(cv({"op": "cross_above", "left": {"price": "close"}, "right": {"value": 10}}), bars)
    assert cu[0] is None and cu[2] is False and cu[1] is True and cu[5] is True and cu[6] is False
    sh = evaluate(cv({"op": ">", "left": {"price": "close"}, "right": {"price": "close", "shift": 1}}), bars)
    assert sh[0] is None and sh[1] is True and sh[3] is False
    ml = evaluate(cv({"op": ">", "left": {"price": "close"}, "right": {"price": "close", "mult": 2}}), bars)
    assert all(v is False for v in ml)
    # Kleene: all(False, None) = False ; all(True, None) = None ; any(True, None) = True
    unk = {"op": ">", "left": {"ind": "sma", "period": 20}, "right": {"value": 0}}        # ยังคำนวณไม่ได้ -> None
    f = {"op": "<", "left": {"price": "close"}, "right": {"value": 0}}
    t = {"op": ">", "left": {"price": "close"}, "right": {"value": 0}}
    assert evaluate(cv({"all": [f, unk]}), bars)[5] is False
    assert evaluate(cv({"all": [t, unk]}), bars)[5] is None
    assert evaluate(cv({"any": [t, unk]}), bars)[5] is True
    assert evaluate(cv({"not": unk}), bars)[5] is None


def test_evaluate_benchmark_operand_aligned_by_date():
    bars = mk_bars("2024-01-01", 10, lambda i: 100)
    bench = mk_bars("2023-12-29", 12, lambda i: [1, 1, 1, 1, 9, 9, 9, 9, 9, 9, 9, 9][i])
    c = validate_strategy({"entry": {"op": ">", "left": {"price": "close", "of": "benchmark"}, "right": {"value": 5}}})["entry"]
    r = evaluate(c, bars, bench)
    for b, v in zip(bars, r):
        last = [x for x in bench if x["date"] <= b["date"]][-1]
        assert v == (last["close"] > 5)


def test_rules_no_lookahead():
    import random
    rnd = random.Random(3)
    px, rows = 100.0, []
    for _ in range(260):
        o = px * (1 + rnd.gauss(0, .004)); c = o * (1 + rnd.gauss(0, .015))
        rows.append((o, max(o, c) * 1.004, min(o, c) * 0.996, c)); px = c
    bars = mk_ohlc("2023-01-02", rows)
    bench = mk_bars("2023-01-02", 260, lambda i: 100 + math.sin(i / 9) * 5)
    c = validate_strategy({"entry": {"all": [
        {"op": "cross_above", "left": {"ind": "ema", "period": 10}, "right": {"ind": "ema", "period": 30}},
        {"op": ">", "left": {"ind": "rsi"}, "right": {"value": 40}},
        {"op": ">", "left": {"price": "close", "of": "benchmark"}, "right": {"ind": "sma", "period": 20, "of": "benchmark"}}]}})["entry"]
    full = evaluate(c, bars, bench)
    for i in range(0, 260, 11):
        part = evaluate(c, bars[:i + 1], [b for b in bench if b["date"] <= bars[i]["date"]])
        assert part[i] == full[i], i


# ------------------------------------------------------------------ engine
def test_signal_at_close_executes_next_open_and_exit_rule():
    path = lambda i: 90 if i < 14 else (110 if i < 24 else 90)
    a = mk_bars("2023-12-28", N + 5, path)
    r = run_strategy(strat_spec([{"symbol": "AAA", "weight": 1.0}], {"entry": ABOVE100, "exit": {
        "op": "<", "left": {"price": "close"}, "right": {"value": 100}}}), {"AAA": a}, BENCH)
    first_up, first_dn = a[14]["date"], a[24]["date"]
    buy, sell = r["trades"][0], r["trades"][1]
    assert buy["side"] == "buy" and buy["date"] == a[15]["date"] and buy["reason"] == "entry"   # สัญญาณปิดวัน 14 -> เปิดวัน 15
    assert sell["side"] == "sell" and sell["date"] == a[25]["date"] and sell["reason"] == "signal_exit"
    assert buy["price"] == 110 and sell["price"] == 90
    assert r["stats"]["final_value"] == pytest.approx(100000 * 90 / 110, rel=1e-12)
    trip = r["strategy_result"]["trips"][0]
    assert trip["return"] == pytest.approx(90 / 110 - 1, rel=1e-12) and trip["exit_reason"] == "signal_exit"
    assert r["strategy_result"]["trip_stats"]["closed_trades"] == 1
    assert r["strategy_result"]["trip_stats"]["win_rate"] == 0.0
    assert r["strategy_result"]["first_entry_signal"]["AAA"] == first_up


def test_no_exit_means_exit_when_entry_known_false():
    path = lambda i: 90 if i < 14 else (110 if i < 24 else 90)
    a = mk_bars("2023-12-28", N + 5, path)
    r = run_strategy(strat_spec([{"symbol": "AAA", "weight": 1.0}], {"entry": ABOVE100}), {"AAA": a}, BENCH)
    assert [t["side"] for t in r["trades"]] == ["buy", "sell"]


def test_never_signals_is_all_cash():
    a = mk_bars("2023-12-28", N + 5, lambda i: 50)
    r = run_strategy(strat_spec([{"symbol": "AAA", "weight": 0.5}], {"entry": ABOVE100}), {"AAA": a}, BENCH)
    assert r["trades"] == [] and r["stats"]["final_value"] == pytest.approx(100000)
    assert r["stats"]["time_in_market"] == 0 and r["strategy_result"]["trip_stats"]["closed_trades"] == 0


def test_stop_loss_intrabar_and_gap():
    # วัน 5 เข้าที่เปิด 100 (สัญญาณปิดวัน 4); วัน 7 low 85 -> stop 10% ที่ 90 ; กรณี gap เปิด 80 -> ได้ 80
    def build(gap):
        rows = [(95, 95, 95, 95)] * 4 + [(105, 105, 105, 105)] + [(100, 101, 99, 101), (101, 102, 100, 101),
                                                                  ((80, 82, 78, 80) if gap else (99, 100, 85, 92))] + [(92, 93, 91, 92)] * 140
        return mk_ohlc("2024-01-02", rows)
    for gap, exp in ((False, 90.0), (True, 80.0)):
        a = build(gap)
        a = mk_bars("2023-12-28", 3, lambda i: 95) + a                       # แท่งก่อนวันเริ่ม
        sp = strat_spec([{"symbol": "AAA", "weight": 1.0}], {"entry": ABOVE100, "stops": {"stop_loss_pct": 10}})
        r = run_strategy(sp, {"AAA": a}, BENCH)
        sells = [t for t in r["trades"] if t["side"] == "sell"]
        assert len(sells) == 1 and sells[0]["reason"] == "stop_loss"
        assert sells[0]["price"] == pytest.approx(exp) and sells[0]["date"] == a[3 + 7]["date"]
        # หลังโดน stop ราคา 92 < 100 -> entry เป็นเท็จ ไม่มีการเข้าใหม่
        assert [t["side"] for t in r["trades"]] == ["buy", "sell"]


def test_reentry_blocked_until_entry_false():
    rows = ([(95,) * 4] * 4 + [(105,) * 4] * 2 + [(105, 105, 80, 104)] + [(104,) * 4] * 6 + [(95,) * 4] * 3 + [(105,) * 4] * 120)
    a = mk_bars("2023-12-28", 3, lambda i: 95) + mk_ohlc("2024-01-02", rows)
    sp = strat_spec([{"symbol": "AAA", "weight": 1.0}], {"entry": ABOVE100, "stops": {"stop_loss_pct": 10}})
    r = run_strategy(sp, {"AAA": a}, BENCH)
    sides = [(t["side"], t["reason"]) for t in r["trades"]]
    # buy -> stop_loss (วัน 6 low 80) แม้ราคาปิด >100 ต่อเนื่องก็ไม่เข้าใหม่ จนกว่าจะมีวันที่ <100 แล้วกลับมา >100
    assert sides[:2] == [("buy", "entry"), ("sell", "stop_loss")]
    assert sides[2] == ("buy", "entry") and r["trades"][2]["date"] == a[3 + 17]["date"]


def test_take_profit_trailing_and_priority():
    base = [(95,) * 4] * 4 + [(100,) * 4]
    # take-profit 20%: วันที่ 6 high 125 -> ออกที่ 120
    rows = base + [(100, 125, 99, 120)] + [(120,) * 4] * 140
    a = mk_bars("2023-12-28", 3, lambda i: 95) + mk_ohlc("2024-01-02", rows)
    r = run_strategy(strat_spec([{"symbol": "AAA", "weight": 1.0}], {"entry": ABOVE100.copy() | {"op": ">="}, "stops": {"take_profit_pct": 20}}), {"AAA": a}, BENCH)
    s = [t for t in r["trades"] if t["side"] == "sell"][0]
    assert s["reason"] == "take_profit" and s["price"] == pytest.approx(120)
    # trailing 10%: high ไต่ไป 130 (ปิดวันก่อนหน้า) แล้ววันถัดไป low 116 ≤ 117 -> ออก 117
    rows = base + [(100, 130, 100, 130), (130, 131, 116, 120)] + [(120,) * 4] * 140
    a = mk_bars("2023-12-28", 3, lambda i: 95) + mk_ohlc("2024-01-02", rows)
    r = run_strategy(strat_spec([{"symbol": "AAA", "weight": 1.0}], {"entry": ABOVE100.copy() | {"op": ">="}, "stops": {"trailing_stop_pct": 10}}), {"AAA": a}, BENCH)
    s = [t for t in r["trades"] if t["side"] == "sell"][0]
    assert s["reason"] == "trailing_stop" and s["price"] == pytest.approx(117.0)
    # แท่งเดียวชนทั้ง stop และ take-profit -> stop ก่อน
    rows = base + [(100, 125, 85, 100)] + [(100,) * 4] * 140
    a = mk_bars("2023-12-28", 3, lambda i: 95) + mk_ohlc("2024-01-02", rows)
    sp = strat_spec([{"symbol": "AAA", "weight": 1.0}], {"entry": ABOVE100.copy() | {"op": ">="}, "stops": {"stop_loss_pct": 10, "take_profit_pct": 20}})
    r = run_strategy(sp, {"AAA": a}, BENCH)
    assert [t for t in r["trades"] if t["side"] == "sell"][0]["reason"] == "stop_loss"


def test_max_hold_days():
    a = mk_bars("2023-12-28", N + 5, lambda i: 110 if i >= 4 else 90)
    r = run_strategy(strat_spec([{"symbol": "AAA", "weight": 1.0}], {"entry": ABOVE100, "exit": {
        "op": "<", "left": {"price": "close"}, "right": {"value": 0}}, "stops": {"max_hold_days": 5}}), {"AAA": a}, BENCH)
    t = r["strategy_result"]["trips"][0]
    assert t["exit_reason"] == "max_hold" and t["holding_days"] == 6          # ถือ 5 วันปิด -> ขายเปิดวันที่ 6


# ------------------------------------------------------------------ equivalence กับ B1 (ไม่มีต้นทุน)
def _always():
    return {"entry": {"op": ">", "left": {"value": 1}, "right": {"value": 0}}}


@pytest.mark.parametrize("rebalance", [
    {"mode": "none"}, {"mode": "calendar", "frequency": "monthly"},
    {"mode": "threshold", "threshold_pct": 3}, {"mode": "hybrid", "frequency": "quarterly", "threshold_pct": 5}])
@pytest.mark.parametrize("weights", [(0.5, 0.5), (0.4, 0.3)])
def test_always_in_strategy_equals_fixed_weight_engine(rebalance, weights):
    a = mk_bars("2023-12-28", N + 5, lambda i: 50 * (1 + 0.004 * math.sin(i / 3)) * 1.003 ** i)
    b = mk_bars("2023-12-28", N + 5, lambda i: 80 * (1 + 0.01 * math.cos(i / 5)) * 0.999 ** i)
    pos = [{"symbol": "AAA", "weight": weights[0]}, {"symbol": "BBB", "weight": weights[1]}]
    bars = {"AAA": a, "BBB": b}
    base = spec(pos, S, E, rebalance=rebalance)
    r1 = run_backtest(base, bars, BENCH)
    r2 = run_strategy(validate_spec({**{k: v for k, v in base.items()}, "strategy": _always()}), bars, BENCH)
    assert r2["stats"]["rebalance_count"] == r1["stats"]["rebalance_count"]
    for x, y in zip(r1["series"], r2["series"]):
        assert y["portfolio"] == pytest.approx(x["portfolio"], abs=1e-9), x["date"]
    assert r2["stats"]["final_value"] == pytest.approx(r1["stats"]["final_value"], rel=1e-9)


def test_initial_costs_match_fixed_weight_engine():
    a = mk_bars("2023-12-28", N + 5, lambda i: 50 * 1.002 ** i)
    base = spec([{"symbol": "AAA", "weight": 1.0}], S, E, costs={"commission_bps": 10, "slippage_bps": 20})
    r1 = run_backtest(base, {"AAA": a}, BENCH)
    r2 = run_strategy(validate_spec({**base, "strategy": _always()}), {"AAA": a}, BENCH)
    assert r2["stats"]["final_value"] == pytest.approx(r1["stats"]["final_value"], rel=1e-12)
    assert r2["stats"]["commission_paid"] == pytest.approx(r1["stats"]["commission_paid"], rel=1e-12)
    assert r2["stats"]["slippage_cost"] == pytest.approx(r1["stats"]["slippage_cost"], rel=1e-12)


def test_value_conservation_with_costs_and_rebalance():
    a = mk_bars("2023-12-28", N + 5, lambda i: 50 * (1 + 0.05 * math.sin(i / 4)))
    b = mk_bars("2023-12-28", N + 5, lambda i: 80 * (1 + 0.05 * math.cos(i / 6)))
    rule = {"entry": {"op": ">", "left": {"price": "close"}, "right": {"ind": "sma", "period": 5}}}
    sp = strat_spec([{"symbol": "AAA", "weight": 0.5}, {"symbol": "BBB", "weight": 0.4}], rule,
                    rebalance={"mode": "calendar", "frequency": "monthly"}, costs={"commission_bps": 5, "slippage_bps": 10})
    r = run_strategy(sp, {"AAA": a, "BBB": b}, BENCH)
    assert r["stats"]["trade_count"] > 4 and r["stats"]["total_cost"] > 0
    # หุ้นเศษ+ไม่มี leverage: น้ำหนักสุดท้ายไม่ติดลบ รวมไม่เกิน 1
    fw = r["stats"]["final_weights"]
    assert all(v >= -1e-12 for v in fw.values()) and sum(fw.values()) <= 1 + 1e-9
    # ไม่มีการซื้อด้วยเงินที่ไม่มี: ทุก trade shares>0
    assert all(t["shares"] > 0 and t["notional"] > 0 for t in r["trades"])


def test_strategy_run_has_no_lookahead_whole_engine():
    """ตัดข้อมูลหลังวัน cut ทิ้ง -> trade ทุกรายการที่เกิดก่อน cut ต้องเหมือนเดิมทุกประการ"""
    a = mk_bars("2023-12-28", N + 5, lambda i: 100 * (1 + 0.08 * math.sin(i / 5)) * 1.001 ** i)
    rule = {"entry": {"op": "cross_above", "left": {"price": "close"}, "right": {"ind": "ema", "period": 8}},
            "exit": {"op": "cross_below", "left": {"price": "close"}, "right": {"ind": "ema", "period": 8}},
            "stops": {"stop_loss_pct": 4, "trailing_stop_pct": 6}}
    full = run_strategy(strat_spec([{"symbol": "AAA", "weight": 1.0}], rule), {"AAA": a}, BENCH)
    assert len(full["trades"]) >= 6
    cut = full["period"]["last_date"]
    cut_i = [b["date"] for b in a].index("2024-04-30")
    sp2 = spec([{"symbol": "AAA", "weight": 1.0}], S, a[cut_i]["date"], strategy=rule)
    part = run_strategy(sp2, {"AAA": a[:cut_i + 1]}, BENCH[:cut_i + 1])
    pre = [t for t in full["trades"] if t["date"] <= a[cut_i]["date"]]
    got = part["trades"]
    # ณ วันสุดท้ายของข้อมูลที่ตัด ไม่มีคำสั่งค้าง จึงเทียบเฉพาะรายการที่เกิดจนถึงวัน cut
    assert [(t["date"], t["side"], t["reason"], round(t["price"], 9)) for t in got] == \
           [(t["date"], t["side"], t["reason"], round(t["price"], 9)) for t in pre]


def test_open_position_at_end_reported_not_sold():
    a = mk_bars("2023-12-28", N + 5, lambda i: 110)
    r = run_strategy(strat_spec([{"symbol": "AAA", "weight": 1.0}], {"entry": ABOVE100}), {"AAA": a}, BENCH)
    sr = r["strategy_result"]
    assert sr["trip_stats"]["closed_trades"] == 0 and sr["trip_stats"]["open_at_end"] == 1
    assert sr["trips"][0]["open"] is True and sr["trips"][0]["exit_date"] is None


def test_benchmark_regime_filter_blocks_entries():
    a = mk_bars("2023-12-28", N + 5, lambda i: 110)
    bench_dn = mk_bars("2023-12-28", N + 5, lambda i: 100 * 0.9995 ** i)            # S&P ต่ำกว่า SMA ตลอด
    rule = {"entry": {"all": [ABOVE100, {"op": ">", "left": {"price": "close", "of": "benchmark"},
                                          "right": {"ind": "sma", "period": 20, "of": "benchmark"}}]}}
    r = run_strategy(strat_spec([{"symbol": "AAA", "weight": 1.0}], rule), {"AAA": a}, bench_dn)
    assert r["trades"] == []
