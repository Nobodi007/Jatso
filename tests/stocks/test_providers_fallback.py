import asyncio
import datetime as dt

import pytest

from stocks import providers as P
from stocks.cache import ProviderError, RateLimited

D1, D2 = dt.date(2026, 10, 1), dt.date(2026, 10, 23)
YROW = [{"date": "2026-10-21", "open": 1.0, "high": 2.0, "low": 1.0, "close": 1.5, "src": "yahoo"}]


def _run(c):
    return asyncio.run(c)


def test_plan_restricted_falls_back_to_yahoo_and_is_remembered(monkeypatch):
    calls = {"fmp": 0, "yh": 0}

    async def fmp(sym, s, e):
        calls["fmp"] += 1
        raise P.PlanRestricted("not in plan")

    def yh(sym, s, e):
        calls["yh"] += 1
        return YROW

    monkeypatch.setattr(P, "daily_history_range", fmp)
    monkeypatch.setattr(P, "_yf_history_sync", yh)
    P._fmp_denied.clear()
    assert _run(P.daily_history_range_any("ZZZ", D1, D2))[0]["src"] == "yahoo"
    _run(P.daily_history_range_any("ZZZ", D1, D2))
    assert calls == {"fmp": 1, "yh": 2}          # FMP is not retried for a denied symbol
    P._fmp_denied.clear()


def test_rate_limited_fmp_also_falls_back(monkeypatch):
    async def fmp(sym, s, e):
        raise RateLimited("fmp")

    monkeypatch.setattr(P, "daily_history_range", fmp)
    monkeypatch.setattr(P, "_yf_history_sync", lambda sym, s, e: YROW)
    P._fmp_denied.clear()
    assert _run(P.daily_history_range_any("QQQ1", D1, D2))[0]["src"] == "yahoo"


def test_fmp_success_is_tagged_and_yahoo_not_called(monkeypatch):
    async def fmp(sym, s, e):
        return [{"date": "2026-10-21", "open": 1, "high": 2, "low": 1, "close": 1.5}]

    def yh(*a):
        raise AssertionError("yahoo must not be called")

    monkeypatch.setattr(P, "daily_history_range", fmp)
    monkeypatch.setattr(P, "_yf_history_sync", yh)
    P._fmp_denied.clear()
    assert _run(P.daily_history_range_any("NVDA", D1, D2))[0]["src"] == "fmp"


def test_splits_fall_back_and_yahoo_failure_is_an_error_not_empty(monkeypatch):
    async def fmp(sym):
        raise P.PlanRestricted("x")

    monkeypatch.setattr(P, "stock_splits", fmp)
    P._fmp_denied.clear()
    monkeypatch.setattr(P, "_yf_splits_sync", lambda sym: [{"date": "2024-06-10", "ratio": 10.0}])
    assert _run(P.stock_splits_any("NVDA"))[0]["ratio"] == 10.0

    def boom(sym):
        raise ProviderError("yahoo: empty history")

    monkeypatch.setattr(P, "_yf_splits_sync", boom)
    P._fmp_denied.clear()
    with pytest.raises(ProviderError):
        _run(P.stock_splits_any("MU"))            # failure must not look like "no splits"
    P._fmp_denied.clear()


def test_yahoo_symbol_mapping():
    assert P._yf_sym("BRK.B") == "BRK-B" and P._yf_sym("^GSPC") == "^GSPC"
