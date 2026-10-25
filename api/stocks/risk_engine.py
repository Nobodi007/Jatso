"""
Jatso US Stock Risk Engine — pure functions, no I/O, no crypto imports.
Inputs: date-aligned daily simple returns (decimal). Sample statistics use ddof=1.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date
from typing import Sequence

METHOD_VERSION = "stock-risk/1.0.0"
TRADING_DAYS = 252
SQRT_T = math.sqrt(TRADING_DAYS)
EPS = 1e-15
EPS_RESID = 1e-12

OK, LIMITED, INSUFFICIENT, UNDEFINED, UNAVAILABLE = (
    "ok", "limited_sample", "insufficient_data", "undefined", "unavailable")
MIN_OBS_VOL, MIN_OBS_RATIO, MIN_OBS_FULL = 20, 60, 250
ANN = "ratio (annualized ×√252)"


@dataclass(frozen=True)
class Metric:
    value: float | None
    status: str
    unit: str
    formula: str
    n_obs: int = 0
    reason: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _ok(v, unit, f, n, limited_below=None) -> Metric:
    st = LIMITED if limited_below and n < limited_below else OK
    return Metric(float(v), st, unit, f, n)

def _na(status, unit, f, n, reason) -> Metric:
    return Metric(None, status, unit, f, n, reason)

def _insufficient(unit, f, n, need) -> Metric:
    return _na(INSUFFICIENT, unit, f, n, f"need ≥{need} observations")

def _validate(*series: Sequence[float]) -> int:
    n = len(series[0])
    for s in series:
        if len(s) != n:
            raise ValueError("series are not date-aligned (length mismatch)")
        for v in s:
            if v is None or not math.isfinite(v):
                raise ValueError("non-finite value in return series")
    return n

def _mean(x): return math.fsum(x) / len(x)
def _cov(x, y):
    mx, my = _mean(x), _mean(y)
    return math.fsum((a - mx) * (b - my) for a, b in zip(x, y)) / (len(x) - 1)
def _var(x): return _cov(x, x)
def _sd(x): return math.sqrt(max(_var(x), 0.0))

def daily_rate(annual: float) -> float:
    return (1.0 + annual) ** (1.0 / TRADING_DAYS) - 1.0

# ---------- returns ----------
def cumulative_return(r: Sequence[float]) -> float:
    w = 1.0
    for v in r:
        w *= 1.0 + v
    return w - 1.0

def relative_wealth(Rp: float, Rb: float) -> float:
    return (1.0 + Rp) / (1.0 + Rb) - 1.0

def total_return(r) -> Metric:
    n = _validate(r)
    f = "∏(1+r_t) − 1"
    return _ok(cumulative_return(r), "decimal", f, n) if n else _insufficient("decimal", f, 0, 1)

def cagr(R: float, calendar_days: int, min_days: int = 365) -> Metric:
    f = "(1+R)^(365.25/D) − 1"
    if calendar_days < min_days:
        return _na(UNDEFINED, "decimal/yr", f, calendar_days, "period < 1 year: not annualized")
    if 1.0 + R <= 0:
        return _na(UNDEFINED, "decimal/yr", f, calendar_days, "terminal wealth ≤ 0")
    return _ok((1.0 + R) ** (365.25 / calendar_days) - 1.0, "decimal/yr", f, calendar_days)

# ---------- risk ----------
def annualized_volatility(r, min_obs=MIN_OBS_VOL) -> Metric:
    f, n = "SD(r_t)·√252", _validate(r)
    if n < max(min_obs, 2):
        return _insufficient("decimal/yr", f, n, min_obs)
    return _ok(_sd(r) * SQRT_T, "decimal/yr", f, n, MIN_OBS_FULL)

def tracking_error(rp, rb, min_obs=MIN_OBS_VOL) -> Metric:
    f, n = "SD(r_p − r_b)·√252", _validate(rp, rb)
    if n < max(min_obs, 2):
        return _insufficient("decimal/yr", f, n, min_obs)
    return _ok(_sd([a - b for a, b in zip(rp, rb)]) * SQRT_T, "decimal/yr", f, n, MIN_OBS_FULL)

def _ann_ratio(x, f, min_obs) -> Metric:
    n = len(x)
    if n < max(min_obs, 2):
        return _insufficient(ANN, f, n, min_obs)
    sd = _sd(x)
    if sd < EPS:
        return _na(UNDEFINED, ANN, f, n, "zero dispersion")
    return _ok(_mean(x) / sd * SQRT_T, ANN, f, n, MIN_OBS_FULL)

def sharpe_ratio(rp, rf, min_obs=MIN_OBS_RATIO) -> Metric:
    f = "mean(r_p − r_f)/SD(r_p − r_f)·√252"
    if rf is None:
        return _na(UNAVAILABLE, ANN, f, len(rp), "risk-free series unavailable")
    _validate(rp, rf)
    return _ann_ratio([a - b for a, b in zip(rp, rf)], f, min_obs)

def information_ratio(rp, rb, min_obs=MIN_OBS_RATIO) -> Metric:
    _validate(rp, rb)
    return _ann_ratio([a - b for a, b in zip(rp, rb)], "mean(r_p − r_b)/SD(r_p − r_b)·√252", min_obs)

def downside_deviation_daily(r, mar_daily=0.0) -> float:
    return math.sqrt(math.fsum(min(v - mar_daily, 0.0) ** 2 for v in r) / len(r))

def downside_deviation(r, mar_annual=0.0, min_obs=MIN_OBS_RATIO) -> Metric:
    f, n = "√(Σ min(r_t − MAR_d, 0)² / N)·√252", _validate(r)
    if n < min_obs:
        return _insufficient("decimal/yr", f, n, min_obs)
    return _ok(downside_deviation_daily(r, daily_rate(mar_annual)) * SQRT_T, "decimal/yr", f, n, MIN_OBS_FULL)

def sortino_ratio(rp, mar_annual=0.0, min_obs=MIN_OBS_RATIO) -> Metric:
    f = "mean(r_p − MAR_d)/DD_d·√252; DD_d = √(Σ min(r − MAR_d,0)²/N); MAR_d=(1+MAR)^(1/252)−1"
    n = _validate(rp)
    if n < min_obs:
        return _insufficient(ANN, f, n, min_obs)
    mar = daily_rate(mar_annual)
    dd = downside_deviation_daily(rp, mar)
    if dd < EPS:
        return _na(UNDEFINED, ANN, f, n, "no returns below MAR")
    return _ok(_mean([v - mar for v in rp]) / dd * SQRT_T, ANN, f, n, MIN_OBS_FULL)

def beta_r2(rp, rb, min_obs=MIN_OBS_RATIO) -> dict[str, Metric]:
    fb, fr, fc = "Cov(r_p,r_b)/Var(r_b)", "Corr(r_p,r_b)²", "Cov/(σ_p σ_b)"
    n = _validate(rp, rb)
    if n < max(min_obs, 3):
        return {"beta": _insufficient("ratio", fb, n, min_obs), "r_squared": _insufficient("ratio", fr, n, min_obs),
                "correlation": _insufficient("ratio", fc, n, min_obs)}
    vb, vp, c = _var(rb), _var(rp), _cov(rp, rb)
    out = {"beta": _na(UNDEFINED, "ratio", fb, n, "benchmark variance is zero") if vb < EPS
           else _ok(c / vb, "ratio", fb, n, MIN_OBS_FULL)}
    if vb < EPS or vp < EPS:
        reason = "zero variance"
        out["r_squared"] = _na(UNDEFINED, "ratio", fr, n, reason)
        out["correlation"] = _na(UNDEFINED, "ratio", fc, n, reason)
    else:
        rho = c / math.sqrt(vp * vb)
        out["correlation"] = _ok(rho, "ratio", fc, n, MIN_OBS_FULL)
        out["r_squared"] = _ok(rho * rho, "ratio", fr, n, MIN_OBS_FULL)
    return out
MIN_OBS_DOWN, LIMITED_DOWN = 20, 60

def downside_beta(rp, rb, min_obs=MIN_OBS_DOWN) -> Metric:
    f = "Cov(r_p,r_b | r_b<0)/Var(r_b | r_b<0)"
    _validate(rp, rb)
    sel = [(a, b) for a, b in zip(rp, rb) if b < 0]
    n = len(sel)
    if n < max(min_obs, 3):
        return _insufficient("ratio", f, n, min_obs)
    xp, xb = [a for a, _ in sel], [b for _, b in sel]
    vb = _var(xb)
    if vb < EPS:
        return _na(UNDEFINED, "ratio", f, n, "benchmark variance on down days is zero")
    return _ok(_cov(xp, xb) / vb, "ratio", f, n, LIMITED_DOWN)

CAPM_KEYS = ("jensens_alpha", "alpha_t_stat", "beta_capm", "treynor", "appraisal_ratio")

def capm_regression(rp, rb, rf, min_obs=MIN_OBS_RATIO) -> dict[str, Metric]:
    """OLS: (r_p − r_f) = α + β(r_b − r_f) + ε. α annualized arithmetically (α_d·252)."""
    f = "OLS (r_p−r_f)=α+β(r_b−r_f)+ε"
    if rb is None or rf is None:
        why = "benchmark unavailable" if rb is None else "risk-free series unavailable"
        return {k: _na(UNAVAILABLE, "", f, len(rp), why) for k in CAPM_KEYS}
    n = _validate(rp, rb, rf)
    if n < max(min_obs, 3):
        return {k: _insufficient("", f, n, min_obs) for k in CAPM_KEYS}
    y = [p - r for p, r in zip(rp, rf)]
    x = [b - r for b, r in zip(rb, rf)]
    mx, my = _mean(x), _mean(y)
    sxx = math.fsum((v - mx) ** 2 for v in x)
    if sxx < EPS:
        return {k: _na(UNDEFINED, "", f, n, "benchmark excess variance is zero") for k in CAPM_KEYS}
    beta = math.fsum((a - mx) * (b - my) for a, b in zip(x, y)) / sxx
    alpha = my - beta * mx
    s_e = math.sqrt(math.fsum((yi - alpha - beta * xi) ** 2 for xi, yi in zip(x, y)) / (n - 2))
    out = {"beta_capm": _ok(beta, "ratio", f, n, MIN_OBS_FULL),
           "jensens_alpha": _ok(alpha * TRADING_DAYS, "decimal/yr", "α_d·252 from " + f, n, MIN_OBS_FULL)}
    if s_e < EPS_RESID:
        out["alpha_t_stat"] = _na(UNDEFINED, "t", "α_d/SE(α_d)", n, "zero residual variance")
        out["appraisal_ratio"] = _na(UNDEFINED, ANN, "α_d/σ_ε·√252", n, "zero residual variance")
    else:
        se_a = s_e * math.sqrt(1.0 / n + mx * mx / sxx)
        out["alpha_t_stat"] = _ok(alpha / se_a, "t", "α_d/SE(α_d)", n)
        out["appraisal_ratio"] = _ok(alpha / s_e * SQRT_T, ANN, "α_d/σ_ε·√252", n, MIN_OBS_FULL)
    ft = "mean(r_p − r_f)·252 / β_capm"
    out["treynor"] = (_na(UNDEFINED, "decimal/yr per β", ft, n, "beta ≈ 0") if abs(beta) < 1e-6
                      else _ok(my * TRADING_DAYS / beta, "decimal/yr per β", ft, n, MIN_OBS_FULL))
    return out

def hit_rate(rp, rb, min_obs=MIN_OBS_VOL) -> Metric:
    f, n = "#(r_p > r_b)/N", _validate(rp, rb)
    if n < min_obs:
        return _insufficient("share", f, n, min_obs)
    return _ok(sum(1 for a, b in zip(rp, rb) if a > b) / n, "share", f, n)

def _geo_mean(x):
    w = 1.0
    for v in x:
        w *= 1.0 + v
    return None if w <= 0 else w ** (1.0 / len(x)) - 1.0

def capture_ratio(rp, rb, up=True, min_obs=10) -> Metric:
    f = f"GeoMean(r_p | r_b{'>' if up else '<'}0)/GeoMean(r_b | same days)"
    _validate(rp, rb)
    sel = [(a, b) for a, b in zip(rp, rb) if (b > 0 if up else b < 0)]
    if len(sel) < min_obs:
        return _insufficient("ratio", f, len(sel), min_obs)
    gp, gb = _geo_mean([a for a, _ in sel]), _geo_mean([b for _, b in sel])
    if gp is None or gb is None or abs(gb) < EPS:
        return _na(UNDEFINED, "ratio", f, len(sel), "degenerate benchmark mean")
    return _ok(gp / gb, "ratio", f, len(sel))

# ---------- drawdown & tail ----------
def drawdown(rp, dates: Sequence[date]) -> dict:
    """dates[0] = base date (wealth 1.0); dates[i+1] ↔ rp[i]."""
    n = _validate(rp)
    if len(dates) != n + 1:
        raise ValueError("dates must be len(returns)+1")
    wealth = [1.0]
    for v in rp:
        wealth.append(wealth[-1] * (1.0 + v))
    peak, peak_i, mdd, mdd_peak, mdd_trough = wealth[0], 0, 0.0, 0, 0
    series, longest, start = [], 0, None
    for i, w in enumerate(wealth):
        if w >= peak:
            peak, peak_i = w, i
        dd = w / peak - 1.0
        series.append({"date": dates[i], "drawdown": dd})
        if dd < mdd:
            mdd, mdd_peak, mdd_trough = dd, peak_i, i
        if dd < 0:
            start = peak_i if start is None else start
            longest = max(longest, i - start)
        else:
            start = None
    recovery = None
    if mdd < 0:
        recovery = next((j for j in range(mdd_trough + 1, len(wealth))
                         if wealth[j] >= wealth[mdd_peak] * (1 - 1e-12)), None)
    f = "DD_t = W_t / max_{s≤t} W_s − 1"
    lim = MIN_OBS_FULL if n < TRADING_DAYS else None
    return {
        "max_drawdown": _ok(mdd, "decimal", "min_t DD_t", n, lim),
        "current_drawdown": _ok(series[-1]["drawdown"], "decimal", f, n),
        "episode": None if mdd >= 0 else {
            "peak_date": dates[mdd_peak], "trough_date": dates[mdd_trough],
            "recovery_date": dates[recovery] if recovery is not None else None,
            "duration_trading_days": (recovery if recovery is not None else n) - mdd_peak,
            "recovery_trading_days": None if recovery is None else recovery - mdd_trough},
        "longest_underwater_trading_days": longest,
        "series": series,
    }

def historical_var_es(r, alpha=0.05, min_obs=MIN_OBS_RATIO, full_obs=MIN_OBS_FULL) -> dict[str, Metric]:
    """Empirical lower quantile (inverted CDF, Hyndman–Fan type 1). ES = −mean(r | r ≤ Q)."""
    fv, fe = f"−Q_{alpha}(r), type-1 quantile", f"−E[r | r ≤ Q_{alpha}]"
    n = _validate(r)
    if n < min_obs:
        return {"var": _insufficient("decimal (1-day)", fv, n, min_obs),
                "es": _insufficient("decimal (1-day)", fe, n, min_obs)}
    s = sorted(r)
    q = s[max(1, math.ceil(alpha * n - 1e-9)) - 1]
    tail = [v for v in r if v <= q]
    return {"var": _ok(-q, "decimal (1-day)", fv, n, full_obs),
            "es": _ok(-_mean(tail), "decimal (1-day)", fe, n, full_obs)}

def calmar(cagr_m: Metric, mdd: float | None, n: int) -> Metric:
    f = "CAGR / |MDD|"
    if cagr_m.value is None:
        return _na(cagr_m.status, "ratio", f, n, f"CAGR: {cagr_m.reason}")
    if mdd is None or mdd > -EPS:
        return _na(UNDEFINED, "ratio", f, n, "no drawdown in period")
    return _ok(cagr_m.value / abs(mdd), "ratio", f, n)

# ---------- periodic & rolling ----------
def period_returns(rp, dates_r: Sequence[date], freq: str) -> list[dict]:
    """Compound daily returns per calendar month ('M') or ISO week ('W'). dates_r aligned to rp."""
    buckets: dict[str, list[float]] = {}
    for v, d in zip(rp, dates_r):
        if freq == "M":
            k = f"{d.year}-{d.month:02d}"
        else:
            iy, iw, _ = d.isocalendar()
            k = f"{iy}-W{iw:02d}"
        buckets.setdefault(k, []).append(v)
    return [{"period": k, "return": cumulative_return(v), "days": len(v)} for k, v in buckets.items()]

def _extremes(rp, dates_r) -> dict:
    lo = min(range(len(rp)), key=rp.__getitem__)
    hi = max(range(len(rp)), key=rp.__getitem__)
    out = {"worst_day": {"date": dates_r[lo], "return": rp[lo]},
           "best_day": {"date": dates_r[hi], "return": rp[hi]}}
    for freq, name in (("W", "week"), ("M", "month")):
        b = period_returns(rp, dates_r, freq)
        out[f"worst_{name}"] = min(b, key=lambda x: x["return"])
        out[f"best_{name}"] = max(b, key=lambda x: x["return"])
    out["note"] = "first/last week & month may be partial (see 'days')"
    return out

def rolling(rp, rb, rf, dates, window=63) -> dict:
    pts = []
    for end in range(window, len(rp) + 1):
        s = slice(end - window, end)
        p = rp[s]
        row = {"date": dates[end], "volatility": _sd(p) * SQRT_T}
        if rb is not None:
            b = rb[s]
            vb = _var(b)
            row["beta"] = _cov(p, b) / vb if vb > EPS else None
        if rf is not None:
            x = [a - c for a, c in zip(p, rf[s])]
            sd = _sd(x)
            row["sharpe"] = _mean(x) / sd * SQRT_T if sd > EPS else None
        pts.append(row)
    return {"window_trading_days": window, "points": pts}

def _dump(x):
    if isinstance(x, Metric):
        return x.to_dict()
    if isinstance(x, dict):
        return {k: _dump(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_dump(v) for v in x]
    if isinstance(x, date):
        return x.isoformat()
    return x

# ---------- orchestration ----------
def analyze(rp, rb, rf, dates: Sequence[date], mar_annual=0.0, rolling_window=63) -> dict:
    n = _validate(rp, *[s for s in (rb, rf) if s is not None])
    if n == 0 or len(dates) != n + 1:
        raise ValueError("need ≥1 return and len(dates) = len(returns)+1")
    dr = list(dates[1:])
    D = (dates[-1] - dates[0]).days
    Rp = cumulative_return(rp)
    na_b = lambda: _na(UNAVAILABLE, "", "", n, "benchmark series unavailable")

    perf = {"portfolio_return": total_return(rp), "volatility": annualized_volatility(rp), "cagr": cagr(Rp, D)}
    bench_keys = ("benchmark_return", "benchmark_volatility", "active_return", "relative_wealth", "beta",
                  "r_squared", "correlation", "hit_rate", "up_capture", "down_capture", "tracking_error")
    if rb is not None:
        Rb = cumulative_return(rb)
        perf.update({
            "benchmark_return": total_return(rb), "benchmark_volatility": annualized_volatility(rb),
            "active_return": _ok(Rp - Rb, "decimal (display ×100 as pp)", "R_p − R_b", n),
            "relative_wealth": _ok(relative_wealth(Rp, Rb), "decimal", "(1+R_p)/(1+R_b) − 1", n),
            **beta_r2(rp, rb), "hit_rate": hit_rate(rp, rb),
            "up_capture": capture_ratio(rp, rb, True), "down_capture": capture_ratio(rp, rb, False),
            "tracking_error": tracking_error(rp, rb)})
    else:
        perf.update({k: na_b() for k in bench_keys})

    dd = drawdown(rp, dates)
    ve = historical_var_es(rp)
    ra = {"sharpe": sharpe_ratio(rp, rf), "sortino": sortino_ratio(rp, mar_annual),
          "information_ratio": information_ratio(rp, rb) if rb is not None else na_b(),
          "downside_beta": downside_beta(rp, rb) if rb is not None else na_b(),
          "tracking_error": perf["tracking_error"], **capm_regression(rp, rb, rf),
          "calmar": calmar(perf["cagr"], dd["max_drawdown"].value, n)}
    tail = {"max_drawdown": dd["max_drawdown"], "current_drawdown": dd["current_drawdown"],
            "drawdown_episode": dd["episode"], "longest_underwater_trading_days": dd["longest_underwater_trading_days"],
            "var_95": ve["var"], "es_95": ve["es"], "downside_deviation": downside_deviation(rp, mar_annual),
            "extremes": _extremes(rp, dr), "drawdown_series": dd["series"]}

    wp, wb, series = 1.0, 1.0, [{"date": dates[0], "portfolio": 0.0, "benchmark": 0.0 if rb is not None else None}]
    for i, d in enumerate(dr):
        wp *= 1 + rp[i]
        if rb is not None:
            wb *= 1 + rb[i]
        series.append({"date": d, "portfolio": wp - 1, "benchmark": wb - 1 if rb is not None else None})
    for s in series:
        s["active"] = None if s["benchmark"] is None else s["portfolio"] - s["benchmark"]

    mp = {x["period"]: x for x in period_returns(rp, dr, "M")}
    mb = {x["period"]: x for x in period_returns(rb, dr, "M")} if rb is not None else {}
    monthly = [{"period": k, "portfolio": v["return"], "benchmark": mb.get(k, {}).get("return"),
                "active": (v["return"] - mb[k]["return"]) if k in mb else None, "days": v["days"]}
               for k, v in mp.items()]

    return _dump({"performance": perf, "risk_adjusted": ra, "tail": tail, "series": series,
                  "monthly": monthly, "rolling": rolling(rp, rb, rf, dates, rolling_window),
                  "conventions": {"mar_annual": mar_annual, "trading_days": TRADING_DAYS,
                                  "cagr_day_count": 365.25, "statistics": "sample (ddof=1)",
                                  "method_version": METHOD_VERSION}})
