"""Stock Risk Center API — US equities only, read-only, never places trades."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from . import ledger as L
from . import risk_data as rd
from . import risk_engine as E
from . import risk_attribution as A
from . import risk_exposure as X
from .auth import current_email
from .cache import ProviderError, RateLimited
from .db import sb
from .risk_ratelimit import make_limiter

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


def _ffill(series: dict[date, float], calendar: list[date], limit: int = 5) -> list[float | None]:
    prior = [d for d in series if d < calendar[0] and series[d] > 0]
    last_c, last_k = (series[max(prior)], -1) if prior else (None, None)
    out = []
    for k, d in enumerate(calendar):
        c = series.get(d)
        if c is not None and c > 0:
            last_c, last_k = c, k
        out.append(last_c if last_c is not None and k - last_k <= limit else None)
    return out


def _exposure_ctx(adj, last: date, calendar: list[date], closes: dict, cash: float) -> dict:
    held = {s: p for s, p in L.positions([t for t in adj if t.session_date <= last]).items() if p.qty > L.QTY_EPS}
    holdings, returns, skipped = {}, {}, []
    for s, p in held.items():
        px = _ffill(closes.get(s, {}), calendar)
        if px[-1] is None:
            skipped.append({"code": "position_unpriced", "symbol": s})
            continue
        holdings[s] = {"qty": p.qty, "price": px[-1], "avg_cost": p.avg_cost}
        returns[s] = [None if (px[i] is None or px[i - 1] is None) else px[i] / px[i - 1] - 1
                      for i in range(1, len(px))]
    return {"as_of": last.isoformat(), "cash": cash, "holdings": holdings, "returns": returns,
            "skipped": skipped, "bench_returns": None}
    
def _realized_summary(adj) -> dict | None:
    try:
        pos = L.positions(adj)
    except L.LedgerError:
        return None
    gross = sum(p.realized_pnl_gross for p in pos.values())
    fees = sum(p.fees for p in pos.values())
    return {
        "basis": "average cost, fees not capitalized; split-adjusted; net = gross - all fees paid to date",
        "realized_gross": round(gross, 2),
        "fees_paid": round(fees, 2),
        "realized_net_of_fees": round(gross - fees, 2),
        "symbols": [{"symbol": s, "realized_gross": round(p.realized_pnl_gross, 2),
                     "fees": round(p.fees, 2), "open_qty": p.qty}
                    for s, p in sorted(pos.items())],
    }

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

    state: dict = {}

    def done(status: str, **body):
        extra = {"exposure_ctx": state["ctx"]} if "ctx" in state else {}
        if "realized" in state:
            extra["realized"] = state["realized"]
        return {"meta": {**meta, "data_status": status, "warnings": warnings}, **extra, **body}

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
    yahoo = sorted(s for s, rows in {rd.BENCHMARK: bench_rows, **eod_rows}.items()
                   if rows and rows[0].get("src") == "yahoo")
    if yahoo:
        meta["providers"]["prices_fallback"] = {"source": "Yahoo Finance (unofficial)", "symbols": yahoo}
        warnings.append({"code": "unofficial_price_source", "symbols": yahoo})
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
    state["ctx"] = _exposure_ctx(adj, last, calendar, closes, nav[-1].cash)
    state["realized"] = _realized_summary(adj)

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
        state["ctx"]["bench_returns"] = rb
    rf = _daily_rf(rf_map, dates)
    if rf_map and rf is None:
        warnings.append({"code": "risk_free_gap", "detail": "gap > 7 days; Sharpe/Alpha unavailable"})
    analysis = E.analyze(rp, rb, rf, dates)
    attribution = None
    try:                                                     # Phase 3: must never break the report itself
        attribution = A.attribution(adj, calendar, {s: _ffill(closes.get(s, {}), calendar) for s in symbols}, nav)
        if not attribution["sum_check"]["ok"]:
            warnings.append({"code": "attribution_residual", "residual": attribution["sum_check"]["residual"]})
    except ValueError as e:                                  # LedgerError is a ValueError
        log.warning("attribution unavailable: %s", e)
        warnings.append({"code": "attribution_unavailable"})
    return done("ok" if not warnings else "ok_with_warnings", analysis=analysis, nav_series=_nav_json(nav),
                attribution=attribution)


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

# จำกัด 30 ครั้ง/นาที/ผู้ใช้ รวมทุก endpoint ในไฟล์นี้ (หน้า Risk Center เปิดทีเดียวยิงหลายตัว)
_heavy = make_limiter(current_email, 30, 60, "heavy")


async def _active_alerts(email: str) -> dict:
    """จำนวน alert ที่เปิดอยู่ ณ การประเมินล่าสุด (POST /alerts/evaluate) ไม่ใช่ตามราคาสด"""
    try:
        rows = await sb("GET", "stock_risk_alerts",
                        params={"email": f"eq.{email}", "status": "eq.active", "select": "id"}) or []
    except HTTPException:
        return {"value": None, "status": "unavailable", "reason": "alerts_unavailable"}
    return {"value": len(rows), "status": "ok", "unit": "count", "basis": "as of last alerts evaluation"}


@router.get("/overview")
async def overview(period: str = PERIOD, email: str = Depends(_heavy)):
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
        "active_alerts": await _active_alerts(email)}}


@router.get("/performance")
async def performance(period: str = PERIOD, email: str = Depends(_heavy)):
    rep = await _report(email)
    a = rep.get("analysis") or {}
    return {"meta": rep["meta"], "metrics": a.get("performance"), "series": a.get("series"),
            "monthly": a.get("monthly"), "rolling": a.get("rolling"),
            "extremes": (a.get("tail") or {}).get("extremes"), "nav_series": rep.get("nav_series")}


@router.get("/metrics")
async def metrics(period: str = PERIOD, email: str = Depends(_heavy)):
    rep = await _report(email)
    a = rep.get("analysis") or {}
    tail = a.get("tail") or {}
    keep = ("max_drawdown", "current_drawdown", "drawdown_episode", "longest_underwater_trading_days",
            "drawdown_series", "extremes", "var_95", "es_95", "downside_deviation")
    return {"meta": rep["meta"], "risk_adjusted": a.get("risk_adjusted"),
            "tail": {k: tail.get(k) for k in keep}, "conventions": a.get("conventions")}

@router.get("/realized")
async def realized(period: str = PERIOD, email: str = Depends(_heavy)):
    rep = await _report(email)
    data = rep.get("realized")
    if data is None:
        return {"meta": rep["meta"], "realized": None, "status": "unavailable",
                "reason": f"data_status={rep['meta'].get('data_status')}"}
    return {"meta": rep["meta"], "realized": data}

def compute_drawdown(points, min_points: int = 5) -> dict:
    """points: [(YYYY-MM-DD, nav)] เรียงเก่า -> ใหม่ ไม่ดึงข้อมูลเพิ่ม ใช้ NAV ที่มีอยู่แล้ว"""
    clean = [(str(d)[:10], float(v)) for d, v in points if v is not None and float(v) > 0]
    if len(clean) < min_points:
        return {"status": "insufficient_data", "points": len(clean), "minPoints": min_points}

    day = date.fromisoformat
    peak, peak_date = clean[0][1], clean[0][0]
    max_dd, max_dd_date, max_dd_peak_date = 0.0, clean[0][0], clean[0][0]
    series, episodes = [], []  # episodes: [peak_date, end_date, recovered]
    ep = None

    for d, v in clean:
        if v >= peak:
            if ep:
                ep[1], ep[2] = d, True
                episodes.append(ep)
                ep = None
            peak, peak_date = v, d
        elif ep is None:
            ep = [peak_date, d, False]
        dd = v / peak - 1
        series.append({"date": d, "drawdownPercent": round(dd * 100, 4)})
        if dd < max_dd:
            max_dd, max_dd_date, max_dd_peak_date = dd, d, peak_date

    if ep:
        ep[1] = clean[-1][0]
        episodes.append(ep)

    days = lambda e: (day(e[1]) - day(e[0])).days
    worst = next((e for e in episodes if e[0] == max_dd_peak_date and max_dd < 0), None)
    current = episodes[-1] if episodes and not episodes[-1][2] else None

    return {
        "status": "ok",
        "points": len(clean),
        "series": series,
        "currentDrawdownPercent": series[-1]["drawdownPercent"],
        "maxDrawdownPercent": round(max_dd * 100, 4),
        "maxDrawdownPeakDate": max_dd_peak_date if max_dd < 0 else None,
        "maxDrawdownTroughDate": max_dd_date if max_dd < 0 else None,
        "maxDrawdownRecoveryDate": worst[1] if worst and worst[2] else None,
        "currentUnderwaterDays": days(current) if current else 0,
        "longestUnderwaterDays": max((days(e) for e in episodes), default=0),
    }

@router.get("/drawdown")
async def drawdown(period: str = PERIOD, email: str = Depends(_heavy)):
    rep = await _report(email)
    status = rep["meta"].get("data_status")
    nav = rep.get("nav_series") or []
    if status not in ("ok", "ok_with_warnings") or not nav:
        return {"meta": rep["meta"], "drawdown": None, "status": "unavailable",
                "reason": f"data_status={status}"}
    tail = (rep.get("analysis") or {}).get("tail") or {}
    return {"meta": rep["meta"],
            "drawdown": compute_drawdown([(p["date"], p["nav"]) for p in nav]),
            "engine": {k: tail.get(k) for k in ("max_drawdown", "current_drawdown", "drawdown_episode")}}


# ---------------- Phase 2: exposure / risk decomposition / stress ----------------
async def _ctx(email: str):
    rep = await _report(email)
    ctx = rep.get("exposure_ctx")
    if not ctx or not ctx["holdings"]:
        return rep, None
    return rep, ctx


def _no_ctx(rep: dict, key: str) -> dict:
    st = rep["meta"].get("data_status")
    return {"meta": rep["meta"], key: None,
            "status": "unavailable", "reason": f"no priced positions (data_status={st})"}


def _meta_with(rep: dict, ctx: dict, extra: list[dict] | None = None, **more) -> dict:
    w = list(rep["meta"]["warnings"]) + list(ctx["skipped"]) + list(extra or [])
    return {**rep["meta"], "as_of": ctx["as_of"], "warnings": w, **more}


@router.get("/exposure")
async def exposure(period: str = PERIOD, email: str = Depends(_heavy)):
    rep, ctx = await _ctx(email)
    if ctx is None:
        return _no_ctx(rep, "exposure")
    syms = list(ctx["holdings"])

    async def sec(s):
        try:
            return await rd.sector(s)
        except ProviderError:
            return None

    got = await asyncio.gather(*[sec(s) for s in syms])
    sectors = dict(zip(syms, got))
    missing = [{"code": "sector_unavailable", "symbol": s} for s, v in sectors.items() if not v]
    return {"meta": _meta_with(rep, ctx, missing,
                               sector_classification="Finnhub industry (not GICS); approximate"),
            "exposure": X.exposure(ctx["holdings"], ctx["cash"], sectors)}


@router.get("/risk-decomposition")
async def risk_decomposition(period: str = PERIOD, email: str = Depends(_heavy)):
    rep, ctx = await _ctx(email)
    if ctx is None:
        return _no_ctx(rep, "decomposition")
    w, _, _ = X.nav_weights(ctx["holdings"], ctx["cash"])
    return {"meta": _meta_with(rep, ctx),
            "decomposition": X.risk_decomposition(w, ctx["returns"])}


@router.get("/attribution")
async def attribution_view(period: str = PERIOD, email: str = Depends(_heavy)):
    rep = await _report(email)
    attr = rep.get("attribution")
    if attr is None:
        st = rep["meta"].get("data_status")
        return {"meta": rep["meta"], "attribution": None, "status": "unavailable",
                "reason": f"attribution not computed (data_status={st})"}
    return {"meta": rep["meta"], "attribution": attr}


_SYM = re.compile(r"^[A-Za-z0-9.\-]{1,12}$")


class StressIn(BaseModel):
    market_shock: float | None = Field(default=None, ge=-1.0, le=1.0)
    shocks: dict[str, float] = Field(default_factory=dict)


@router.post("/stress-test")
async def stress_test(body: StressIn, email: str = Depends(_heavy)):
    shocks = {k.strip().upper(): v for k, v in body.shocks.items()}
    if body.market_shock is None and not shocks:
        raise HTTPException(400, "Provide market_shock and/or shocks.")
    if len(shocks) > rd.MAX_SYMBOLS or any(not _SYM.match(k) or not -1.0 <= v <= 1.0 for k, v in shocks.items()):
        raise HTTPException(400, "Invalid shocks (symbols A-Z0-9.-, values within -1..1).")
    rep, ctx = await _ctx(email)
    if ctx is None:
        return _no_ctx(rep, "stress")
    betas = X.holding_betas(ctx["returns"], ctx["bench_returns"])
    out = X.stress(ctx["holdings"], ctx["cash"], betas, body.market_shock, shocks)
    out["unknown_symbols"] = sorted(set(shocks) - set(ctx["holdings"]))
    out["betas"] = {s: m.to_dict() for s, m in betas.items()}
    return {"meta": _meta_with(rep, ctx), "stress": out}
