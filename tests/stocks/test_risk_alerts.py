import asyncio

from stocks import risk_alerts as RA
from stocks import risk_exposure as X


def _exp(holdings, cash):
    return X.exposure(holdings, cash, {})


def test_single_weight_breach():
    e = _exp({"AAA": {"qty": 10, "price": 100.0}, "BBB": {"qty": 10, "price": 10.0}}, 100.0)
    found, evaluated, _ = RA._find_conditions(e, None, {"max_single_weight": 0.5})
    assert ("single_weight", "AAA") in found and ("single_weight", "BBB") not in found
    assert "single_weight" in evaluated


def test_low_cash_and_hhi_breach():
    e = _exp({"AAA": {"qty": 1, "price": 100.0}}, 5.0)
    found, evaluated, _ = RA._find_conditions(e, None, {"min_cash_weight": 0.1, "max_hhi": 0.5})
    assert ("low_cash", "") in found and ("hhi", "") in found
    assert {"low_cash", "hhi"} <= evaluated


def test_drawdown_needs_enough_observations():
    e = _exp({"AAA": {"qty": 1, "price": 100.0}}, 0.0)
    few = {"tail": {"current_drawdown": {"value": -0.2, "status": "limited_sample", "n_obs": 2}}}
    found, evaluated, skipped = RA._find_conditions(e, few, {"max_drawdown": 0.1})
    assert ("drawdown", "") not in found and "drawdown" not in evaluated and skipped[0]["alert_type"] == "drawdown"
    enough = {"tail": {"current_drawdown": {"value": -0.2, "status": "limited_sample", "n_obs": 30}}}
    found, evaluated, _ = RA._find_conditions(e, enough, {"max_drawdown": 0.1})
    assert found[("drawdown", "")]["observed_value"] == 0.2 and "drawdown" in evaluated


def test_empty_portfolio_lets_position_alerts_resolve():
    e = _exp({}, 1000.0)
    found, evaluated, _ = RA._find_conditions(e, None, {"max_hhi": 0.5, "max_single_weight": 0.3})
    assert found == {} and {"hhi", "single_weight"} <= evaluated


def test_plan_opens_updates_and_resolves_only_evaluated_types():
    found = {("single_weight", "AAA"): {"alert_type": "single_weight", "symbol": "AAA"},
             ("hhi", ""): {"alert_type": "hhi", "symbol": None}}
    active = [{"id": 1, "alert_type": "single_weight", "symbol": "AAA"},
              {"id": 2, "alert_type": "single_weight", "symbol": "ZZZ"},
              {"id": 3, "alert_type": "drawdown", "symbol": None}]
    to_open, to_update, to_resolve = RA._plan(found, {"single_weight", "hhi"}, active)
    assert [c["alert_type"] for c in to_open] == ["hhi"]
    assert [r["id"] for r, _ in to_update] == [1]
    assert [r["id"] for r in to_resolve] == [2]          # drawdown not evaluated -> left alone


def test_same_tolerates_float_noise():
    assert RA._same(None, None) and RA._same(0.0742, 0.07420000000000001)
    assert not RA._same(0.1, None) and not RA._same(0.1, 0.2)


def test_evaluate_after_reset_resolves_everything(monkeypatch):
    calls = []

    async def fake_report(email, portfolio="paper"):
        return {"meta": {"data_status": "no_activity"}}

    async def fake_sb(method, table, params=None, json=None, prefer=None, **kw):
        calls.append((method, table, params, json))
        return [{"id": 7, "alert_type": "single_weight", "symbol": "AAA"}] if method == "GET" else None

    monkeypatch.setattr(RA, "_report", fake_report)
    monkeypatch.setattr(RA, "sb", fake_sb)
    out = asyncio.run(RA.evaluate(email="a@b.c"))
    assert out["evaluated"] is True and out["resolved"][0]["symbol"] == "AAA"
    patch = [c for c in calls if c[0] == "PATCH"][0]
    assert patch[2]["email"] == "eq.a@b.c" and patch[3]["status"] == "resolved"


def test_evaluate_does_nothing_when_data_not_ready(monkeypatch):
    async def fake_report(email, portfolio="paper"):
        return {"meta": {"data_status": "incomplete", "warnings": []}, "exposure_ctx": None}

    async def fake_sb(*a, **k):
        raise AssertionError("must not touch the database when data is not ready")

    monkeypatch.setattr(RA, "_report", fake_report)
    monkeypatch.setattr(RA, "sb", fake_sb)
    out = asyncio.run(RA.evaluate(email="a@b.c"))
    assert out["evaluated"] is False and out["reason"] == "data_not_ready"


def test_list_alerts_is_scoped_to_the_caller(monkeypatch):
    seen = {}

    async def fake_sb(method, table, params=None, **k):
        seen.update(params)
        return []

    monkeypatch.setattr(RA, "sb", fake_sb)
    asyncio.run(RA.list_alerts(status=None, limit=20, email="me@x.com"))
    assert seen["email"] == "eq.me@x.com"


# ---------------------------------------------------------------- กฎใหม่ (sector / daily_loss / vol / TE / stale)
def _exp_sec(holdings, cash, sectors):
    return X.exposure(holdings, cash, sectors)


def test_sector_breach_needs_classification_and_keys_by_sector():
    e = _exp_sec({"AAA": {"qty": 10, "price": 10.0}, "BBB": {"qty": 1, "price": 10.0}}, 0.0,
                 {"AAA": "Tech", "BBB": "Energy"})
    found, evaluated, skipped = RA._find_conditions(e, None, {"max_sector_weight": 0.5}, {"sector_fetched": True})
    assert ("sector_weight", "Tech") in found and ("sector_weight", "Energy") not in found
    assert found[("sector_weight", "Tech")]["symbol"] is None and "sector_weight" in evaluated and not skipped
    # ไม่ได้ดึง sector (sector = "n/a"): ห้ามประเมิน ห้ามปิด alert เก่า
    e2 = _exp_sec({"AAA": {"qty": 10, "price": 10.0}}, 0.0, {"AAA": "n/a"})
    found, evaluated, _ = RA._find_conditions(e2, None, {"max_sector_weight": 0.5}, {"sector_fetched": False})
    assert found == {} and "sector_weight" not in evaluated


def test_sector_unknown_holding_reports_breach_but_never_resolves():
    e = _exp_sec({"AAA": {"qty": 10, "price": 10.0}, "BBB": {"qty": 1, "price": 10.0}}, 0.0, {"AAA": "Tech"})
    found, evaluated, skipped = RA._find_conditions(e, None, {"max_sector_weight": 0.5}, {"sector_fetched": True})
    assert ("sector_weight", "Tech") in found and ("sector_weight", "Unknown") not in found
    assert "sector_weight" not in evaluated and skipped[0]["alert_type"] == "sector_weight"


def test_daily_loss_uses_latest_session_and_ignores_gains():
    e = _exp({}, 1000.0)
    ex = {"daily_return": {"date": "2026-10-27", "value": -0.05}}
    found, evaluated, _ = RA._find_conditions(e, None, {"max_daily_loss": 0.03}, ex)
    assert found[("daily_loss", "")]["observed_value"] == 0.05 and "daily_loss" in evaluated
    found, _, _ = RA._find_conditions(e, None, {"max_daily_loss": 0.03}, {"daily_return": {"date": "d", "value": 0.07}})
    assert found == {}
    _, evaluated, skipped = RA._find_conditions(e, None, {"max_daily_loss": 0.03}, {"daily_return": None})
    assert "daily_loss" not in evaluated and skipped[0]["reason"] == "daily_return_unavailable"


def test_last_daily_return():
    nav = [{"date": "a", "nav": 100.0}, {"date": "b", "nav": 97.0}]
    assert abs(RA._last_daily_return(nav)["value"] + 0.03) < 1e-12
    assert RA._last_daily_return(nav[:1]) is None and RA._last_daily_return(None) is None
    assert RA._last_daily_return([{"date": "a", "nav": 0.0}, {"date": "b", "nav": 1.0}]) is None


def test_volatility_and_tracking_error_need_enough_obs():
    e = _exp({}, 1000.0)
    perf = {"volatility": {"value": 0.4, "status": "limited_sample", "n_obs": 30},
            "tracking_error": {"value": 0.2, "status": "insufficient_data", "n_obs": 5, "reason": "need ≥20 observations"}}
    lim = {"max_volatility": 0.3, "max_tracking_error": 0.1}
    found, evaluated, skipped = RA._find_conditions(e, {"performance": perf}, lim)
    assert ("volatility", "") in found and "volatility" in evaluated
    assert "tracking_error" not in evaluated and skipped[0]["alert_type"] == "tracking_error"
    # n_obs ต่ำกว่าเกณฑ์แม้ status ok ก็ไม่ประเมิน
    perf["volatility"]["n_obs"] = 3
    found, evaluated, _ = RA._find_conditions(e, {"performance": perf}, {"max_volatility": 0.3})
    assert found == {} and "volatility" not in evaluated


def test_stale_data_always_on_when_health_known():
    e = _exp({}, 1000.0)
    ok = {"data": {"freshness": "fresh", "days_old": 1, "missing": []}}
    found, evaluated, _ = RA._find_conditions(e, None, {}, ok)
    assert found == {} and "stale_data" in evaluated
    stale = {"data": {"freshness": "stale", "days_old": 6, "missing": []}}
    found, _, _ = RA._find_conditions(e, None, {}, stale)
    assert found[("stale_data", "")]["severity"] == "warning"
    very = {"data": {"freshness": "stale", "days_old": 9, "missing": []}}
    assert RA._find_conditions(e, None, {}, very)[0][("stale_data", "")]["severity"] == "critical"
    miss = {"data": {"freshness": "fresh", "days_old": 0, "missing": [{"code": "position_unpriced", "symbol": "ZZZ"}]}}
    assert ("stale_data", "") in RA._find_conditions(e, None, {}, miss)[0]
    # ไม่รู้สุขภาพข้อมูล: ไม่ประเมิน ไม่ปิด
    assert "stale_data" not in RA._find_conditions(e, None, {}, None)[1]


def test_severity_levels():
    assert RA._severity("hhi", 0.45, 0.4) == "warning"
    assert RA._severity("hhi", 0.6, 0.4) == "critical"
    assert RA._severity("daily_loss", 0.04, 0.03) == "critical"
    assert RA._severity("daily_loss", 0.035, 0.03) == "warning"
    assert RA._severity("low_cash", 0.045, 0.05) == "warning"
    assert RA._severity("low_cash", 0.03, 0.05) == "critical"
    assert RA._severity("low_cash", -0.01, 0.0) == "critical"


def test_found_conditions_always_carry_severity_and_sector_key():
    e = _exp({"AAA": {"qty": 1, "price": 100.0}}, 5.0)
    found, _, _ = RA._find_conditions(e, None, {"min_cash_weight": 0.1, "max_hhi": 0.5})
    assert all(c["severity"] in RA.SEVERITIES and "sector" in c for c in found.values())


def test_plan_keys_sector_alerts_by_sector():
    found = {("sector_weight", "Tech"): {"alert_type": "sector_weight", "symbol": None, "sector": "Tech"}}
    active = [{"id": 1, "alert_type": "sector_weight", "symbol": None, "sector": "Tech"},
              {"id": 2, "alert_type": "sector_weight", "symbol": None, "sector": "Energy"}]
    to_open, to_update, to_resolve = RA._plan(found, {"sector_weight"}, active)
    assert to_open == [] and [r["id"] for r, _ in to_update] == [1] and [r["id"] for r in to_resolve] == [2]


def test_limits_defaults_only_when_no_row():
    assert RA._effective_limits({}) == RA.DEFAULT_LIMITS
    row = {"max_drawdown": 0.1, "max_hhi": None}
    eff = RA._effective_limits(row)
    assert eff["max_drawdown"] == 0.1 and eff["max_hhi"] is None and eff["max_sector_weight"] is None
    assert set(RA._limit_sources({}).values()) == {"default"}
    src = RA._limit_sources(row)
    assert src["max_drawdown"] == "custom" and src["max_hhi"] == "off"
    assert set(RA.DEFAULT_LIMITS) == set(RA.LIMIT_FIELDS)


# ---------------------------------------------------------------- เส้นทางเต็มของ endpoint
def _fake_sb(calls, limits_rows=(), active_rows=()):
    async def fake_sb(method, table, params=None, json=None, prefer=None, **kw):
        calls.append((method, table, params, json))
        if method == "GET" and table == "stock_risk_limits":
            return list(limits_rows)
        if method == "GET" and table == "stock_risk_alerts":
            return list(active_rows)
        if method == "POST" and table == "stock_risk_limits":
            return json
        return None
    return fake_sb


def test_evaluate_uses_default_limits_fetches_sector_and_writes_severity(monkeypatch):
    calls = []

    async def fake_report(email, portfolio="paper"):
        return {"meta": {"data_status": "ok", "as_of": "2026-10-27", "freshness": "fresh", "warnings": []},
                "exposure_ctx": {"holdings": {"AAA": {"qty": 10, "price": 10.0}}, "cash": 0.0, "skipped": []},
                "analysis": {"performance": {}},
                "nav_series": [{"date": "2026-10-26", "nav": 100.0}, {"date": "2026-10-27", "nav": 90.0}]}

    async def fake_sector(sym):
        return "Tech"

    monkeypatch.setattr(RA, "_report", fake_report)
    monkeypatch.setattr(RA, "sb", _fake_sb(calls))          # ไม่มีแถวลิมิต = ค่าเริ่มต้น
    monkeypatch.setattr(RA.rd, "sector", fake_sector)

    async def fake_earn(a, b):
        return []                                           # ไม่มีประกาศงบในช่วงนี้ (ไม่เรียก Finnhub จริง)

    monkeypatch.setattr(RA.rd, "earnings", fake_earn)
    out = asyncio.run(RA.evaluate(email="a@b.c"))
    posted = {c[3][0]["alert_type"]: c[3][0] for c in calls if c[0] == "POST"}
    assert {"single_weight", "hhi", "sector_weight", "daily_loss"} <= set(posted)
    assert posted["sector_weight"]["sector"] == "Tech" and posted["sector_weight"]["symbol"] is None
    assert posted["daily_loss"]["severity"] == "critical"      # -10% เทียบลิมิต 3%
    assert all(r["email"] == "a@b.c" and r["severity"] in RA.SEVERITIES for r in posted.values())
    assert {o["alert_type"] for o in out["opened"]} == set(posted)


def test_evaluate_skips_finnhub_when_sector_limit_is_off(monkeypatch):
    calls = []

    async def fake_report(email, portfolio="paper"):
        return {"meta": {"data_status": "ok", "as_of": "2026-10-27", "freshness": "fresh", "warnings": []},
                "exposure_ctx": {"holdings": {"AAA": {"qty": 10, "price": 10.0}}, "cash": 0.0, "skipped": []},
                "analysis": {"performance": {}}, "nav_series": []}

    async def boom(sym):
        raise AssertionError("must not call Finnhub when the sector limit is off")

    monkeypatch.setattr(RA, "_report", fake_report)
    monkeypatch.setattr(RA, "sb", _fake_sb(calls, limits_rows=[{"email": "a@b.c", "max_drawdown": 0.5}]))
    monkeypatch.setattr(RA.rd, "sector", boom)
    out = asyncio.run(RA.evaluate(email="a@b.c"))
    assert out["evaluated"] is True and not [c for c in calls if c[0] == "POST"]


def test_acknowledge_is_scoped_and_distinguishes_missing_from_closed(monkeypatch):
    calls = []
    monkeypatch.setattr(RA, "sb", _fake_sb(calls))
    try:
        asyncio.run(RA.acknowledge_alert(5, email="a@b.c"))
        raise AssertionError("expected 404")
    except RA.HTTPException as e:
        assert e.status_code == 404
    patch = [c for c in calls if c[0] == "PATCH"][0]
    assert patch[2]["email"] == "eq.a@b.c" and patch[2]["status"] == "eq.active" and "acknowledged_at" in patch[3]

    calls.clear()
    monkeypatch.setattr(RA, "sb", _fake_sb(calls, active_rows=[{"id": 5, "status": "resolved", "acknowledged_at": None}]))
    try:
        asyncio.run(RA.acknowledge_alert(5, email="a@b.c"))
        raise AssertionError("expected 409")
    except RA.HTTPException as e:
        assert e.status_code == 409


def test_put_limits_seeds_defaults_for_a_new_user_only(monkeypatch):
    from types import SimpleNamespace
    calls = []
    monkeypatch.setattr(RA, "sb", _fake_sb(calls))
    body = SimpleNamespace(model_fields_set={"max_drawdown"}, max_drawdown=0.15)
    out = asyncio.run(RA.put_limits(body, email="a@b.c"))
    row = [c for c in calls if c[0] == "POST" and c[1] == "stock_risk_limits"][0][3][0]
    assert row["max_drawdown"] == 0.15 and row["max_hhi"] == RA.DEFAULT_LIMITS["max_hhi"]
    assert out["changed"] == ["max_drawdown"] and "max_hhi" in out["seeded_defaults"]

    calls.clear()  # ผู้ใช้เดิม: แก้ข้อเดียว ไม่แตะข้ออื่น (null = ปิด ต้องคงไว้)
    monkeypatch.setattr(RA, "sb", _fake_sb(calls, limits_rows=[{"email": "a@b.c", "max_drawdown": 0.2}]))
    out = asyncio.run(RA.put_limits(body, email="a@b.c"))
    row = [c for c in calls if c[0] == "POST" and c[1] == "stock_risk_limits"][0][3][0]
    assert "max_hhi" not in row and out["seeded_defaults"] == []


# ---------------------------------------------------------------- กฎ earnings
import datetime as _dt

_TODAY = _dt.date(2026, 10, 29)


def _er(sym, d, **kw):
    return {"symbol": sym, "date": d, "hour": "amc", "epsActual": None, "epsEstimate": 1.5, "quarter": 3, "year": 2026, **kw}


def test_earnings_by_symbol_filters_held_window_and_already_reported():
    rows = [_er("MU", "2026-10-30"), _er("META", "2026-11-04"), _er("AMZN", "2026-10-29"),   # AMZN ไม่ได้ถือ
            _er("MU", "2026-12-20"),                                    # นอกช่วง
            _er("NVDA", "2026-10-28"),                                  # ผ่านไปแล้ว
            _er("AAPL", "2026-10-29", epsActual=1.9),                   # ประกาศแล้ว
            {"symbol": "TSLA", "date": "bad"}, {"symbol": None, "date": "2026-10-30"}]
    out = RA._earnings_by_symbol(rows, ["MU", "meta", "NVDA", "AAPL", "TSLA"], _TODAY, 7)
    assert set(out) == {"MU", "meta"} and out["MU"]["days"] == 1 and out["meta"]["days"] == 6   # key ตามชื่อที่ถือ
    near = RA._earnings_by_symbol([_er("MU", "2026-11-03"), _er("MU", "2026-10-31")], ["MU"], _TODAY, 7)
    assert near["MU"]["days"] == 2                                      # เลือกวันที่ใกล้สุด


def test_earnings_rule_severity_and_detail():
    e = _exp({}, 1000.0)
    ex = {"earnings": {"MU": {"date": "2026-10-30", "hour": "amc", "days": 1, "quarter": 3, "year": 2026, "epsEstimate": 1.5},
                       "META": {"date": "2026-11-04", "hour": "amc", "days": 6}}}
    found, evaluated, _ = RA._find_conditions(e, None, {"earnings_lookahead_days": 7}, ex)
    assert "earnings" in evaluated and found[("earnings", "MU")]["severity"] == "warning"
    assert found[("earnings", "META")]["severity"] == "info" and found[("earnings", "META")]["symbol"] == "META"
    assert found[("earnings", "MU")]["observed_value"] == 1.0 and found[("earnings", "MU")]["threshold"] == 7.0
    assert found[("earnings", "MU")]["detail"]["date"] == "2026-10-30"
    # ลิมิตแคบลง: META (6 วัน) หลุดช่วง
    found, _, _ = RA._find_conditions(e, None, {"earnings_lookahead_days": 3}, ex)
    assert set(found) == {("earnings", "MU")}


def test_earnings_rule_unavailable_off_and_not_fetched():
    e = _exp({}, 1000.0)
    found, evaluated, skipped = RA._find_conditions(e, None, {"earnings_lookahead_days": 7}, {"earnings": None})
    assert found == {} and "earnings" not in evaluated and skipped[0]["reason"] == "earnings_calendar_unavailable"
    assert "earnings" in RA._find_conditions(e, None, {}, {"earnings": None})[1]          # ปิดกฎ = ประเมิน (ปิด alert เก่า)
    assert "earnings" not in RA._find_conditions(e, None, {"earnings_lookahead_days": 7}, {})[1]   # ไม่ได้ดึง = ไม่ประเมิน
    assert "earnings" in RA._find_conditions(e, None, {"earnings_lookahead_days": 7}, {"earnings": {}})[1]


def test_fetch_earnings_handles_provider_failure_and_empty_holdings(monkeypatch):
    async def boom(a, b):
        raise RA.ProviderError("down")

    monkeypatch.setattr(RA.rd, "earnings", boom)
    assert asyncio.run(RA._fetch_earnings(["MU"], _TODAY, 7)) is None                    # ล้มเหลว = None ไม่ใช่ {}
    assert asyncio.run(RA._fetch_earnings([], _TODAY, 7)) == {}                          # ไม่ถืออะไรเลย ไม่เรียกปฏิทิน


def test_evaluate_opens_earnings_alert_for_held_symbol(monkeypatch):
    calls = []
    seen = {}

    async def fake_report(email, portfolio="paper"):
        return {"meta": {"data_status": "ok", "as_of": "2026-10-28", "freshness": "fresh", "warnings": []},
                "exposure_ctx": {"holdings": {"MU": {"qty": 1, "price": 100.0}}, "cash": 900.0, "skipped": []},
                "analysis": {"performance": {}}, "nav_series": []}

    async def fake_earn(a, b):
        seen["range"] = (a, b)
        return [_er("MU", (a + _dt.timedelta(days=2)).isoformat()), _er("ZZZ", a.isoformat())]

    monkeypatch.setattr(RA, "_report", fake_report)
    monkeypatch.setattr(RA, "sb", _fake_sb(calls, limits_rows=[{"email": "a@b.c", "earnings_lookahead_days": 5}]))
    monkeypatch.setattr(RA.rd, "earnings", fake_earn)
    asyncio.run(RA.evaluate(email="a@b.c"))
    posted = [c[3][0] for c in calls if c[0] == "POST"]
    assert [p["alert_type"] for p in posted] == ["earnings"] and posted[0]["symbol"] == "MU"
    assert posted[0]["severity"] == "info" and posted[0]["threshold"] == 5.0
    assert (seen["range"][1] - seen["range"][0]).days == 5                               # ช่วงเรียกตามลิมิต


def test_earnings_constants_are_registered():
    assert RA.DEFAULT_LIMITS["earnings_lookahead_days"] == 7 and "earnings_lookahead_days" in RA.LIMIT_FIELDS
    assert "earnings" in RA.ALERT_TYPES


# ---------------------------------------------------------------- ลิมิต/alert แยกตามพอร์ต (paper | real)
def _tables_used(calls):
    return {(c[0], c[1]) for c in calls}


def test_real_portfolio_uses_its_own_tables_and_report(monkeypatch):
    seen = {}

    async def fake_report(email, portfolio="paper"):
        seen["portfolio"] = portfolio
        return {"meta": {"data_status": "ok", "as_of": "2026-10-28", "freshness": "fresh", "warnings": []},
                "exposure_ctx": {"holdings": {"AAA": {"qty": 10, "price": 10.0}}, "cash": 0.0, "skipped": []},
                "analysis": {"performance": {}}, "nav_series": []}

    for pf, lim_t, al_t in (("real", "real_risk_limits", "real_risk_alerts"), ("paper", "stock_risk_limits", "stock_risk_alerts")):
        calls = []

        async def sb(method, table, params=None, json=None, prefer=None, **kw):
            calls.append((method, table))
            if method == "GET" and table == lim_t:
                return [{"email": "a@b.c", "max_hhi": 0.9}]       # หุ้นตัวเดียว HHI = 1.0 > 0.9
            return []

        monkeypatch.setattr(RA, "_report", fake_report)
        monkeypatch.setattr(RA, "sb", sb)
        out = asyncio.run(RA.evaluate(portfolio=pf, email="a@b.c"))
        assert seen["portfolio"] == pf and [o["alert_type"] for o in out["opened"]] == ["hhi"]
        used = _tables_used(calls)
        assert ("GET", lim_t) in used and ("POST", al_t) in used
        other = "stock_risk_alerts" if pf == "real" else "real_risk_alerts"
        assert not any(t in (other, "stock_risk_limits" if pf == "real" else "real_risk_limits") for _, t in used)


def test_limits_endpoints_and_audit_events_are_scoped_per_portfolio(monkeypatch):
    from types import SimpleNamespace
    for pf, lim_t, ev in (("real", "real_risk_limits", "real_risk_limit_changed"), ("paper", "stock_risk_limits", "risk_limit_changed")):
        calls = []

        async def sb(method, table, params=None, json=None, prefer=None, **kw):
            calls.append((method, table, json))
            if method == "POST" and table == lim_t:
                return json
            return []

        monkeypatch.setattr(RA, "sb", sb)
        body = SimpleNamespace(model_fields_set={"max_drawdown"}, max_drawdown=0.15)
        out = asyncio.run(RA.put_limits(body, portfolio=pf, email="a@b.c"))
        assert out["changed"] == ["max_drawdown"] and ("POST", lim_t) in {(c[0], c[1]) for c in calls}
        audit = [c for c in calls if c[1] == "audit_log"][0][2]
        assert {a["event"] for a in audit if a["param"] == "max_drawdown"} == {ev}
        got = asyncio.run(RA.get_limits(portfolio=pf, email="a@b.c"))
        assert got["source"]["max_drawdown"] == "default" and ("GET", lim_t) in {(c[0], c[1]) for c in calls}


def test_alert_list_and_acknowledge_are_scoped_per_portfolio(monkeypatch):
    calls = []

    async def sb(method, table, params=None, json=None, prefer=None, **kw):
        calls.append((method, table, params))
        return []

    monkeypatch.setattr(RA, "sb", sb)
    asyncio.run(RA.list_alerts(status="active", acknowledged=None, limit=10, portfolio="real", email="a@b.c"))
    assert calls[-1][1] == "real_risk_alerts" and calls[-1][2]["email"] == "eq.a@b.c"
    try:
        asyncio.run(RA.acknowledge_alert(3, portfolio="real", email="a@b.c"))
    except RA.HTTPException as e:
        assert e.status_code == 404
    assert {c[1] for c in calls} == {"real_risk_alerts"}
    asyncio.run(RA.list_alerts(status=None, acknowledged=None, limit=10, portfolio="paper", email="a@b.c"))
    assert calls[-1][1] == "stock_risk_alerts"


def test_overview_active_alert_count_reads_the_portfolios_own_table(monkeypatch):
    from stocks import risk_api as API
    seen = []

    async def sb(method, table, params=None, **kw):
        seen.append(table)
        return [{"id": 1, "severity": "critical", "acknowledged_at": None}]

    monkeypatch.setattr(API, "sb", sb)
    real = asyncio.run(API._active_alerts("a@b.c", "real"))
    paper = asyncio.run(API._active_alerts("a@b.c", "paper"))
    assert seen == ["real_risk_alerts", "stock_risk_alerts"]
    assert real["value"] == 1 and real["critical"] == 1 and paper["unacknowledged"] == 1
