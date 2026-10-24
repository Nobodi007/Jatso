"""Jatso US Stock Risk Engine, Phase 3: position contribution (partial attribution). Pure, no I/O.

Mirrors ledger.build_nav exactly: NAV_t = cash_t + Σ q_i,t · P_i,t, trades with session_date ≤ t are
applied before valuing day t, prices are the forward-filled closes. With no external cash flows:

  ΔNAV_t = Σ_i q_i,t−1 · (P_i,t − P_i,t−1)                   price effect on opening quantity
         + Σ_trades on t [ ±q · (P_i,t − p_fill) − fee ]       fill price vs close, fees (buy +, sell −)

c_i,t = price effect / NAV_t−1. Daily pieces are linked by prior wealth W_t−1 = NAV_t−1 / NAV_0:
Σ_t W_t−1 · (Σ_i c_i,t + e_t) = NAV_T / NAV_0 − 1, so position contributions plus execution/fees equal
the portfolio return exactly (up to floating point). The check is returned, not assumed.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Mapping, Sequence

from . import ledger as L

RESIDUAL_TOL = 1e-9
PARTIAL_NOTE = ("Partial attribution: position contribution only. No S&P 500 sector weights are available, "
                "so Brinson allocation/selection effects are not computed.")
METHOD = ("c_i = Σ_t W_t−1 · q_i,t−1 · (P_i,t − P_i,t−1) / NAV_t−1, linked by prior wealth "
          "W_t−1 = NAV_t−1 / NAV_0; positions + execution_and_fees = portfolio return")
EXEC_NOTE = ("Fill price vs same-day close on trade days, net of fees. Includes positions opened and "
             "closed within one session.")


def attribution(trades: Sequence[L.Trade], calendar: Sequence[date],
                px: Mapping[str, Sequence[float | None]], nav: Sequence[L.NavPoint]) -> dict:
    """trades: split-adjusted, sorted as in build_nav. px[sym][k] = forward-filled close on calendar[k]."""
    n = len(calendar)
    if n < 2 or len(nav) != n:
        raise ValueError("need ≥2 calendar days and one NAV point per day")
    if any(p.nav is None or p.nav <= 0 for p in nav):
        raise ValueError("NAV unavailable or non-positive")
    nav0 = nav[0].nav
    qty: dict[str, float] = {}
    idx = 0

    def apply(k: int) -> list[L.Trade]:
        nonlocal idx
        applied = []
        while idx < len(trades) and trades[idx].session_date <= calendar[k]:
            t = trades[idx]
            held = qty.get(t.symbol, 0.0)
            qty[t.symbol] = held + t.qty if t.side == "buy" else held - t.qty
            applied.append(t)
            idx += 1
        return applied

    def price(sym: str, k: int) -> float:
        series = px.get(sym)
        v = None if series is None else series[k]
        if v is None:
            raise ValueError(f"missing price for {sym} on {calendar[k].isoformat()}")
        return v

    apply(0)                                            # opening book, same as build_nav day 0
    acc: dict[str, dict] = {}
    exec_total = 0.0
    for k in range(1, n):
        nav_prev = nav[k - 1].nav
        link = nav_prev / nav0
        for s, q in qty.items():                        # opening quantities of day k
            if q <= L.QTY_EPS:
                continue
            p0, p1 = price(s, k - 1), price(s, k)
            a = acc.setdefault(s, {"c": 0.0, "w": 0.0, "d": 0})
            a["c"] += link * q * (p1 - p0) / nav_prev
            a["w"] += q * p0 / nav_prev
            a["d"] += 1
        e = 0.0
        for t in apply(k):                              # trades applied before valuing day k
            sign = 1.0 if t.side == "buy" else -1.0
            e += sign * t.qty * (price(t.symbol, k) - t.price) - t.fee
        exec_total += link * e / nav_prev

    rp = nav[-1].nav / nav0 - 1.0
    rows = [{"symbol": s, "contribution": a["c"], "avg_weight_nav": a["w"] / a["d"],
             "days_held": a["d"], "held_now": qty.get(s, 0.0) > L.QTY_EPS} for s, a in acc.items()]
    rows.sort(key=lambda r: -r["contribution"])
    pos_sum = math.fsum(r["contribution"] for r in rows)
    resid = rp - (pos_sum + exec_total)
    return {
        "partial": True, "partial_note": PARTIAL_NOTE, "method": METHOD,
        "unit": "decimal of start-of-period NAV (display ×100 as pp)",
        "n_obs": n - 1, "portfolio_return": rp, "positions": rows,
        "execution_and_fees": {"value": exec_total, "note": EXEC_NOTE},
        "sum_check": {"positions": pos_sum, "execution_and_fees": exec_total, "portfolio_return": rp,
                      "residual": resid, "tolerance": RESIDUAL_TOL, "ok": abs(resid) <= RESIDUAL_TOL},
    }
