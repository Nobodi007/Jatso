"""T-bill risk-free + attribution + exposure (รอบ risk panel)"""
import copy
import datetime as dt
import math
import random
from datetime import date

import pytest

from backtest_lab.data.price_store import MemoryBackend, PriceStore
from backtest_lab.data.provider_base import ProviderError
from backtest_lab.data.rates import FmpRates, KEY, RateStore
from backtest_lab.engine.execution import Account
from backtest_lab.engine.runner import run_backtest
from backtest_lab.engine.spec import SpecError, spec_hash, validate_spec
from backtest_lab.engine.strategy_runner import run_strategy
from backtest_lab.metrics import attribution as ATT, core as M, exposure as EXP
from backtest_lab.metrics.riskfree import daily_rf, describe
from backtest_lab.service import build_result
from backtest_lab.tests.helpers import mk_bars, spec

TODAY = date(2025, 1, 1)
N = 330
A = mk_bars("2023-12-28", N, lambda i: (100 * (1 + 0.0008 * i + 0.04 * math.sin(i / 7)),) * 2)
B = mk_bars("2023-12-28", N, lambda i: (50 * (1 + 0.0004 * i + 0.06 * math.cos(i / 5)),) * 2)
BE = mk_bars("2023-12-28", N, lambda i: 4000 * 1.0004 ** i)
POS = [{"symbol": "AAA", "weight": 0.5}, {"symbol": "BBB", "weight": 0.4}]
COSTS = {"commission_bps": 3, "slippage_bps": 5}


def vs(positions=POS, **kw):
    return validate_spec(spec(positions, "2024-01-02", "2024-12-13", **kw), today=TODAY)


STRAT = {"entry": {"op": ">", "left": {"price": "close"}, "right": {"ind": "sma", "period": 10}},
         "exit": {"op": "<", "left": {"price": "close"}, "right": {"ind": "sma", "period": 10}},
         "stops": {"stop_loss_pct": 6.0, "take_profit_pct": 12.0}}


def flat_rates(y, start="2023-11-01", n=480):
    d0 = date.fromisoformat(start)
    return {d0 + dt.timedelta(days=i): y for i in range(n)}


# ------------------------------------------------------------------ riskfree
def dates_of(k=5, start=date(2024, 1, 2)):
    return [start + dt.timedelta(days=i) for i in range(k + 1)]


def test_daily_rf_uses_previous_day_yield_not_same_day():
    ds = dates_of(4)                                   # base + 4 วัน
    rates = {ds[0]: 0.04, ds[1]: 0.05, ds[2]: 0.06}    # yield ประกาศวัน ds[1] ต้องถูกใช้กับผลตอบแทนวัน ds[2]
    rf = daily_rf(rates, ds)
    assert rf[0] == pytest.approx(M.daily_rate(0.04))  # ผลตอบแทนวัน ds[1] ใช้ yield ณ ds[0]
    assert rf[1] == pytest.approx(M.daily_rate(0.05))  # วัน ds[2] ใช้ yield ณ ds[1]
    assert rf[2] == pytest.approx(M.daily_rate(0.06))
    assert rf[3] == pytest.approx(M.daily_rate(0.06))  # ไม่มีค่าใหม่ -> ใช้ค่าล่าสุด


def test_daily_rf_gap_and_missing_give_none_not_guess():
    ds = dates_of(3)
    assert daily_rf(None, ds) is None and daily_rf({}, ds) is None
    one = dates_of(1)                                                         # ผลตอบแทนวันเดียว อ้างอิงวัน one[0]
    assert daily_rf({one[0] - dt.timedelta(days=8): 0.04}, one) is None       # เก่าเกิน 7 วัน
    assert daily_rf({one[0] - dt.timedelta(days=7): 0.04}, one) is not None   # พอดี 7 วันยังรับ
    assert daily_rf({ds[0] - dt.timedelta(days=7): 0.04}, ds) is None         # วันถัดไปห่างเกิน 7 วัน -> ทั้งชุดใช้ไม่ได้ (เหมือน Risk Center)
    assert daily_rf({ds[1]: 0.04}, ds) is None                                # ยังไม่มีค่าก่อนวันแรก


def test_zero_yield_is_valid_not_dropped():
    ds = dates_of(3)
    rf = daily_rf({ds[0]: 0.0}, ds)
    assert rf == [0.0, 0.0, 0.0]
    assert describe({ds[0]: 0.0}, ds, rf)["avg_annual"] == pytest.approx(0.0, abs=1e-12)


def test_describe_statuses():
    ds = dates_of(3)
    assert describe(None, ds, None)["status"] == "no_data"
    assert describe({ds[0] - dt.timedelta(days=30): 0.04}, ds, None)["status"] == "unavailable"
    d = describe({ds[0]: 0.05}, ds, daily_rf({ds[0]: 0.05}, ds))
    assert d["status"] == "ok" and d["avg_annual"] == pytest.approx(0.05)


# ------------------------------------------------------------------ rate store
class FakeRates:
    name = "fake"

    def __init__(self, data=None, fail=False):
        self.data, self.fail, self.calls = data or {}, fail, []

    def get_rates(self, start, end):
        self.calls.append((start, end))
        if self.fail:
            raise ProviderError("boom")
        return {d: v for d, v in self.data.items() if start.isoformat() <= d <= end.isoformat()}


def mkdata(a, b, y=0.04):
    d, out = date.fromisoformat(a), {}
    while d <= date.fromisoformat(b):
        out[d.isoformat()] = y
        d += dt.timedelta(days=1)
    return out


def test_rate_store_caches_extends_head_and_tail():
    prov = FakeRates(mkdata("2020-01-01", "2024-12-31"))
    now = [dt.datetime(2024, 6, 1, tzinfo=dt.timezone.utc)]
    st = RateStore(prov, MemoryBackend(), ttl_seconds=10 ** 9, now_fn=lambda: now[0])
    r, _ = st.get_rates(date(2023, 1, 1), date(2023, 12, 31))
    assert len(r) == 365 and len(prov.calls) == 1
    st.get_rates(date(2023, 3, 1), date(2023, 6, 1))
    assert len(prov.calls) == 1                                    # อยู่ในช่วง cache แล้ว ไม่ยิงซ้ำ
    r, _ = st.get_rates(date(2022, 6, 1), date(2023, 12, 31))      # ขยายหัว
    assert prov.calls[-1] == (date(2022, 6, 1), date(2022, 12, 31)) and len(r) == 579
    r, _ = st.get_rates(date(2022, 6, 1), date(2024, 3, 31))       # ขยายท้าย (ซ้อนทับ 7 วัน)
    assert prov.calls[-1][0] == date(2023, 12, 24) and max(r) == date(2024, 3, 31)


def test_rate_store_stale_when_refresh_fails_but_cache_exists_and_raises_without_cache():
    prov = FakeRates(mkdata("2023-01-01", "2023-12-31"))
    now = [dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)]
    st = RateStore(prov, MemoryBackend(), ttl_seconds=60, now_fn=lambda: now[0])
    st.get_rates(date(2023, 1, 1), date(2023, 12, 31))
    prov.fail = True
    now[0] += dt.timedelta(hours=1)
    r, meta = st.get_rates(date(2023, 1, 1), date(2023, 12, 31))
    assert meta["stale"] and len(r) == 365
    with pytest.raises(ProviderError):
        RateStore(FakeRates(fail=True), MemoryBackend()).get_rates(date(2023, 1, 1), date(2023, 2, 1))


def test_fmp_rates_requires_key_and_parses_zero_and_chunks(monkeypatch):
    with pytest.raises(ProviderError):
        FmpRates(key="").get_rates(date(2024, 1, 1), date(2024, 2, 1))
    f = FmpRates(key="k")
    calls = []

    def fake_get(s, e):
        calls.append((s, e))
        return [{"date": s.isoformat(), "month3": 0.0}, {"date": e.isoformat(), "month3": 5.25}, {"date": "2024-01-01", "month3": None}]
    monkeypatch.setattr(f, "_get", fake_get)
    out = f.get_rates(date(2023, 1, 1), date(2023, 12, 31))          # 365 วัน -> 5 ช่วง ≤ 90 วัน
    assert len(calls) == 5 and all((e - s).days <= 89 for s, e in calls)
    assert out["2023-01-01"] == 0.0 and out["2023-03-31"] == pytest.approx(0.0525)
    monkeypatch.setattr(f, "_get", lambda s, e: {"Error Message": "x"})
    with pytest.raises(ProviderError):
        f.get_rates(date(2024, 1, 1), date(2024, 1, 5))


# ------------------------------------------------------------------ spec
def test_spec_risk_free_source_rules_and_hash_unchanged():
    base = vs()
    assert "risk_free_source" not in base
    h0 = spec_hash(base)
    assert spec_hash(vs()) == h0
    t = vs(risk_free_source="tbill")
    assert t["risk_free_source"] == "tbill" and spec_hash(t) != h0
    with pytest.raises(SpecError):
        vs(risk_free_source="tbill", risk_free_annual=0.03)
    with pytest.raises(SpecError):
        vs(risk_free_source="libor")
    assert vs(risk_free_source=None) == base


# ------------------------------------------------------------------ engine + rf
def test_engine_tbill_matches_manual_series_both_runners():
    rates = flat_rates(0.04)
    for runner, sp in ((run_backtest, vs(costs=COSTS)), (run_strategy, vs(costs=COSTS, strategy=STRAT))):
        sp = {**sp, "risk_free_source": "tbill"}
        if runner is run_backtest:
            r = runner(sp, {"AAA": A, "BBB": B}, BE, rates)
        else:
            r = runner(sp, {"AAA": A, "BBB": B}, BE, None, None, rates)
        ref_sp = {k: v for k, v in sp.items() if k != "risk_free_source"}
        ref_sp["risk_free_annual"] = 0.04
        r2 = (runner(ref_sp, {"AAA": A, "BBB": B}, BE) if runner is run_backtest
              else runner(ref_sp, {"AAA": A, "BBB": B}, BE))
        assert r["risk_free"]["status"] == "ok" and r["risk_free"]["avg_annual"] == pytest.approx(0.04)
        assert r["analysis"]["risk_adjusted"]["sharpe"]["value"] == pytest.approx(r2["analysis"]["risk_adjusted"]["sharpe"]["value"])
        assert r["analysis"]["risk_adjusted"]["jensens_alpha"]["value"] == pytest.approx(r2["analysis"]["risk_adjusted"]["jensens_alpha"]["value"])


def test_engine_tbill_missing_or_gap_gives_unavailable():
    sp = vs(risk_free_source="tbill")
    for rates in (None, {date(2020, 1, 1): 0.04}):                    # ไม่มี / เก่าเกิน 7 วัน
        r = run_backtest(sp, {"AAA": A, "BBB": B}, BE, rates)
        assert r["risk_free"]["status"] in ("no_data", "unavailable")
        assert r["analysis"]["risk_adjusted"]["sharpe"]["status"] == "unavailable"


def test_user_constant_and_not_set_info():
    r = run_backtest(vs(risk_free_annual=0.03), {"AAA": A, "BBB": B}, BE)
    assert r["risk_free"] == {"source": "user_constant", "status": "ok", "avg_annual": 0.03}
    assert run_backtest(vs(), {"AAA": A, "BBB": B}, BE)["risk_free"]["status"] == "not_set"


def test_rate_change_affects_only_next_day_no_lookahead():
    """ขยับ yield ของวัน d แล้ว Sharpe/อัตรารายวันของวัน d เองต้องไม่เปลี่ยน (ใช้ yield ของ d-1)"""
    sp = vs(risk_free_source="tbill")
    base = flat_rates(0.04)
    r0 = run_backtest(sp, {"AAA": A, "BBB": B}, BE, base)
    last = date.fromisoformat(r0["period"]["last_date"])
    bumped = dict(base)
    bumped[last] = 0.5                                                  # yield วันสุดท้าย (ไม่มีผลกับวันใดในช่วง)
    r1 = run_backtest(sp, {"AAA": A, "BBB": B}, BE, bumped)
    assert r1["analysis"]["risk_adjusted"]["sharpe"]["value"] == r0["analysis"]["risk_adjusted"]["sharpe"]["value"]
    bumped2 = dict(base)
    mid = date.fromisoformat(r0["series"][60]["date"])                    # วันทำการ (วันหยุดไม่ถูกใช้เป็นวันอ้างอิง)
    bumped2[mid] = 0.5
    r2 = run_backtest(sp, {"AAA": A, "BBB": B}, BE, bumped2)
    assert r2["analysis"]["risk_adjusted"]["sharpe"]["value"] != r0["analysis"]["risk_adjusted"]["sharpe"]["value"]


# ------------------------------------------------------------------ attribution
def check_reconcile(r):
    a = r["attribution"]
    cap = r["stats"]["initial_capital"]
    assert abs(a["totals"]["reconciliation_error"]) < 1e-6
    assert sum(p["net_pnl"] for p in a["positions"]) == pytest.approx(r["stats"]["final_value"] - cap, abs=1e-6)
    assert a["totals"]["sum_contribution"] == pytest.approx(r["comparison"]["portfolio"]["total_return"]["value"], abs=1e-12)
    assert sum(p["commission"] for p in a["positions"]) == pytest.approx(r["stats"]["commission_paid"])
    assert sum(p["slippage_cost"] for p in a["positions"]) == pytest.approx(r["stats"]["slippage_cost"])
    assert a["totals"]["pct_risk_sum"] == pytest.approx(1.0, abs=1e-9)
    for p in a["positions"]:
        assert p["gross_pnl"] - p["commission"] - p["slippage_cost"] == pytest.approx(p["net_pnl"])


@pytest.mark.parametrize("reb", [{"mode": "none"}, {"mode": "calendar", "frequency": "monthly"},
                                 {"mode": "threshold", "threshold_pct": 2}])
def test_attribution_reconciles_fixed_weight_with_costs(reb):
    r = run_backtest(vs(costs=COSTS, rebalance=reb), {"AAA": A, "BBB": B}, BE)
    check_reconcile(r)


@pytest.mark.parametrize("reb", [{"mode": "none"}, {"mode": "calendar", "frequency": "monthly"}])
def test_attribution_reconciles_strategy_with_sleeves_stops_costs(reb):
    r = run_strategy(vs(costs=COSTS, rebalance=reb, strategy=STRAT), {"AAA": A, "BBB": B}, BE)
    assert r["stats"]["trade_count"] > 4
    check_reconcile(r)


def test_attribution_cash_remainder_has_no_pnl():
    r = run_backtest(vs([{"symbol": "AAA", "weight": 0.3}]), {"AAA": A}, BE)       # 70% เงินสด
    check_reconcile(r)
    assert r["attribution"]["positions"][0]["contribution"] == pytest.approx(r["comparison"]["portfolio"]["total_return"]["value"], abs=1e-12)


def test_attribution_unit_daily_contributions_sum_to_portfolio_return_exactly():
    random.seed(7)
    cal = [d["date"] for d in A[5:105]]
    closes = {"X": [100 * (1 + 0.01 * random.uniform(-1, 1)) for _ in cal], "Y": [20 * (1 + 0.02 * random.uniform(-1, 1)) for _ in cal]}
    acct = Account(10000.0, 10, 20)
    acct.buy_outlay("X", closes["X"][0], 4000, cal[0], "initial")
    acct.buy_outlay("Y", closes["Y"][0], 3000, cal[0], "initial")
    eq = []
    for k, d in enumerate(cal):
        if k == 20:
            acct.sell_qty("X", closes["X"][k], acct.shares["X"] * 0.5, d, "rebalance")
        if k == 40:
            acct.buy_outlay("Y", closes["Y"][k], 1500, d, "rebalance")
        if k == 60:
            acct.sell_qty("Y", closes["Y"][k], acct.shares["Y"], d, "exit")
        eq.append(acct.value({s: closes[s][k] for s in closes}))
    rp = [eq[0] / 10000.0 - 1] + [eq[i] / eq[i - 1] - 1 for i in range(1, len(eq))]
    out = ATT.build(["X", "Y"], acct.trades, cal, closes, 10000.0, eq, rp)
    c = out["_daily_contrib"]
    for k in range(len(cal)):
        assert c["X"][k] + c["Y"][k] == pytest.approx(rp[k], abs=1e-12)
    assert out["totals"]["reconciliation_error"] == pytest.approx(0.0, abs=1e-8)
    assert out["totals"]["pct_risk_sum"] == pytest.approx(1.0, abs=1e-9)


def test_attribution_risk_share_follows_volatility_not_weight():
    """หุ้นนิ่ง 50% + หุ้นผันผวนมาก 50% -> %risk ของตัวผันผวนต้องใกล้ 100%"""
    random.seed(3)
    cal = [d["date"] for d in A[:200]]
    calm = [100 * (1 + 0.0001 * k) for k in range(200)]
    wild = [100.0]
    for _ in range(199):
        wild.append(wild[-1] * (1 + random.gauss(0, 0.03)))
    acct = Account(10000.0, 0, 0)
    acct.buy_outlay("C", calm[0], 5000, cal[0], "initial")
    acct.buy_outlay("W", wild[0], 5000, cal[0], "initial")
    eq = [acct.value({"C": calm[k], "W": wild[k]}) for k in range(200)]
    rp = [eq[0] / 10000 - 1] + [eq[i] / eq[i - 1] - 1 for i in range(1, 200)]
    rows = {p["symbol"]: p for p in ATT.build(["C", "W"], acct.trades, cal, {"C": calm, "W": wild}, 10000.0, eq, rp)["positions"]}
    assert rows["W"]["pct_of_risk"] > 0.97 and rows["C"]["pct_of_risk"] < 0.03


def test_attribution_short_history_marks_risk_insufficient():
    r = run_backtest(validate_spec(spec(POS, "2024-01-02", "2024-02-09"), today=TODAY), {"AAA": A, "BBB": B}, BE)
    assert r["period"]["trading_days"] < ATT.MIN_OBS
    assert r["attribution"]["risk_status"] == "insufficient_data" and r["attribution"]["positions"][0]["pct_of_risk"] is None
    assert abs(r["attribution"]["totals"]["reconciliation_error"]) < 1e-6


# ------------------------------------------------------------------ exposure
def test_concentration_known_values():
    c = EXP.concentration({"A": 0.5, "B": 0.25, "C": 0.25})
    assert c["hhi"]["value"] == pytest.approx(0.375) and c["effective_n"]["value"] == pytest.approx(1 / 0.375)
    assert c["top1"]["value"] == pytest.approx(0.5) and c["top3"]["value"] == pytest.approx(1.0)
    eq = EXP.concentration({"A": 0.2, "B": 0.2, "C": 0.2, "D": 0.2, "E": 0.2})
    assert eq["effective_n"]["value"] == pytest.approx(5.0)
    assert EXP.concentration({"A": 0.0})["hhi"]["status"] == M.UNDEFINED


def test_risk_decomposition_two_asset_closed_form():
    random.seed(5)
    n = 300
    x = [random.gauss(0, 0.01) for _ in range(n)]
    y = [random.gauss(0, 0.02) for _ in range(n)]
    w = {"x": 0.6, "y": 0.4}
    out = EXP.risk_decomposition(w, {"x": x, "y": y})
    vx, vy, cxy = M._var(x) * 252, M._var(y) * 252, M._cov(x, y) * 252
    var = 0.36 * vx + 0.16 * vy + 2 * 0.24 * cxy
    assert out["portfolio_volatility"]["value"] == pytest.approx(math.sqrt(var))
    assert sum(c["pct_of_risk"] for c in out["contributions"]) == pytest.approx(1.0)
    assert out["correlation"]["matrix"][0][1] == pytest.approx(M._cov(x, y) / math.sqrt(M._var(x) * M._var(y)))
    assert out["diversification_ratio"]["value"] >= 1.0


def test_risk_decomposition_insufficient_and_incomplete():
    assert EXP.risk_decomposition({"x": 1.0}, {"x": [0.01] * 10})["portfolio_volatility"]["status"] == M.INSUFFICIENT
    r = [0.01 * ((i % 7) - 3) for i in range(100)]
    out = EXP.risk_decomposition({"x": 0.5, "y": 0.5}, {"x": r, "y": r[:50] + [None] + r[51:]})
    assert out["excluded"] and out["excluded"][0]["symbol"] == "y"


def test_result_contains_exposure_block():
    r = run_backtest(vs(), {"AAA": A, "BBB": B}, BE)
    e = r["exposure"]
    assert e["target"]["hhi"]["value"] == pytest.approx((0.5 ** 2 + 0.4 ** 2) / 0.9 ** 2)   # น้ำหนักหุ้นปรับให้รวม 1
    assert e["static_decomposition"]["contributions"] and "note" in e
    assert sum(c["pct_of_risk"] for c in e["static_decomposition"]["contributions"]) == pytest.approx(1.0)


# ------------------------------------------------------------------ service
class Prov:
    name = "fake"

    def __init__(self, bars):
        self.bars = bars

    def get_bars(self, sym, s, e):
        return self.bars[sym]


def mkstore(rate_store):
    return PriceStore(Prov({"AAA": A, "BBB": B, "^GSPC": BE}), MemoryBackend(), rate_store=rate_store)


def test_service_tbill_ok_and_failure_warnings():
    sp = {**vs(), "risk_free_source": "tbill"}
    ok = RateStore(FakeRates(mkdata("2023-01-01", "2024-12-31", 0.045)), MemoryBackend())
    res = build_result(sp, mkstore(ok))
    codes = {w["code"] for w in res["warnings"]}
    assert "risk_free_tbill" in codes and "risk_free_missing" not in codes
    assert res["analysis"]["risk_adjusted"]["sharpe"]["status"] != "unavailable"
    assert res["conventions"]["risk_free"].startswith("อัตรา T-bill")
    bad = RateStore(FakeRates(fail=True), MemoryBackend())
    res = build_result(sp, mkstore(bad))
    codes = {w["code"] for w in res["warnings"]}
    assert "risk_free_unavailable" in codes and res["analysis"]["risk_adjusted"]["sharpe"]["status"] == "unavailable"
    res = build_result(sp, mkstore(None))                                   # ไม่ได้ตั้ง rate_store
    assert "risk_free_unavailable" in {w["code"] for w in res["warnings"]}
    res = build_result(vs(), mkstore(ok))                                   # ไม่เลือก tbill -> ไม่ยิง rate store เลย
    assert "risk_free_missing" in {w["code"] for w in res["warnings"]}


def test_service_untouched_when_tbill_not_requested():
    ok = FakeRates(mkdata("2023-01-01", "2024-12-31"))
    build_result(vs(), mkstore(RateStore(ok, MemoryBackend())))
    assert ok.calls == []


# ------------------------------------------------------------------ baseline wording
def test_baseline_verdict_distinguishes_worse_than_random():
    from backtest_lab.robust.baseline import verdict_text
    assert verdict_text({"p_bonferroni": 0.01, "beats_fraction": 0.99}).startswith("แยกจากโชคได้")
    assert verdict_text({"p_bonferroni": 1.0, "beats_fraction": 0.03}).startswith("ต่ำกว่าการสุ่มที่ระดับ 5%")
    assert "ต่ำกว่าค่ากลาง" in verdict_text({"p_bonferroni": 0.9, "beats_fraction": 0.3})
    assert verdict_text({"p_bonferroni": 0.2, "beats_fraction": 0.8}).startswith("ยังแยกจากโชคไม่ได้")
