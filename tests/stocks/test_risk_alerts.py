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

    async def fake_report(email):
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
    async def fake_report(email):
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
