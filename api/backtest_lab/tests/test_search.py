"""Sweep / Walk-forward / เทียบกลยุทธ์สุ่ม — ความถูกต้อง, ไม่แอบดูอนาคต, ขอบเขต, endpoint"""
import asyncio
import copy
import math
import random
from datetime import date, timedelta

import pytest

from backtest_lab.api import handlers as H
from backtest_lab.data.price_store import MemoryBackend, PriceStore
from backtest_lab.data.total_return import Market
from backtest_lab.db.run_store import MemoryRunStore
from backtest_lab.engine.runner import run_backtest
from backtest_lab.engine.strategy_runner import run_strategy
from backtest_lab.jobs.limiter import RateLimiter
from backtest_lab.jobs.runner_pool import RunPool
from backtest_lab.robust import baseline as BL
from backtest_lab.robust import search as SR
from backtest_lab.robust import search_handlers as SH
from backtest_lab.tests.helpers import mk_bars, spec
from backtest_lab.tests.test_handlers import finish


# ------------------------------------------------------------------ ข้อมูลทดสอบ
def walk(seed, n, drift=0.0004, vol=0.015, p0=100.0):
    rng, p, out = random.Random(seed), p0, []
    for _ in range(n):
        p *= math.exp(drift + vol * rng.gauss(0, 1))
        out.append(p)
    return out


def gapless(start, closes):
    """open_i = close_{i-1}: ซื้อ/ขายที่ราคาเปิดเท่ากับปิดวันก่อน -> แบบจำลอง close-to-close ตรงกับ engine เป๊ะ"""
    prev = [closes[0]] + closes[:-1]
    return mk_bars(start, len(closes), lambda i: (prev[i], closes[i]))


NW = 900
WARM = 300
BENCH = mk_bars("2019-01-01", NW + WARM, lambda i: 100 * 1.0004 ** i)
DATES = [b["date"] for b in BENCH]
START, END = DATES[WARM], DATES[-1]
SYMS = ("AAA", "BBB", "CCC")


def market(seed=1, **kw):
    bars = {s: gapless("2019-01-01", walk(seed * 10 + i, NW + WARM, **kw)) for i, s in enumerate(SYMS)}
    return Market(bars, BENCH)


STRAT = {"entry": {"all": [{"op": ">", "left": {"price": "close"}, "right": {"ind": "ema", "period": 50}},
                           {"op": ">", "left": {"ind": "rsi", "period": 14}, "right": {"value": 45}}]},
         "exit": {"op": "<", "left": {"price": "close"}, "right": {"ind": "ema", "period": 50}},
         "stops": {"stop_loss_pct": 10, "take_profit_pct": 40, "max_hold_days": 120}}


def sp(strategy=STRAT, weights=(0.3, 0.3, 0.3), **kw):
    return spec([{"symbol": s, "weight": w} for s, w in zip(SYMS, weights)], START, END, strategy=strategy, **kw)


EMA_ID = "entry.all.0.right.params.period"
RSI_ID = "entry.all.1.left.params.period"
CONST_ID = "entry.all.1.right.value"
EXIT_ID = "exit.right.params.period"
SL_ID = "stops.stop_loss_pct"


def pick(spec_, *reqs):
    return SR.parse_selection(spec_, [dict(id=i, **r) for i, r in reqs])


# ------------------------------------------------------------------ tunables / whitelist
def test_tunables_discovery_ids_paths_and_current_values():
    s = sp()
    ts = SR.tunables(s)
    ids = [t["id"] for t in ts]
    assert len(ids) == len(set(ids))
    assert {EMA_ID, RSI_ID, CONST_ID, EXIT_ID, SL_ID, "stops.take_profit_pct", "stops.max_hold_days"} <= set(ids)
    for t in ts:
        assert SR._get(s["strategy"], t["path"]) == t["current"]                        # path ชี้ถึงค่าจริง
    by = {t["id"]: t for t in ts}
    assert by[EMA_ID]["integer"] and by[EMA_ID]["lo"] == 2 and by[EMA_ID]["suggest"] == {"min": 25, "max": 75, "steps": 5}
    assert by[CONST_ID]["kind"] == "const" and "RSI(14) > 45" in by[CONST_ID]["label"]
    assert all("path" not in t for t in SR.public_tunables(s))
    assert SR.tunables(spec([{"symbol": "AAA", "weight": 1.0}], START, END)) == []        # ไม่มีกลยุทธ์


def test_build_values_rounding_dedupe_and_bounds():
    t = {t["id"]: t for t in SR.tunables(sp())}
    assert SR.build_values(t[EMA_ID], {"min": 20, "max": 100, "steps": 5}) == [20, 40, 60, 80, 100]
    assert SR.build_values(t[EMA_ID], {"values": [30, 10, 30, 20]}) == [10, 20, 30]
    assert SR.build_values(t[SL_ID], {"min": 5, "max": 20, "steps": 4}) == [5.0, 10.0, 15.0, 20.0]
    for bad in ({"min": 20, "max": 20, "steps": 3}, {"min": 20, "max": 10, "steps": 3}, {"min": 1, "max": 50, "steps": 3},
                {"min": 20, "max": 100, "steps": 2000}, {"min": 20, "max": 100, "steps": True}, {"values": [10]},
                {"values": "x"}, {"values": [10, float("nan")]}, {"values": [10, True]}, {"min": 20, "steps": 3}, {}):
        with pytest.raises(SR.SearchError):
            SR.build_values(t[EMA_ID], bad)
    with pytest.raises(SR.SearchError):
        SR.build_values(t[SL_ID], {"min": 0, "max": 20, "steps": 3})                     # stop ต่ำกว่า 0.1
    with pytest.raises(SR.SearchError):
        SR.build_values(t[EMA_ID], {"min": 3.1, "max": 3.4, "steps": 3})                 # ปัดแล้วเหลือค่าเดียว


def test_parse_selection_whitelist_and_limits():
    s = sp()
    ok = {"id": EMA_ID, "min": 20, "max": 100, "steps": 3}
    assert SR.parse_selection(s, [ok])[0][0]["id"] == EMA_ID
    for bad in ([], None, "x", [ok, ok], [ok, {"id": RSI_ID, "min": 7, "max": 21, "steps": 3}, {"id": SL_ID, "min": 5, "max": 15, "steps": 3}],
                [{"id": "entry.all.0.right.ind", "min": 1, "max": 5, "steps": 3}],          # ฟิลด์ที่ไม่ใช่ tunable
                [{"id": "__class__", "min": 1, "max": 5, "steps": 3}],
                [{"id": "entry.all.0.right.params.source", "min": 1, "max": 5, "steps": 3}],
                [{"id": "strategy", "values": [1, 2]}], [5], [{"min": 1, "max": 5, "steps": 3}]):
        with pytest.raises(SR.SearchError):
            SR.parse_selection(s, bad)
    with pytest.raises(SR.SearchError):
        SR.parse_selection(spec([{"symbol": "AAA", "weight": 1.0}], START, END), [ok])        # ไม่มีกลยุทธ์


def test_make_variant_sets_only_target_and_does_not_mutate():
    s = sp()
    before = copy.deepcopy(s)
    chosen, _ = pick(s, (EMA_ID, {"values": [30, 60]}), (SL_ID, {"values": [5, 15]}))
    v = SR.make_variant(s, chosen, (30, 5.0))
    assert s == before
    assert v["strategy"]["entry"]["all"][0]["right"]["params"]["period"] == 30 and v["strategy"]["stops"]["stop_loss_pct"] == 5.0
    v["strategy"]["entry"]["all"][0]["right"]["params"]["period"] = 30
    expect = copy.deepcopy(before)
    expect["strategy"]["entry"]["all"][0]["right"]["params"]["period"] = 30
    expect["strategy"]["stops"]["stop_loss_pct"] = 5.0
    assert v == expect                                                                         # ไม่มีอย่างอื่นเปลี่ยน
    # ค่าคงที่
    c2, _ = pick(s, (CONST_ID, {"values": [40, 55]}))
    assert SR.make_variant(s, c2, (55.0,))["strategy"]["entry"]["all"][1]["right"]["value"] == 55.0
    # ผิดกติกาตัวชี้วัด: MACD fast >= slow
    macd = {"entry": {"op": ">", "left": {"ind": "macd", "fast": 12, "slow": 26, "signal": 9, "output": "hist"}, "right": {"value": 0}}}
    ms = sp(macd)
    mc, _ = pick(ms, ("entry.left.params.fast", {"values": [10, 30]}))
    assert SR.make_variant(ms, mc, (10,)) is not None
    assert SR.make_variant(ms, mc, (30,)) is None


# ------------------------------------------------------------------ sweep
def test_sweep_cell_equals_direct_run_and_summary_consistent():
    s, mk = sp(), market()
    chosen, grids = pick(s, (EMA_ID, {"values": [30, 50, 80]}), (SL_ID, {"values": [5, 10, 20]}))
    out = SR.sweep(s, mk, chosen, grids, "total_return")
    assert out["trials"] == 9 and len(out["cells"]) == 9 and out["base"] == {"i": 1, "j": 1}
    direct = run_strategy(s, mk.bars, mk.bench)
    base = next(c for c in out["cells"] if (c["i"], c["j"]) == (1, 1))
    assert base["metrics"]["total_return"] == pytest.approx(direct["comparison"]["portfolio"]["total_return"]["value"], rel=1e-12)
    assert out["reference"]["buy_hold"]["total_return"] == pytest.approx(direct["comparison"]["buy_hold"]["total_return"]["value"], rel=1e-12)
    # ทุกเซลล์ตรงกับการรันตรงด้วย spec ที่ขยับเอง
    for c in out["cells"]:
        v = copy.deepcopy(s)
        v["strategy"]["entry"]["all"][0]["right"]["params"]["period"] = c["params"][EMA_ID]
        v["strategy"]["stops"]["stop_loss_pct"] = float(c["params"][SL_ID])
        r = run_strategy(v, mk.bars, mk.bench)
        assert c["metrics"]["total_return"] == pytest.approx(r["comparison"]["portfolio"]["total_return"]["value"], rel=1e-12)
        assert c["trades"] == r["stats"]["trade_count"]
    vals = [c["metrics"]["total_return"] for c in out["cells"]]
    assert out["best"]["metrics"]["total_return"] == max(vals) and out["summary"]["best_value"] == max(vals)
    assert out["summary"]["worst_value"] == min(vals)
    assert out["summary"]["frac_positive"] == pytest.approx(sum(1 for v in vals if v > 0) / 9)


def test_sweep_1d_and_limits_and_metric_validation():
    s, mk = sp(), market()
    chosen, grids = pick(s, (EMA_ID, {"values": [30, 50, 80]}))
    out = SR.sweep(s, mk, chosen, grids, "cagr")
    assert len(out["axes"]) == 1 and {c["j"] for c in out["cells"]} == {0} and out["trials"] == 3
    with pytest.raises(SR.SearchError):
        SR.sweep(s, mk, chosen, grids, "sharpe")
    big, bg = pick(s, (EMA_ID, {"min": 20, "max": 100, "steps": 9}), (SL_ID, {"min": 5, "max": 20, "steps": 9}))
    with pytest.raises(SR.SearchError):
        SR.sweep(s, mk, big, bg, "calmar")                                                      # 81 > 49


def _fake_runner(surface):
    """แทน _run_safe ด้วยผลสังเคราะห์ที่ควบคุมรูปพื้นผิวได้ — ทดสอบตรรกะ verdict/neighbor โดยตรง"""
    def run(spec_, mk):
        p = spec_["strategy"]["entry"]["all"][0]["right"]["params"]["period"]
        sl = spec_["strategy"]["stops"]["stop_loss_pct"]
        v = surface(p, sl)
        m = lambda x: {"value": x}
        port = {"total_return": m(v), "cagr": m(v), "max_drawdown": m(-0.1), "calmar": m(v), "sortino": m(v)}
        flat = {k: m(0.0) for k in port}
        return {"comparison": {"portfolio": port, "buy_hold": flat, "benchmark": flat},
                "stats": {"trade_count": 5, "time_in_market": 0.5}}, None
    return run


@pytest.mark.parametrize("surface,verdict,edge", [
    (lambda p, sl: 1.0 if (p, sl) == (50, 10.0) else 0.1, "spike", False),
    (lambda p, sl: 0.9 + 0.1 * (p == 50 and sl == 10.0), "plateau", False),
    (lambda p, sl: 0.7, "plateau", False),                                                      # พื้นผิวเรียบเท่ากันหมด -> ใช้เซลล์กลางตาราง ไม่ใช่ขอบ
    (lambda p, sl: -0.5 - p / 1000, "no_profit", None),
    (lambda p, sl: p / 100, "edge", True),                                                      # สูงสุดอยู่ขอบ (p มากสุด) แม้พื้นผิวเรียบ ก็ไม่เรียกว่า plateau
])
def test_sweep_verdict_heuristics(monkeypatch, surface, verdict, edge):
    s = sp()
    monkeypatch.setattr(SR, "_run_safe", _fake_runner(surface))
    chosen, grids = pick(s, (EMA_ID, {"values": [30, 40, 50, 60, 70]}), (SL_ID, {"values": [5, 10, 15]}))
    out = SR.sweep(s, None, chosen, grids, "total_return")
    assert out["summary"]["verdict"] == verdict
    if edge is not None:
        assert out["summary"]["best_on_edge"] is edge
    if verdict == "spike":
        assert out["summary"]["neighbor_ratio"] == pytest.approx(0.1)
    if verdict == "plateau":
        assert out["summary"]["neighbor_ratio"] >= SR.PLATEAU_NEIGHBOR


def test_sweep_neighbor_ratio_exact_on_known_surface(monkeypatch):
    s = sp()
    monkeypatch.setattr(SR, "_run_safe", _fake_runner(lambda p, sl: {50: 1.0, 40: 0.5, 60: 0.7}.get(p, 0.2) * (1.0 if sl == 10.0 else 0.0)))
    chosen, grids = pick(s, (EMA_ID, {"values": [30, 40, 50, 60, 70]}))
    # 1 มิติ: ใช้เฉพาะ EMA; best=50 เพื่อนบ้าน=40,60 -> (0.5+0.7)/2 = 0.6 ; sl คงที่ 10 จึงได้ค่าเต็ม
    out = SR.sweep(s, None, chosen, grids, "total_return")
    assert out["best"]["params"][EMA_ID] == 50 and out["summary"]["neighbor_ratio"] == pytest.approx(0.6)
    assert out["summary"]["verdict"] == "mixed"                                                  # 0.6 ไม่ต่ำกว่า spike และไม่ถึง plateau


def test_sweep_invalid_cells_reported_not_crash():
    ms = sp({"entry": {"op": ">", "left": {"ind": "macd", "fast": 12, "slow": 26, "signal": 9, "output": "hist"}, "right": {"value": 0}}})
    chosen, grids = pick(ms, ("entry.left.params.fast", {"values": [10, 20, 30]}))
    out = SR.sweep(ms, market(), chosen, grids, "total_return")
    bad = [c for c in out["cells"] if c["metrics"] is None]
    assert len(bad) == 1 and bad[0]["params"]["entry.left.params.fast"] == 30 and "ผิดกติกา" in bad[0]["reason"]
    assert out["summary"]["valid_cells"] == 2


def test_sweep_cancel_aborts():
    import threading
    ev = threading.Event()
    ev.set()
    s = sp()
    chosen, grids = pick(s, (EMA_ID, {"values": [30, 50]}))
    with pytest.raises(SR.Aborted):
        SR.sweep(s, market(), chosen, grids, "total_return", cancel=ev)


# ------------------------------------------------------------------ walk-forward
def run_dates(s, mk):
    return [x["date"] for x in run_strategy(s, mk.bars, mk.bench)["series"]]


def test_walk_forward_selection_is_argmax_of_train_window():
    s, mk = sp(), market()
    dates = run_dates(s, mk)
    chosen, grids = pick(s, (EMA_ID, {"values": [20, 40, 80, 120]}))
    wf = SR.walk_forward(s, mk, dates, chosen, grids, "total_return", 3, True)
    blocks = SR.split_windows(dates, 4)
    assert len(wf["folds"]) == 3 and wf["summary"]["trials"] == 12
    for f, row in enumerate(wf["folds"]):
        assert row["train"] == [blocks[0][0], blocks[f][1]] and row["test"] == list(blocks[f + 1])
        scores = {}
        for p in grids[0]:
            v = copy.deepcopy(s)
            v["strategy"]["entry"]["all"][0]["right"]["params"]["period"] = p
            r = run_strategy({**v, "start": row["train"][0], "end": row["train"][1]}, mk.bars, mk.bench)
            scores[p] = r["comparison"]["portfolio"]["total_return"]["value"]
        best = max(scores, key=scores.get)
        assert row["chosen"][EMA_ID] == best and row["is_value"] == pytest.approx(scores[best], rel=1e-12)


def test_walk_forward_rolling_train_uses_previous_block_only():
    s, mk = sp(), market()
    dates = run_dates(s, mk)
    chosen, grids = pick(s, (EMA_ID, {"values": [20, 80]}))
    wf = SR.walk_forward(s, mk, dates, chosen, grids, "total_return", 3, False)
    blocks = SR.split_windows(dates, 4)
    for f, row in enumerate(wf["folds"]):
        assert row["train"] == list(blocks[f]) and row["test"] == list(blocks[f + 1])


def _scramble_after(mk, cut_date):
    """แทนราคาหลัง cut_date ด้วยราคาที่ต่างสุดขั้ว — ถ้ามีการแอบดูอนาคต ผลเลือกพารามิเตอร์จะเปลี่ยน"""
    bars = {}
    for s, bs in mk.bars.items():
        out, rng = [], random.Random(99)
        last = None
        for b in bs:
            if b["date"] <= cut_date:
                out.append(b)
                last = b["close"]
            else:
                new = last * math.exp(rng.choice((-0.2, 0.25)))
                out.append({**b, "open": last, "close": new, "high": max(last, new), "low": min(last, new)})
                last = new
        bars[s] = out
    return Market(bars, mk.bench)


def test_walk_forward_has_no_lookahead_into_future_blocks():
    s, mk = sp(), market()
    dates = run_dates(s, mk)
    chosen, grids = pick(s, (EMA_ID, {"values": [20, 50, 100]}), (SL_ID, {"values": [5, 15]}))
    base = SR.walk_forward(s, mk, dates, chosen, grids, "total_return", 3, True)
    blocks = SR.split_windows(dates, 4)
    # ทำลายข้อมูลหลังสิ้นสุดช่วงฝึกของ fold สุดท้าย (= บล็อกสุดท้ายทั้งบล็อก): การเลือกของทุก fold ต้องไม่เปลี่ยน
    alt = SR.walk_forward(s, _scramble_after(mk, blocks[2][1]), dates, chosen, grids, "total_return", 3, True)
    for a, b in zip(base["folds"], alt["folds"]):
        assert a["chosen"] == b["chosen"] and a["is_value"] == b["is_value"]
    assert base["folds"][-1]["oos_value"] != alt["folds"][-1]["oos_value"]                     # ทดสอบมีพลัง: ผล OOS ของ fold สุดท้ายเปลี่ยนจริง
    # fold แรกต้องไม่ขึ้นกับข้อมูลหลังบล็อก 0 เลย
    alt0 = SR.walk_forward(s, _scramble_after(mk, blocks[0][1]), dates, chosen, grids, "total_return", 3, True)
    assert alt0["folds"][0]["chosen"] == base["folds"][0]["chosen"] and alt0["folds"][0]["is_value"] == base["folds"][0]["is_value"]


def test_walk_forward_stitched_equals_compounded_fold_returns():
    s, mk = sp(), market()
    dates = run_dates(s, mk)
    chosen, grids = pick(s, (EMA_ID, {"values": [20, 50, 100]}))
    wf = SR.walk_forward(s, mk, dates, chosen, grids, "total_return", 3, True)
    for key, fold_key in (("walk_forward", "oos"), ("fixed_params", "fixed_oos"), ("buy_hold", "buy_hold_oos"), ("benchmark", "benchmark_oos")):
        comp = 1.0
        for r in wf["folds"]:
            comp *= 1.0 + r[fold_key]["total_return"]
        assert wf["stitched"][key]["total_return"] == pytest.approx(comp - 1.0, rel=1e-9)
    c = wf["curves"]
    assert len(c["dates"]) == len(c["walk_forward"]) == len(c["buy_hold"]) and c["walk_forward"][-1] == pytest.approx(wf["stitched"]["walk_forward"]["total_return"], abs=0.02)
    assert [r["fold"] for r in wf["folds"]] == [1, 2, 3]
    st = wf["param_stability"][EMA_ID]
    assert len(st["chosen"]) == 3 and st["distinct"] == len(set(st["chosen"]))


def test_walk_forward_limits_and_errors():
    s, mk = sp(), market()
    dates = run_dates(s, mk)
    chosen, grids = pick(s, (EMA_ID, {"values": [20, 50]}))
    for folds in (1, 7, 0):
        with pytest.raises(SR.SearchError):
            SR.walk_forward(s, mk, dates, chosen, grids, "total_return", folds, True)
    with pytest.raises(SR.SearchError):
        SR.walk_forward(s, mk, dates[:150], chosen, grids, "total_return", 5, True)             # บล็อกสั้นเกิน
    with pytest.raises(SR.SearchError):
        SR.walk_forward(s, mk, dates, chosen, grids, "calmar", 5, True)                          # บล็อก < 1 ปี คำนวณ CAGR ไม่ได้
    with pytest.raises(SR.SearchError):
        SR.walk_forward(s, mk, dates, chosen, grids, "nope", 3, True)
    big, bg = pick(s, (EMA_ID, {"min": 20, "max": 100, "steps": 9}), (SL_ID, {"min": 5, "max": 20, "steps": 9}))
    with pytest.raises(SR.SearchError):
        SR.walk_forward(s, mk, dates, big, bg, "total_return", 3, True)                          # เกิน MAX_WF_RUNS


# ------------------------------------------------------------------ path_metrics ตรงกับ engine
def test_path_metrics_matches_engine():
    s, mk = sp(), market()
    res = run_strategy(s, mk.bars, mk.bench)
    cap = s["initial_capital"]
    pm = SR.path_metrics([cap * (1 + p["portfolio"]) for p in res["series"]], cap, res["period"]["base_date"], res["series"][-1]["date"])
    c = res["comparison"]["portfolio"]
    assert pm["total_return"] == pytest.approx(c["total_return"]["value"], rel=1e-12)
    assert pm["cagr"] == pytest.approx(c["cagr"]["value"], rel=1e-9)
    assert pm["max_drawdown"] == pytest.approx(c["max_drawdown"]["value"], abs=1e-9)
    assert pm["calmar"] == pytest.approx(c["calmar"]["value"], rel=1e-8)
    short = SR.path_metrics([1.0, 1.1], 1.0, "2024-01-01", "2024-06-01")
    assert short["cagr"] is None and short["calmar"] is None and short["total_return"] == pytest.approx(0.1)


# ------------------------------------------------------------------ random baseline
def test_place_preserves_count_durations_and_never_overlaps():
    rng = random.Random(5)
    for _ in range(300):
        n = rng.randint(30, 400)
        durs, left = [], n
        for _ in range(rng.randint(0, 8)):
            d = rng.randint(1, max(1, left // 3))
            if d > left:
                break
            durs.append(d)
            left -= d
        out = BL._place(durs, n, rng)
        assert sorted(x - e for e, x in out) == sorted(durs)
        assert all(0 <= e < x <= n for e, x in out)
        assert all(b[0] >= a[1] for a, b in zip(out, out[1:]))                                   # ไม่ซ้อนทับ เรียงตามเวลา


def test_place_covers_positions_roughly_uniformly():
    rng, n, counts = random.Random(1), 20, [0] * 20
    for _ in range(4000):
        (e, x), = BL._place([5], n, rng)
        counts[e] += 1
    assert set(range(16)) == {i for i, c in enumerate(counts) if c}                              # เริ่มได้ 0..15 เท่านั้น
    assert min(counts[:16]) > 4000 / 16 * 0.7 and max(counts[:16]) < 4000 / 16 * 1.3


def test_values_single_trip_exact_and_costs():
    G = {"A": [1.0, 1.1, 1.21, 1.331, 1.4641, 1.61051]}
    n = 5
    vals = BL._values({"A": [(1, 4)]}, G, {"A": 1000.0}, 500.0, n, 1.0)
    # ถือวัน 1..3 : มูลค่า ณ ปิดวัน i = 1000 * G[i+1]/G[1] ; ก่อนเข้า/หลังออก = คงที่
    assert vals[0] == pytest.approx(1500.0)
    assert vals[1] == pytest.approx(500 + 1000 * 1.21 / 1.1) and vals[2] == pytest.approx(500 + 1000 * 1.331 / 1.1)
    assert vals[3] == pytest.approx(500 + 1000 * 1.4641 / 1.1) and vals[4] == vals[3]
    costed = BL._values({"A": [(1, 4)]}, G, {"A": 1000.0}, 500.0, n, 0.99)
    assert costed[0] == pytest.approx(1500.0) and costed[4] - 500 == pytest.approx((vals[4] - 500) * 0.99)
    assert BL._values({"A": []}, G, {"A": 1000.0}, 0.0, n, 0.99) == [1000.0] * n


@pytest.mark.parametrize("strategy", [
    {"entry": {"op": ">", "left": {"price": "close"}, "right": {"ind": "sma", "period": 30}}, "stops": {}},
    {"entry": {"op": ">", "left": {"price": "close"}, "right": {"ind": "ema", "period": 40}},
     "exit": {"op": "<", "left": {"price": "close"}, "right": {"ind": "ema", "period": 20}}, "stops": {"max_hold_days": 50}},
])
def test_replication_matches_engine_exactly_on_gapless_zero_cost_data(strategy):
    s, mk = sp(strategy, weights=(0.3, 0.3, 0.2)), market(3)                                    # น้ำหนักรวม 0.8 -> มีเงินสดค้าง
    res = run_strategy(s, mk.bars, mk.bench)
    assert res["stats"]["trade_count"] >= 4
    out = BL.random_baseline(s, mk, res, "total_return", 100, 1)
    rep = out["replication"]
    assert rep["model"]["total_return"] == pytest.approx(rep["actual"]["total_return"], abs=1e-9)
    assert rep["model"]["max_drawdown"] == pytest.approx(rep["actual"]["max_drawdown"], abs=1e-9)
    assert rep["within_tolerance"] and not [w for w in out["warnings"] if w["code"] == "model_mismatch"]


@pytest.mark.parametrize("strategy", [
    # รอบทั้งหมดปิดก่อนจบ (ออกด้วยกฎ)
    {"entry": {"op": ">", "left": {"price": "close"}, "right": {"ind": "ema", "period": 40}},
     "exit": {"op": "<", "left": {"price": "close"}, "right": {"ind": "ema", "period": 20}}, "stops": {}},
    # มีรอบเปิดค้างถึงวันสุดท้าย (ไม่มีกฎออก) -> ต้องไม่หักต้นทุนฝั่งขายที่ engine ไม่ได้จ่าย
    {"entry": {"op": ">", "left": {"price": "close"}, "right": {"ind": "sma", "period": 30}}, "stops": {"max_hold_days": 400}},
])
def test_replication_with_costs_is_tight_not_just_close(strategy):
    """ต้นทุนต้องหักทั้งฝั่งซื้อและขายและตรงกับ engine (ผลต่างน้อยกว่า 0.02 จุด) — กันหักผิดข้าง/ซ้ำ/ขาด"""
    s = sp(strategy, weights=(0.3, 0.3, 0.2), costs={"commission_bps": 20, "slippage_bps": 30})
    mk = market(3)
    res = run_strategy(s, mk.bars, mk.bench)
    assert res["stats"]["trade_count"] >= 4
    rep = BL.random_baseline(s, mk, res, "total_return", 100, 1)["replication"]
    assert abs(rep["total_return_diff"]) < 2e-4, rep["total_return_diff"]


def test_replication_with_costs_close_and_flags_rebalance():
    s = sp(strategy={"entry": {"op": ">", "left": {"price": "close"}, "right": {"ind": "sma", "period": 30}}, "stops": {}},
           costs={"commission_bps": 5, "slippage_bps": 10}, rebalance={"mode": "calendar", "frequency": "monthly"})
    mk = market(3)
    res = run_strategy(s, mk.bars, mk.bench)
    out = BL.random_baseline(s, mk, res, "total_return", 100, 1)
    assert abs(out["replication"]["total_return_diff"]) < 0.1
    assert any(w["code"] == "rebalance_ignored" for w in out["warnings"])


def cycle_prices(n, up=0.01, period=60, seed=0):
    """ขึ้นต่อเนื่อง period วัน แล้วลงต่อเนื่อง period วัน — กฎตามเทรนด์มีข้อมูลจริงให้จับได้ ส่วนการสุ่มจังหวะไม่มี"""
    rng, p, out = random.Random(seed), 100.0, []
    for i in range(n):
        d = up if (i // period) % 2 == 0 else -up
        p *= math.exp(d + 0.002 * rng.gauss(0, 1))
        out.append(p)
    return out


def cycle_market(n=NW + WARM):
    bars = {s: gapless("2019-01-01", cycle_prices(n, seed=i)) for i, s in enumerate(SYMS)}
    return Market(bars, BENCH)


def test_baseline_detects_real_timing_information_and_rejects_reverse():
    mk = cycle_market()
    trend = {"entry": {"op": ">", "left": {"price": "close"}, "right": {"ind": "sma", "period": 10}}, "stops": {}}
    contra = {"entry": {"op": "<", "left": {"price": "close"}, "right": {"ind": "sma", "period": 10}}, "stops": {}}
    good, bad = sp(trend, weights=(0.33, 0.33, 0.33)), sp(contra, weights=(0.33, 0.33, 0.33))
    rg = run_strategy(good, mk.bars, mk.bench)
    og = BL.random_baseline(good, mk, rg, "total_return", 400, 3)
    assert og["stats"]["total_return"]["beats_fraction"] > 0.97 and og["stats"]["total_return"]["p_as_good"] < 0.03
    rb = run_strategy(bad, mk.bars, mk.bench)
    ob = BL.random_baseline(bad, mk, rb, "total_return", 400, 3)
    assert ob["stats"]["total_return"]["beats_fraction"] < 0.03 and ob["stats"]["total_return"]["p_as_good"] > 0.9


def test_baseline_pvalue_roughly_uniform_when_no_information():
    """ข้อมูลสุ่มล้วน + กฎที่ไม่มีข้อมูล: p ต้องไม่ต่ำผิดปกติบ่อย (ตรวจว่าวิธีไม่เอนเอียงไปทางพบ 'edge' ปลอม)"""
    ps = []
    for seed in range(12):
        mk = market(100 + seed, drift=0.0, vol=0.015)
        s = sp({"entry": {"op": ">", "left": {"price": "close"}, "right": {"ind": "sma", "period": 20}}, "stops": {}})
        res = run_strategy(s, mk.bars, mk.bench)
        if res["stats"]["trade_count"] < 4:
            continue
        ps.append(BL.random_baseline(s, mk, res, "total_return", 200, seed)["stats"]["total_return"]["p_as_good"])
    assert len(ps) >= 10
    assert sum(1 for p in ps if p < 0.05) <= 3 and 0.2 < sum(ps) / len(ps) < 0.8


def test_baseline_seed_bonferroni_metric_fallback_and_hist():
    s, mk = sp(), market()
    res = run_strategy(s, mk.bars, mk.bench)
    a = BL.random_baseline(s, mk, res, "calmar", 200, 11)
    b = BL.random_baseline(s, mk, res, "calmar", 200, 11)
    c = BL.random_baseline(s, mk, res, "calmar", 200, 12)
    assert a == b and a["stats"] != c["stats"]
    t = BL.random_baseline(s, mk, res, "calmar", 200, 11, trials=49)
    h, h1 = t["stats"]["calmar"], a["stats"]["calmar"]
    assert h["p_as_good"] == h1["p_as_good"] and h["p_bonferroni"] == pytest.approx(min(1.0, h1["p_as_good"] * 49))
    assert 1 / 201 <= h1["p_as_good"] <= 1.0
    hist = a["histogram"]
    assert len(hist["counts"]) == BL.HIST_BINS and len(hist["edges"]) == BL.HIST_BINS + 1 and sum(hist["counts"]) == a["stats"]["calmar"]["n"]
    short_start = DATES[WARM]
    short = spec([{"symbol": x, "weight": 0.3} for x in SYMS], short_start, DATES[WARM + 150], strategy=STRAT)
    rs = run_strategy(short, mk.bars, mk.bench)
    o = BL.random_baseline(short, mk, rs, "calmar", 100, 1) if rs["stats"]["trade_count"] else None
    if o:
        assert o["metric"] == "total_return" and o["notes"]                                       # ช่วง < 1 ปี: CAGR/Calmar ไม่มี -> ใช้ผลตอบแทนรวม


def test_baseline_errors_and_limits():
    mk = market()
    plain = spec([{"symbol": x, "weight": 0.3} for x in SYMS], START, END)
    res_plain = run_backtest(plain, mk.bars, mk.bench)
    with pytest.raises(SR.SearchError):
        BL.random_baseline(plain, mk, res_plain, "calmar", 100, 1)                                # ไม่มีกลยุทธ์
    never = sp({"entry": {"op": ">", "left": {"price": "close"}, "right": {"value": 1e9}}, "stops": {}})
    rn = run_strategy(never, mk.bars, mk.bench)
    with pytest.raises(SR.SearchError):
        BL.random_baseline(never, mk, rn, "calmar", 100, 1)                                       # ไม่เคยเข้า
    s = sp()
    res = run_strategy(s, mk.bars, mk.bench)
    trunc = copy.deepcopy(res)
    trunc["strategy_result"]["trips"] = trunc["strategy_result"]["trips"][:-1]
    with pytest.raises(SR.SearchError):
        BL.random_baseline(s, mk, trunc, "total_return", 100, 1)                                  # รอบไม่ครบ
    with pytest.raises(SR.SearchError):
        BL.random_baseline(s, mk, res, "sharpe", 100, 1)
    with pytest.raises(SR.SearchError):
        BL.random_baseline(s, mk, {**res, "series": res["series"][:-1]}, "total_return", 100, 1)  # วันที่ไม่ตรง
    old = BL.MAX_WORK
    BL.MAX_WORK = 1000
    try:
        with pytest.raises(SR.SearchError):
            BL.random_baseline(s, mk, res, "total_return", 100, 1)
    finally:
        BL.MAX_WORK = old
    import threading
    ev = threading.Event()
    ev.set()
    with pytest.raises(SR.Aborted):
        BL.random_baseline(s, mk, res, "total_return", 100, 1, cancel=ev)


# ------------------------------------------------------------------ endpoint (end-to-end ผ่านระบบหลัก)
ND = 1100
E_BENCH = mk_bars("2020-01-01", ND, lambda i: 100 * 1.0004 ** i)
E_SERIES = {"AAA": gapless("2020-01-01", walk(7, ND)), "BBB": gapless("2020-01-01", walk(8, ND))}


class EProv:
    name = "yahoo"

    def get_bars(self, symbol, start, end):
        src = E_BENCH if symbol == "^GSPC" else E_SERIES.get(symbol, [])
        return [b for b in src if start.isoformat() <= b["date"] <= end.isoformat()]


E_SPEC = {"start": "2022-02-01", "end": "2024-02-28", "initial_capital": 100000,
          "positions": [{"symbol": "AAA", "weight": 0.5}, {"symbol": "BBB", "weight": 0.5}],
          "costs": {"commission_bps": 0, "slippage_bps": 5},
          "strategy": {"entry": {"op": ">", "left": {"price": "close"}, "right": {"ind": "sma", "period": 30}},
                       "exit": {"op": "<", "left": {"price": "close"}, "right": {"ind": "sma", "period": 30}},
                       "stops": {"stop_loss_pct": 10}}}


def e_services():
    return H.Services(MemoryRunStore(), PriceStore(EProv(), MemoryBackend()), RunPool(2, 60), RateLimiter(50, 600))


def test_endpoints_end_to_end_isolation_errors_and_limits(monkeypatch):
    monkeypatch.setattr(SH, "_limiter", RateLimiter(500, 600))

    async def go():
        s = e_services()
        st, out = await H.create_run(s, "a@x.com", {"spec": E_SPEC})
        rid = out["id"]
        assert (await SH.sweep(s, "a@x.com", rid, {}))[0] == 409                                     # ยังไม่เสร็จ
        await finish(s)
        st, tn = await SH.tunables(s, "a@x.com", rid)
        ids = [t["id"] for t in tn["tunables"]]
        assert st == 200 and "stops.stop_loss_pct" in ids and "entry.right.params.period" in ids and tn["limits"]["max_cells"] == SR.MAX_CELLS
        assert (await SH.tunables(s, "b@x.com", rid))[0] == 404 and (await SH.tunables(s, "a@x.com", "nope"))[0] == 404
        p2 = [{"id": "entry.right.params.period", "min": 10, "max": 50, "steps": 3}, {"id": "stops.stop_loss_pct", "values": [5, 10]}]
        st, sw = await SH.sweep(s, "a@x.com", rid, {"params": p2, "metric": "total_return"})
        assert st == 200 and sw["trials"] == 6 and sw["base"] == {"i": 1, "j": 1}
        assert (await SH.sweep(s, "b@x.com", rid, {"params": p2}))[0] == 404                         # คนอื่นเข้าไม่ได้
        assert (await SH.sweep(s, "a@x.com", rid, {"params": p2, "metric": "sharpe"}))[0] == 400
        assert (await SH.sweep(s, "a@x.com", rid, {"params": [{"id": "x.y", "values": [1, 2]}]}))[0] == 400
        assert (await SH.sweep(s, "a@x.com", rid, {"params": []}))[0] == 400
        st, wf = await SH.walkforward(s, "a@x.com", rid, {"params": p2[:1], "metric": "total_return", "folds": 2})
        assert st == 200 and wf["kind"] == "walk_forward" and len(wf["folds"]) == 2
        assert (await SH.walkforward(s, "a@x.com", rid, {"params": p2[:1], "folds": 99}))[0] == 400
        assert (await SH.walkforward(s, "a@x.com", rid, {"params": p2[:1], "anchored": "yes"}))[0] == 400
        st, rb = await SH.random_baseline(s, "a@x.com", rid, {"sims": 150, "metric": "total_return", "trials": 6})
        assert st == 200 and rb["trials"] == 6 and rb["sims"] == 150
        st, rb2 = await SH.random_baseline(s, "a@x.com", rid, {"sims": 150, "metric": "total_return", "trials": 6})
        assert rb2 == rb                                                                             # seed เริ่มต้นผูกกับ run id -> ทำซ้ำได้
        assert (await SH.random_baseline(s, "a@x.com", rid, {"sims": 5}))[0] == 400
        assert (await SH.random_baseline(s, "a@x.com", rid, {"metric": "sortino"}))[0] == 400
        assert (await SH.random_baseline(s, "b@x.com", rid, {}))[0] == 404
        # รันแบบไม่มีกลยุทธ์ -> 400 no_strategy
        plain = {k: v for k, v in E_SPEC.items() if k != "strategy"}
        st, o2 = await H.create_run(s, "d@x.com", {"spec": plain})
        await finish(s)
        st, r = await SH.sweep(s, "d@x.com", o2["id"], {"params": p2})
        assert st == 400 and r["code"] == "no_strategy"
    asyncio.run(go())


def test_sweep_loads_enough_history_for_longest_period(monkeypatch):
    """ค่าช่วงยาวที่สุดใน grid ต้องมีประวัติก่อนวันเริ่มพอ ไม่ใช่เผื่อแค่ตามค่าเดิมของกลยุทธ์"""
    seen = []
    mk = market()
    monkeypatch.setattr(SH, "load_market", lambda sp_, ps, ff, e: (seen.append(ff), mk)[1])
    s = sp()
    chosen, g_small = pick(s, (EMA_ID, {"values": [20, 50]}))
    _, g_big = pick(s, (EMA_ID, {"values": [50, 300]}))
    SH._load_for_variants(s, chosen, g_small, None)
    SH._load_for_variants(s, chosen, g_big, None)
    assert seen[1] < seen[0]
    assert (date.fromisoformat(s["start"]) - seen[1]).days >= int(5 * 300 * 1.5)                       # EMA(300) ต้องการ 5×300 แท่ง


def test_search_rate_limit_per_user_and_cancel_on_timeout(monkeypatch):
    monkeypatch.setattr(SH, "_limiter", RateLimiter(2, 600))

    async def go():
        s = e_services()
        _, out = await H.create_run(s, "a@x.com", {"spec": E_SPEC})
        await finish(s)
        p = [{"id": "stops.stop_loss_pct", "values": [5, 10]}]
        codes = [(await SH.sweep(s, "a@x.com", out["id"], {"params": p, "metric": "total_return"}))[0] for _ in range(3)]
        assert codes == [200, 200, 429]
        assert (await SH.sweep(s, "b@x.com", out["id"], {"params": p}))[0] == 404                    # ผู้ใช้อื่นไม่ได้รับผลกระทบ/เข้าไม่ได้
        # หมดเวลา: ต้องสั่ง cancel ให้ thread หยุด ไม่ปล่อยค้าง
        s2 = e_services()
        _, o2 = await H.create_run(s2, "a@x.com", {"spec": E_SPEC})
        await finish(s2)
        s2.pool.timeout_s = 0.05
        flag = {}

        def slow(sp_, mk, chosen, grids, metric, cancel=None):
            import time
            for _ in range(200):
                if cancel is not None and cancel.is_set():
                    flag["stopped"] = True
                    raise SR.Aborted()
                time.sleep(0.01)
            return {}
        monkeypatch.setattr(SR, "sweep", slow)
        monkeypatch.setattr(SH, "_limiter", RateLimiter(50, 600))
        st, r = await SH.sweep(s2, "a@x.com", o2["id"], {"params": p})
        assert st == 504 and r["code"] == "timeout"
        await asyncio.sleep(0.3)
        assert flag.get("stopped") is True
    asyncio.run(go())


def test_router_registers_all_routes():
    pytest.importorskip("fastapi")
    from fastapi import APIRouter
    from backtest_lab.robust.router import register
    r = APIRouter()
    register(r, lambda: None, lambda a: "x", lambda t: t)
    paths = {(tuple(sorted(x.methods)), x.path) for x in r.routes}
    for p in ("montecarlo", "robustness", "sweep", "walkforward", "randombaseline"):
        assert (("POST",), f"/runs/{{run_id}}/{p}") in paths
    assert (("GET",), "/runs/{run_id}/tunables") in paths
