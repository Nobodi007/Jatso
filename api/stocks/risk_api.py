"""Stock Risk Center API — US equities only, read-only, never places trades."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from . import ledger as L
from . import risk_data as rd
from . import risk_engine as E
from .auth import current_email
from .cache import ProviderError, RateLimited

log = logging.getLogger("stocks.risk_api")
router = APIRouter(prefix="/api/stocks/risk", tags=["stock-risk"])
REPORT_TTL, STALE_AFTER_DAYS = 60, 4


def _one_year_before(d: date) -> date:
    try:
        return d.replace(year=d.year - 1)
    except ValueError:
        return d.replace(year=d.year - 1, day=28)


def _daily_rf(rf_map: dict[date, float] | None, dates: list[date], max_gap=7) -> list[float] | None:
    """r_f for day t uses the latest annual yield observed on or before t−1."""
    if not rf_map:
        return None
    keys, out, j = sorted(rf_map), [], -1
    for i in range(1, len(dates)):
        ref = dates[i - 1]
        while j + 1 < len(keys) and keys[j + 1] <= ref:
            j += 1
        if j < 0 or (ref - keys[j]).days > max_gap:
            return None
        out.append(E.daily_rate(rf_map[keys[j]]))
    return out


def _nav_json(points):
    return [{"date": p.date.isoformat(), "nav": p.nav, "cash": p.cash,
             "market_value": p.market_value, "stale_symbols": list(p.stale)} for p in points]


async def _build(email: str) -> dict:
    today = datetime.now(L.ET).date()
    f_start, f_end = rd.window(today)
    warnings: list[dict] = []
    meta = {
        "asset_class": "us_equities", "account_type": "paper_trading", "currency": "USD",
        "return_method": "daily time-weighted price return; split-adjusted; net of fees; excludes dividends",
        "benchmark": {"symbol": rd.BENCHMARK, "name": "S&P 500 Price Index", "return_method": "price return"},
        "providers": {"prices": "Financial Modeling Prep EOD", "risk_free": "FMP treasury-rates 3M"},
        "method_version": E.METHOD_VERSION, "computed_at": datetime.now(timezone.utc).isoformat()}

    def done(status: str, **body):
        return {"meta": {**meta, "data_status": status, "warnings": warnings}, **body}

    acc = await rd.account(email)
    if not acc:
        return done("no_account")
    try:
        trades = L.to_trades(await rd.active_trades(email))
    except L.LedgerError as e:
        warnings.append({"code": "ledger_invalid", "detail": str(e)})
        return done("ledger_integrity_error")
    if not trades:
        return done("no_activity")
    symbols = sorted({t.symbol for t in trades})
    if len(symbols) > rd.MAX_SYMBOLS:
        warnings.append({"code": "too_many_symbols", "detail": f">{rd.MAX_SYMBOLS} symbols exceeds provider quota"})
        return done("unavailable")

    async def safe(coro, code, sym=None):
        try:
            return await coro
        except RateLimited:
            raise
        except ProviderError:
            warnings.append({"code": code, "symbol": sym})
            return None

    res = await asyncio.gather(
        safe(rd.eod(rd.BENCHMARK, f_start, f_end), "benchmark_unavailable", rd.BENCHMARK),
        safe(rd.risk_free(f_start, f_end), "risk_free_unavailable"),
        *[safe(rd.eod(s, f_start, f_end), "prices_unavailable", s) for s in symbols],
        *[safe(rd.splits(s), "splits_unavailable", s) for s in symbols])
    bench_rows, rf_map, n = res[0], res[1], len(symbols)
    eod_rows, split_rows = dict(zip(symbols, res[2:2 + n])), dict(zip(symbols, res[2 + n:]))
    if any(v is None for v in split_rows.values()):
        warnings.append({"code": "split_adjustment_incomplete",
                         "detail": "values may be wrong if a split occurred for listed symbols"})

    closes = {s: {date.fromisoformat(r["date"]): r["close"] for r in rows} for s, rows in eod_rows.items() if rows}
    bars = {s: {date.fromisoformat(r["date"]): (r["low"], r["high"]) for r in rows} for s, rows in eod_rows.items() if rows}
    if bench_rows:
        cal_all = [date.fromisoformat(r["date"]) for r in bench_rows]
    else:
        cal_all = sorted(set().union(*[set(c) for c in closes.values()])) if closes else []
        warnings.append({"code": "calendar_from_holdings"})
    if not cal_all:
        return done("insufficient_data")

    adj = L.adjust_for_splits(trades, {s: v for s, v in split_rows.items() if v})
    last = cal_all[-1]
    base_c = [d for d in cal_all if d <= _one_year_before(last)]
    base = base_c[-1] if base_c else cal_all[0]
    incep = L.session_date(L.parse_ts(acc["inception_at"])) if acc.get("inception_at") else adj[0].session_date
    incep = min(incep, adj[0].session_date)
    if incep > base:
        prior = [d for d in cal_all if d < incep]
        base = prior[-1] if prior else cal_all[0]
        warnings.append({"code": "portfolio_younger_than_period", "inception_session": incep.isoformat()})
    calendar = [d for d in cal_all if base <= d <= last]
    if any(t.session_date > last for t in adj):
        warnings.append({"code": "trades_after_last_close", "detail": "not yet reflected in EOD NAV"})

    try:
        nav, issues = L.build_nav(adj, float(acc["initial_cash"]), calendar, closes)
    except L.LedgerError as e:
        warnings.append({"code": "ledger_invalid", "detail": str(e)})
        return done("ledger_integrity_error")
    warnings.extend(issues)

    for t in adj:                                            # price sanity vs daily range
        b = bars.get(t.symbol, {}).get(t.ts.astimezone(L.ET).date())
        if b and not (b[0] * 0.99 <= t.price <= b[1] * 1.01):
            warnings.append({"code": "trade_price_outside_daily_range", "trade_id": t.id, "symbol": t.symbol})
    ledger_cash = L.replay_cash(trades, float(acc["initial_cash"]))
    if abs(ledger_cash - float(acc["cash"])) > 0.01:
        warnings.append({"code": "cash_reconciliation_mismatch", "ledger": round(ledger_cash, 2),
                         "account": float(acc["cash"])})

    meta["as_of"] = last.isoformat()
    meta["freshness"] = "fresh" if (today - last).days <= STALE_AFTER_DAYS else "stale"
    meta["period"] = {"label": "1y", "start": calendar[0].isoformat(), "end": last.isoformat(),
                      "trading_days": len(calendar) - 1, "calendar_days": (last - calendar[0]).days}
    if any(pt.nav is None for pt in nav):
        return done("incomplete", nav_series=_nav_json(nav))
    if len(nav) < 2:
        return done("insufficient_data", nav_series=_nav_json(nav))

    dates = [pt.date for pt in nav]
    rp = [nav[i].nav / nav[i - 1].nav - 1 for i in range(1, len(nav))]
    rb = None
    if bench_rows:
        bmap = {date.fromisoformat(r["date"]): r["close"] for r in bench_rows}
        rb = [bmap[dates[i]] / bmap[dates[i - 1]] - 1 for i in range(1, len(dates))]
    rf = _daily_rf(rf_map, dates)
    if rf_map and rf is None:
        warnings.append({"code": "risk_free_gap", "detail": "gap > 7 days; Sharpe/Alpha unavailable"})
    analysis = E.analyze(rp, rb, rf, dates)
    return done("ok" if not warnings else "ok_with_warnings", analysis=analysis, nav_series=_nav_json(nav))


async def _report(email: str) -> dict:
    try:
        return await rd.memo(f"report:{email}", REPORT_TTL, lambda: _build(email), provider_call=False)
    except RateLimited:
        raise HTTPException(503, "Market data rate limit reached. Try again later.")
    except ProviderError:
        raise HTTPException(503, "Market data provider unavailable.")
    except HTTPException:
        raise
    except Exception:
        log.exception("stock risk report failed")
        raise HTTPException(500, "Risk report failed.")


PERIOD = Query("1y", pattern="^1y$")


@router.get("/overview")
async def overview(period: str = PERIOD, email: str = Depends(current_email)):
    rep = await _report(email)
    a = rep.get("analysis") or {}
    perf, ra, tail = a.get("performance", {}), a.get("risk_adjusted", {}), a.get("tail", {})
    nav = rep.get("nav_series") or []
    lastp = nav[-1] if nav else None
    return {"meta": rep["meta"], "cards": {
        "market_value": {"value": lastp["nav"] if lastp else None, "unit": "USD",
                         "basis": "EOD close + cash", "as_of": lastp["date"] if lastp else None},
        "portfolio_return": perf.get("portfolio_return"), "benchmark_return": perf.get("benchmark_return"),
        "active_return": perf.get("active_return"), "volatility": perf.get("volatility"),
        "max_drawdown": tail.get("max_drawdown"), "sharpe": ra.get("sharpe"),
        "active_alerts": {"value": None, "status": "unavailable", "reason": "alerts engine ships in Phase 4"}}}


@router.get("/performance")
async def performance(period: str = PERIOD, email: str = Depends(current_email)):
    rep = await _report(email)
    a = rep.get("analysis") or {}
    return {"meta": rep["meta"], "metrics": a.get("performance"), "series": a.get("series"),
            "monthly": a.get("monthly"), "rolling": a.get("rolling"),
            "extremes": (a.get("tail") or {}).get("extremes"), "nav_series": rep.get("nav_series")}


@router.get("/metrics")
async def metrics(period: str = PERIOD, email: str = Depends(current_email)):
    rep = await _report(email)
    a = rep.get("analysis") or {}
    tail = a.get("tail") or {}
    keep = ("max_drawdown", "current_drawdown", "drawdown_episode", "var_95", "es_95", "downside_deviation")
    return {"meta": rep["meta"], "risk_adjusted": a.get("risk_adjusted"),
            "tail": {k: tail.get(k) for k in keep}, "conventions": a.get("conventions")}
