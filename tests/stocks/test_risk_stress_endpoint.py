import asyncio
from types import SimpleNamespace

import pytest
from stocks import risk_api as A
from stocks import risk_engine as E


def _body(**kw):
    d = {"market_shock": None, "shocks": {}, "sector_shocks": {}}
    d.update(kw)
    return SimpleNamespace(**d)


def _patch(monkeypatch):
    ctx = {"holdings": {"AAA": {"qty": 10, "price": 100.0}, "BBB": {"qty": 5, "price": 100.0}}, "cash": 500.0,
           "returns": {}, "bench_returns": None, "as_of": "2026-10-27", "skipped": []}

    async def fake_ctx(email, portfolio="paper"):
        return {"meta": {"warnings": [], "data_status": "ok"}}, ctx

    async def fake_sectors(syms):
        return {"AAA": "Technology", "BBB": "Energy"}

    monkeypatch.setattr(A, "_ctx", fake_ctx)
    monkeypatch.setattr(A, "_sector_map", fake_sectors)
    monkeypatch.setattr(A.X, "holding_betas", lambda r, b: {"AAA": E.Metric(1.0, "ok", "", "", 100),
                                                            "BBB": E.Metric(1.0, "ok", "", "", 100)})


def test_sector_name_match_is_case_insensitive_and_reports_unknown_names(monkeypatch):
    _patch(monkeypatch)
    out = asyncio.run(A.stress_test(_body(sector_shocks={"technology": -0.3, "Utilities": -0.1}), email="a@b.c"))["stress"]
    assert out["pnl"] == pytest.approx(-300.0)                  # เฉพาะ Technology (1000 × -30%) BBB ไม่มี shock/beta ตลาด
    assert out["unknown_sectors"] == ["Utilities"]
    assert [r["sector"] for r in out["by_sector"]] == ["Technology"]
    assert out["skipped"][0]["symbol"] == "BBB"
    assert out["sector_classification"].startswith("Finnhub")


def test_requires_at_least_one_shock_and_validates_sector_values(monkeypatch):
    _patch(monkeypatch)
    for bad in (_body(), _body(sector_shocks={"Tech": 1.5}), _body(sector_shocks={"": -0.1}),
                _body(sector_shocks={"x" * 61: -0.1})):
        with pytest.raises(A.HTTPException) as e:
            asyncio.run(A.stress_test(bad, email="a@b.c"))
        assert e.value.status_code == 400


def test_attribution_endpoint_adds_sector_and_pnl(monkeypatch):
    attr = {"positions": [{"symbol": "AAA", "contribution": 0.03, "avg_weight_nav": 0.5, "days_held": 5, "held_now": True},
                          {"symbol": "BBB", "contribution": -0.01, "avg_weight_nav": 0.2, "days_held": 3, "held_now": False}],
            "sum_check": {"ok": True}}

    async def fake_report(email, portfolio="paper"):
        return {"meta": {"data_status": "ok"}, "attribution": attr, "pnl": {"total_net": 12.5}}

    async def fake_sectors(syms):
        assert sorted(syms) == ["AAA", "BBB"]                 # รวมตัวที่ขายแล้วด้วย
        return {"AAA": "Technology", "BBB": None}

    monkeypatch.setattr(A, "_report", fake_report)
    monkeypatch.setattr(A, "_sector_map", fake_sectors)
    out = asyncio.run(A.attribution_view(email="a@b.c"))
    assert out["pnl"] == {"total_net": 12.5} and out["attribution"] is attr
    assert [r["sector"] for r in out["by_sector"]] == ["Technology", "Unknown"]
    assert out["sector_classification"].startswith("Finnhub")
