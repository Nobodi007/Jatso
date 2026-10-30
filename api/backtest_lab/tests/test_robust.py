import asyncio
import copy
import math

import pytest

from backtest_lab.api import handlers as H
from backtest_lab.engine.strategy_runner import run_strategy
from backtest_lab.robust import handlers as RH
from backtest_lab.robust import montecarlo as MC
from backtest_lab.robust import stability as ST
from backtest_lab.tests.helpers import mk_bars, spec
from backtest_lab.tests.test_handlers import BENCH as HBENCH, SPEC, finish, services

NB = 250
BENCH = mk_bars("2023-12-28", NB + 5, lambda i: 100 * 1.0005 ** i)


# ------------------------------------------------------------------ Monte Carlo
def test_percentile_exact():
    assert MC.percentile([1, 2, 3, 4, 5], 50) == 3
    assert MC.percentile([1, 2, 3, 4, 5], 25) == 2
    assert MC.percentile([0, 10], 50) == 5


def test_constant_returns_every_path_identical():
    r = [0.001] * 120
    out = MC.simulate(r, r, sims=200, horizon=100, block=7, seed=1)
    exp = 1.001 ** 100 - 1
    for k in ("p5", "p50", "p95"):
        assert out["final_return"][k] == pytest.approx(exp, rel=1e-12)
    assert out["max_drawdown"]["p5"] == 0
    assert out["prob"]["loss"] == 0 and out["prob"]["beat_benchmark"] == 0     # benchmark เหมือนกัน ไม่มี "ชนะ" เด็ดขาด


def test_all_losing_days_drawdown_equals_final():
    r = [-0.002] * 80
    out = MC.simulate(r, r, sims=100, horizon=60, block=5, seed=3)
    assert out["max_drawdown"]["p50"] == pytest.approx(out["final_return"]["p50"], rel=1e-12)
    assert out["prob"]["loss"] == 1.0


def test_seed_reproducible_and_different_seed_differs():
    import random
    rnd = random.Random(1)
    rp = [rnd.gauss(0.0004, 0.012) for _ in range(300)]
    rb = [x * 0.8 for x in rp]
    a = MC.simulate(rp, rb, sims=300, seed=5)
    b = MC.simulate(rp, rb, sims=300, seed=5)
    c = MC.simulate(rp, rb, sims=300, seed=6)
    assert a == b and a["final_return"] != c["final_return"]


def test_distribution_structure_and_fan():
    import random
    rnd = random.Random(2)
    rp = [rnd.gauss(0.0005, 0.01) for _ in range(300)]
    out = MC.simulate(rp, rp, sims=400, horizon=250, block=21, seed=9, actual_final=0.1)
    fr = out["final_return"]
    assert fr["p5"] <= fr["p25"] <= fr["p50"] <= fr["p75"] <= fr["p95"]
    f = out["fan"]
    assert f["x"][0] == 0 and f["x"][-1] == 249
    for i in range(len(f["x"])):
        assert f["p5"][i] <= f["p50"][i] <= f["p95"][i]
    assert f["p50"][-1] == pytest.approx(fr["p50"], rel=1e-12)              # จุดสุดท้ายของพัดคือผลสุดท้าย
    assert out["max_drawdown"]["p95"] <= 0
    assert "actual" not in out                                               # horizon ≠ จำนวนวันจริง
    out2 = MC.simulate(rp, rp, sims=100, seed=1, actual_final=0.1)
    assert 0 <= out2["actual"]["percentile_rank"] <= 1
    assert "not_a_forecast" in out["labels"]


def test_positive_drift_has_positive_mean_and_block1_vs_block_n_valid():
    rp = [0.0006 if i % 2 else -0.0002 for i in range(200)]
    for blk in (1, 21, 200):
        out = MC.simulate(rp, rp, sims=100, horizon=200, block=blk, seed=4)
        assert out["final_return"]["mean"] > 0


@pytest.mark.parametrize("kw", [dict(sims=99), dict(sims=5001), dict(horizon=10), dict(block=0), dict(block=253),
                                dict(sims=5000, horizon=7000)])
def test_limits(kw):
    r = [0.001] * 120
    with pytest.raises(MC.MCError):
        MC.simulate(r, r, **{"sims": 200, **kw})
    with pytest.raises(MC.MCError):
        MC.simulate([0.0] * 10, [0.0] * 10, sims=200)


# ------------------------------------------------------------------ Stability
def strat(ind_period=10, **stops):
    return {"entry": {"op": ">", "left": {"price": "close"}, "right": {"ind": "ema", "period": ind_period}},
            "stops": stops}


def wavy(i):
    return 100 * (1 + 0.06 * math.sin(i / 7)) * 1.0008 ** i


def test_split_windows_partition():
    dates = [f"d{i:03d}" for i in range(103)]
    w = ST.split_windows(dates, 4)
    assert len(w) == 4 and w[0][0] == dates[0] and w[-1][1] == dates[-1]
    for (a, b), (c, d) in zip(w, w[1:]):
        assert dates.index(c) == dates.index(b) + 1                          # ต่อกันพอดี ไม่ซ้อน ไม่ตกหล่น


def test_window_test_and_summary():
    a = mk_bars("2023-12-28", NB + 5, wavy)
    sp = spec([{"symbol": "AAA", "weight": 1.0}], "2024-01-02", "2024-12-13", strategy=strat(10))
    res = run_strategy(sp, {"AAA": a}, BENCH)
    dates = [x["date"] for x in res["series"]]
    out = ST.window_test(sp, {"AAA": a}, BENCH, dates, 4)
    assert out["summary"]["windows"] == 4 and not out["skipped"]
    assert out["windows"][0]["start"] == dates[0] and out["windows"][-1]["end"] == dates[-1]
    assert 0 <= out["summary"]["beat_benchmark"] <= 4


def test_scaled_variant_identity_scaling_and_no_mutation():
    sp = spec([{"symbol": "AAA", "weight": 1.0}], "2024-01-02", "2024-12-13",
              strategy={"entry": {"all": [{"op": ">", "left": {"price": "close"}, "right": {"ind": "ema", "period": 20}},
                                          {"op": ">", "left": {"ind": "macd", "fast": 12, "slow": 26, "signal": 9, "output": "hist"}, "right": {"value": 0}}]},
                        "stops": {"stop_loss_pct": 10, "max_hold_days": 40}})
    before = copy.deepcopy(sp)
    v = ST.scaled_variant(sp, "indicators", 0.5)
    assert sp == before                                                       # ไม่แก้ spec เดิม
    ops = [o for o in ST._walk(v["strategy"]["entry"]) if o["kind"] == "ind"]
    assert ops[0]["params"]["period"] == 10
    assert (ops[1]["params"]["fast"], ops[1]["params"]["slow"], ops[1]["params"]["signal"]) == (6, 13, 4)
    v1 = ST.scaled_variant(sp, "indicators", 1.0)
    assert v1["strategy"] == sp["strategy"]
    s = ST.scaled_variant(sp, "stops", 1.5)
    assert s["strategy"]["stops"]["stop_loss_pct"] == 15.0 and s["strategy"]["stops"]["max_hold_days"] == 60
    tiny = ST.scaled_variant(spec([{"symbol": "AAA", "weight": 1.0}], "2024-01-02", "2024-12-13", strategy=strat(2)), "indicators", 0.5)
    assert [o for o in ST._walk(tiny["strategy"]["entry"]) if o["kind"] == "ind"][0]["params"]["period"] == 2   # ไม่ต่ำกว่าขอบล่าง
    assert ST.scaled_variant(sp, "indicators", 1.0) is not None
    only_ind = spec([{"symbol": "AAA", "weight": 1.0}], "2024-01-02", "2024-12-13", strategy=strat(10))
    assert ST.scaled_variant(only_ind, "stops", 1.5) is None                  # ไม่มี stop ให้ขยับ


def test_sensitivity_baseline_matches_original_run():
    a = mk_bars("2023-12-28", NB + 5, wavy)
    sp = spec([{"symbol": "AAA", "weight": 1.0}], "2024-01-02", "2024-12-13", strategy=strat(10, stop_loss_pct=8))
    res = run_strategy(sp, {"AAA": a}, BENCH)
    out = ST.sensitivity(sp, {"AAA": a}, BENCH)
    assert out["available"] and set(out["families"]) == {"indicators", "stops"}
    for fam in out["families"].values():
        assert [r["factor"] for r in fam["rows"]] == list(ST.FACTORS)
        base = next(r for r in fam["rows"] if r["factor"] == 1.0)
        assert base["portfolio"]["total_return"] == pytest.approx(res["comparison"]["portfolio"]["total_return"]["value"], rel=1e-12)
        assert fam["summary"]["min"] <= fam["summary"]["median"] <= fam["summary"]["max"]
    plain = spec([{"symbol": "AAA", "weight": 1.0}], "2024-01-02", "2024-12-13")
    assert ST.sensitivity(plain, {"AAA": a}, BENCH)["available"] is False


# ------------------------------------------------------------------ handlers
STRAT_SPEC = {**SPEC, "strategy": {"entry": {"op": ">", "left": {"price": "close"}, "right": {"ind": "sma", "period": 20}},
                                   "stops": {"stop_loss_pct": 10}}}


def test_handlers_end_to_end_isolation_and_errors():
    async def go():
        s = services()
        st, out = await H.create_run(s, "a@x.com", {"spec": STRAT_SPEC})
        rid = out["id"]
        st, _ = await RH.montecarlo(s, "a@x.com", rid, {"sims": 200})
        assert st == 409                                                    # ยังไม่เสร็จ
        await finish(s)
        st, mc = await RH.montecarlo(s, "a@x.com", rid, {"sims": 200, "block_days": 10})
        assert st == 200 and mc["params"]["sims"] == 200 and "not_a_forecast" in mc["labels"]
        st, mc2 = await RH.montecarlo(s, "a@x.com", rid, {"sims": 200, "block_days": 10})
        assert mc2 == mc                                                    # seed เริ่มต้นผูกกับ run id -> ทำซ้ำได้
        assert (await RH.montecarlo(s, "b@x.com", rid, {}))[0] == 404       # คนอื่นเข้าไม่ได้
        assert (await RH.montecarlo(s, "a@x.com", rid, {"sims": 10}))[0] == 400
        assert (await RH.montecarlo(s, "a@x.com", rid, {"sims": True}))[0] == 400
        assert (await RH.montecarlo(s, "a@x.com", "nope", {}))[0] == 404
        st, rb = await RH.run_robustness(s, "a@x.com", rid, {"windows": 3})
        assert st == 200 and len(rb["window_test"]["windows"]) == 3
        assert rb["sensitivity"]["available"] and "indicators" in rb["sensitivity"]["families"]
        assert (await RH.run_robustness(s, "a@x.com", rid, {"windows": 99}))[0] == 400
        assert (await RH.run_robustness(s, "b@x.com", rid, {}))[0] == 404
    asyncio.run(go())
