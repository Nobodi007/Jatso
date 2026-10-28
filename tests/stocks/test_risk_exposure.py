import math
import pytest
from stocks import risk_exposure as X
from stocks import risk_engine as E

ap = lambda x, rel=1e-9: pytest.approx(x, rel=rel, abs=1e-12)

def rets(seed, n=120, beta=1.0, bench=None):
    import random
    random.seed(seed)
    base = bench or [random.gauss(0, 0.01) for _ in range(n)]
    return base, [beta * b + random.gauss(0, 0.005) for b in base]

H = {"AAA": {"qty": 10, "price": 100.0, "avg_cost": 90.0}, "BBB": {"qty": 5, "price": 200.0, "avg_cost": 210.0}}

def test_exposure_weights_hhi_sector():
    out = X.exposure(H, 1000.0, {"AAA": "Tech", "BBB": "Tech"})
    assert out["nav"] == ap(3000) and out["cash_weight"] == ap(1 / 3)
    assert out["hhi"]["value"] == ap(0.5) and out["effective_n"]["value"] == ap(2)
    assert out["top1"]["value"] == ap(0.5)
    assert out["sectors"][0]["sector"] == "Tech" and out["sectors"][0]["weight_nav"] == ap(2 / 3)
    assert out["positions"][0]["unrealized_pnl"] == ap(100.0) or out["positions"][0]["unrealized_pnl"] == ap(-50.0)

def test_unknown_sector_and_empty():
    assert X.exposure(H, 0.0, {})["sectors"][0]["sector"] == "Unknown"
    assert X.exposure({}, 500.0, {})["hhi"]["status"] == E.UNDEFINED

def test_risk_decomposition_identities():
    b, a = rets(1); _, c = rets(2, bench=b, beta=0.5)
    w = {"AAA": 0.5, "BBB": 0.3}
    out = X.risk_decomposition(w, {"AAA": a, "BBB": c})
    sig = out["portfolio_volatility"]["value"]
    import numpy as np
    S = np.cov(np.array([a, c]), ddof=1) * 252
    ww = np.array([0.5, 0.3])
    assert sig == ap(math.sqrt(ww @ S @ ww), 1e-9)
    assert sum(r["ccr"] for r in out["contributions"]) == ap(sig)
    assert sum(r["pct_of_risk"] for r in out["contributions"]) == ap(1.0)
    corr = np.corrcoef(a, c)[0, 1]
    assert out["correlation"]["matrix"][0][1] == ap(corr)
    assert out["avg_pairwise_correlation"]["value"] == ap(corr)

def test_decomposition_insufficient_and_excluded():
    _, a = rets(3, n=30)
    assert X.risk_decomposition({"AAA": 1.0}, {"AAA": a})["portfolio_volatility"]["status"] == E.INSUFFICIENT
    _, a = rets(3); bad = a[:]; bad[5] = None
    out = X.risk_decomposition({"AAA": 0.5, "BBB": 0.5}, {"AAA": a, "BBB": bad})
    assert out["excluded"][0]["symbol"] == "BBB" and out["portfolio_volatility"]["status"] == E.LIMITED

def test_stress_beta_and_explicit():
    b, a = rets(4, beta=2.0)
    betas = X.holding_betas({"AAA": a, "BBB": [None] * len(a)}, b)
    assert betas["AAA"].value == pytest.approx(2.0, abs=0.3) and betas["BBB"].value is None
    out = X.stress(H, 1000.0, betas, -0.10, {"BBB": -0.5})
    assert out["hypothetical"] and out["skipped"] == []
    bb = next(r for r in out["positions"] if r["symbol"] == "BBB")
    assert bb["pnl"] == ap(-500.0)
    aa = next(r for r in out["positions"] if r["symbol"] == "AAA")
    assert aa["shock"] == ap(betas["AAA"].value * -0.10)
    assert out["nav_after"] == ap(out["nav_before"] + out["pnl"])
    only = X.stress(H, 1000.0, betas, -0.10, {})
    assert only["skipped"][0]["symbol"] == "BBB"

def test_stress_floor_and_no_benchmark():
    betas = X.holding_betas({"AAA": [0.01] * 70}, None)
    assert betas["AAA"].status == E.UNAVAILABLE
    big = {"AAA": E.Metric(5.0, "ok", "", "", 100)}
    out = X.stress({"AAA": {"qty": 1, "price": 100.0}}, 0.0, big, -0.5, {})
    assert out["positions"][0]["shock"] == -1.0 and out["pnl"] == ap(-100.0)


def _flat_betas(*syms):
    return {s: E.Metric(1.0, "ok", "", "", 100) for s in syms}

def test_stress_sector_shock_priority_and_by_sector():
    h = {"AAA": {"qty": 10, "price": 100.0}, "BBB": {"qty": 5, "price": 200.0}, "CCC": {"qty": 1, "price": 50.0}}
    sec = {"AAA": "Tech", "BBB": "Tech", "CCC": None}
    out = X.stress(h, 0.0, _flat_betas("AAA", "BBB", "CCC"), -0.10, {"BBB": -0.5}, sec, {"Tech": -0.2})
    by = {r["symbol"]: r for r in out["positions"]}
    assert by["BBB"]["pnl"] == ap(-500.0) and by["BBB"]["basis"] == "explicit symbol shock"   # รายตัวชนะ sector
    assert by["AAA"]["pnl"] == ap(-200.0) and by["AAA"]["basis"] == "sector shock"            # sector ชนะ beta
    assert by["CCC"]["basis"].startswith("β") and by["CCC"]["sector"] == "Unknown"            # ที่เหลือใช้ beta × ตลาด
    bs = {r["sector"]: r for r in out["by_sector"]}
    assert bs["Tech"]["pnl"] == ap(-700.0) and bs["Tech"]["market_value"] == ap(2000.0)
    assert bs["Unknown"]["pnl"] == ap(-5.0)
    assert sum(r["pnl"] for r in out["by_sector"]) == ap(out["pnl"])
    assert out["by_sector"][0]["sector"] == "Tech"                                            # เรียงขาดทุนมากสุดก่อน
    assert out["scenario"]["sector_shocks"] == {"Tech": -0.2}

def test_stress_without_sectors_has_no_by_sector_and_ignores_sector_shocks():
    h = {"AAA": {"qty": 10, "price": 100.0}}
    out = X.stress(h, 0.0, _flat_betas("AAA"), -0.10, {}, None, {"Tech": -0.9})
    assert "by_sector" not in out and out["positions"][0]["sector"] is None
    assert out["positions"][0]["shock"] == ap(-0.10)

def test_stress_sector_only_scenario_skips_unshocked_sectors():
    h = {"AAA": {"qty": 10, "price": 100.0}, "BBB": {"qty": 1, "price": 100.0}}
    out = X.stress(h, 0.0, {}, None, {}, {"AAA": "Tech", "BBB": "Energy"}, {"Tech": -0.3})
    assert [r["symbol"] for r in out["positions"]] == ["AAA"] and out["skipped"][0]["symbol"] == "BBB"
    assert out["pnl"] == ap(-300.0)
