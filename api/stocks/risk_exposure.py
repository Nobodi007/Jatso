"""Jatso US Stock Risk Engine, Phase 2: exposure, concentration, risk decomposition, stress. Pure, no I/O."""
from __future__ import annotations

import math
from typing import Mapping, Sequence

from . import risk_engine as E

MIN_OBS_COV = 60
SHOCK_MIN = -1.0
HYPOTHETICAL = "Hypothetical scenario, not a forecast or a prediction."


def _m(x):
    return x.to_dict() if hasattr(x, "to_dict") else x


def nav_weights(holdings: Mapping[str, dict], cash: float) -> tuple[dict[str, float], float, float]:
    """(weights of NAV per symbol, equity value, NAV). Cash is the residual."""
    mv = {s: h["qty"] * h["price"] for s, h in holdings.items()}
    eq = math.fsum(mv.values())
    nav = cash + eq
    return ({s: v / nav for s, v in mv.items()} if nav > 0 else {}), eq, nav


def exposure(holdings: Mapping[str, dict], cash: float, sectors: Mapping[str, str | None]) -> dict:
    w_nav, eq, nav = nav_weights(holdings, cash)
    if nav <= 0 or eq <= 0:
        na = E._na(E.UNDEFINED, "", "", 0, "no equity positions")
        return {"nav": nav, "equity_value": eq, "cash_weight": 1.0 if nav > 0 else None, "positions": [],
                "sectors": [], "hhi": _m(na), "effective_n": _m(na), "top1": _m(na), "top3": _m(na), "top5": _m(na)}
    rows = []
    for s, h in holdings.items():
        mv = h["qty"] * h["price"]
        rows.append({"symbol": s, "qty": h["qty"], "price": h["price"], "market_value": mv,
                     "weight_nav": mv / nav, "weight_equity": mv / eq,
                     "avg_cost": h.get("avg_cost"),
                     "unrealized_pnl": (h["price"] - h["avg_cost"]) * h["qty"] if h.get("avg_cost") else None})
    rows.sort(key=lambda r: -r["market_value"])
    we = [r["weight_equity"] for r in rows]
    hhi = math.fsum(w * w for w in we)
    n = len(rows)
    top = lambda k: E._ok(math.fsum(we[:k]), "share of equity", f"Σ top-{k} equity weights", n)
    sec: dict[str, float] = {}
    for r in rows:
        k = sectors.get(r["symbol"]) or "Unknown"
        sec[k] = sec.get(k, 0.0) + r["market_value"]
    return {
        "nav": nav, "equity_value": eq, "cash": cash, "cash_weight": cash / nav, "positions": rows,
        "hhi": _m(E._ok(hhi, "index 0..1", "HHI = Σ w_i² (equity weights)", n)),
        "effective_n": _m(E._ok(1.0 / hhi, "positions", "N_eff = 1 / HHI", n)),
        "top1": _m(top(1)), "top3": _m(top(3)), "top5": _m(top(5)),
        "sectors": sorted(({"sector": k, "market_value": v, "weight_nav": v / nav, "weight_equity": v / eq}
                           for k, v in sec.items()), key=lambda r: -r["market_value"]),
    }


def _complete(r: Sequence[float | None] | None) -> bool:
    return bool(r) and all(v is not None and math.isfinite(v) for v in r)


def risk_decomposition(w_nav: Mapping[str, float], returns: Mapping[str, Sequence[float | None]]) -> dict:
    """Historical-covariance decomposition of CURRENT weights (holdings held constant over the window)."""
    f_vol = "σ_p = √(wᵀΣw), Σ = sample covariance ×252, w = current NAV weights (cash has zero variance)"
    syms, excluded = [], []
    n = max((len(v) for v in returns.values() if v), default=0)
    for s in w_nav:
        r = returns.get(s)
        if not r or len(r) != n:
            excluded.append({"symbol": s, "reason": "no return history"})
        elif not _complete(r):
            excluded.append({"symbol": s, "reason": "incomplete price history in window"})
        else:
            syms.append(s)
    if not syms or n < MIN_OBS_COV:
        na = E._na(E.INSUFFICIENT, "", f_vol, n, f"need ≥{MIN_OBS_COV} aligned observations and priced holdings")
        return {"portfolio_volatility": _m(na), "contributions": [], "correlation": None, "excluded": excluded}
    k = len(syms)
    cov = [[E._cov(returns[a], returns[b]) * E.TRADING_DAYS for b in syms] for a in syms]
    w = [w_nav[s] for s in syms]
    sw = [math.fsum(cov[i][j] * w[j] for j in range(k)) for i in range(k)]       # Σw
    var = math.fsum(w[i] * sw[i] for i in range(k))
    if var <= E.EPS:
        na = E._na(E.UNDEFINED, "", f_vol, n, "portfolio variance is zero")
        return {"portfolio_volatility": _m(na), "contributions": [], "correlation": None, "excluded": excluded}
    sig = math.sqrt(var)
    limited = n < E.MIN_OBS_FULL or bool(excluded)
    vol = E.Metric(sig, E.LIMITED if limited else E.OK, "annualized volatility", f_vol, n,
                   "short window or excluded holdings" if limited else None)
    vols = [math.sqrt(max(cov[i][i], 0.0)) for i in range(k)]
    contrib = []
    for i, s in enumerate(syms):
        mcr = sw[i] / sig
        ccr = w[i] * mcr
        contrib.append({"symbol": s, "weight_nav": w[i], "volatility": vols[i], "mcr": mcr, "ccr": ccr,
                        "pct_of_risk": ccr / sig})
    contrib.sort(key=lambda r: -r["pct_of_risk"])
    corr = [[(cov[i][j] / (vols[i] * vols[j])) if vols[i] > E.EPS and vols[j] > E.EPS else None
             for j in range(k)] for i in range(k)]
    pairs = sorted(({"a": syms[i], "b": syms[j], "correlation": corr[i][j]}
                    for i in range(k) for j in range(i + 1, k) if corr[i][j] is not None),
                   key=lambda p: -p["correlation"])
    if pairs:
        avgc = E._ok(math.fsum(p["correlation"] for p in pairs) / len(pairs), "correlation",
                     "mean of pairwise correlations", n)
    else:
        avgc = E._na(E.UNDEFINED, "correlation", "mean of pairwise correlations", n, "need ≥2 priced holdings")
    sum_wv = math.fsum(w[i] * vols[i] for i in range(k))
    return {"portfolio_volatility": _m(vol),
            "diversification_ratio": _m(E._ok(sum_wv / sig, "ratio", "Σ w_i σ_i / σ_p", n)),
            "avg_pairwise_correlation": _m(avgc),
            "contributions": contrib, "correlation": {"symbols": syms, "matrix": corr},
            "top_pairs": pairs[:5], "excluded": excluded}


def holding_betas(returns: Mapping[str, Sequence[float | None]], bench: Sequence[float] | None) -> dict[str, E.Metric]:
    out = {}
    for s, r in returns.items():
        if not bench:
            out[s] = E._na(E.UNAVAILABLE, "beta", "OLS slope vs benchmark", 0, "benchmark unavailable")
        elif not _complete(r) or len(r) != len(bench):
            out[s] = E._na(E.INSUFFICIENT, "beta", "OLS slope vs benchmark", 0, "incomplete price history")
        else:
            out[s] = E.beta_r2(list(r), list(bench))["beta"]
    return out


def stress(holdings: Mapping[str, dict], cash: float, betas: Mapping[str, E.Metric],
           market_shock: float | None, shocks: Mapping[str, float]) -> dict:
    """Instantaneous shock: P&L_i = MV_i × shock_i. shock_i = explicit override, else β_i × market_shock."""
    nav = cash + math.fsum(h["qty"] * h["price"] for h in holdings.values())
    rows, skipped, total = [], [], 0.0
    for s, h in holdings.items():
        mv = h["qty"] * h["price"]
        if s in shocks:
            sh, basis = shocks[s], "explicit symbol shock"
        elif market_shock is not None and betas.get(s) is not None and betas[s].value is not None:
            sh, basis = betas[s].value * market_shock, f"β ({betas[s].status}) × market shock"
        else:
            skipped.append({"symbol": s, "reason": "no explicit shock and beta unavailable"})
            continue
        sh = max(SHOCK_MIN, sh)                      # a long position cannot lose more than 100%
        pnl = mv * sh
        total += pnl
        rows.append({"symbol": s, "market_value": mv, "shock": sh, "pnl": pnl, "basis": basis})
    rows.sort(key=lambda r: r["pnl"])
    return {"hypothetical": True, "disclaimer": HYPOTHETICAL,
            "scenario": {"market_shock": market_shock, "symbol_shocks": dict(shocks)},
            "nav_before": nav, "pnl": total, "pnl_pct_nav": total / nav if nav > 0 else None,
            "nav_after": nav + total, "positions": rows, "skipped": skipped}
