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
EXEC_NOTE = ("Fill price vs same-day close on trade days, before fees. Includes positions opened and "
             "closed within one session.")
FEES_NOTE = "Commissions/fees paid on trade days, linked the same way as the position contributions."
CASH_DRAG_NOTE = ("Memo, not part of the sum. Σ_t W_t−1 · (−cash weight_t−1) · (return of the invested book on t): "
                  "negative = holding cash cost return while stocks rose, positive = cash cushioned a fall. "
                  "Fully-invested contribution = positions − cash_drag. Cash earns no interest in this ledger.")


def attribution(trades: Sequence[L.Trade], calendar: Sequence[date],
                px: Mapping[str, Sequence[float | None]], nav: Sequence[L.NavPoint]) -> dict:
    """trades: split-adjusted, sorted as in build_nav. px[sym][k] = forward-filled close on calendar[k]."""
    n = len(calendar)
    if n < 2 or len(nav) != n:
        raise ValueError("need ≥2 calendar days and one NAV point per day")
    has_flows = any(p.flow != 0 for p in nav[1:])
    if any(p.nav is None for p in nav) or (not has_flows and any(p.nav <= 0 for p in nav)):
        raise ValueError("NAV unavailable or non-positive")
    nav0 = nav[0].nav                                   # may be 0 only when flows fund the account after the base day
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
    exec_total = fees_total = cash_drag = 0.0
    cash_w_sum = 0.0
    cum = 1.0                                           # cumulative time-weighted growth (used only with flows)
    for k in range(1, n):
        flow = nav[k].flow                              # external flow arrives at the start of day k
        nav_prev = nav[k - 1].nav + flow                # capital at work on day k (= NAV_{k−1} when no flows)
        if nav_prev <= 0:
            raise ValueError(f"no capital at start of {calendar[k].isoformat()}")
        link = cum if has_flows else nav[k - 1].nav / nav0
        eq_open = eq_pnl = 0.0
        for s, q in qty.items():                        # opening quantities of day k
            if q <= L.QTY_EPS:
                continue
            p0, p1 = price(s, k - 1), price(s, k)
            a = acc.setdefault(s, {"c": 0.0, "w": 0.0, "d": 0})
            a["c"] += link * q * (p1 - p0) / nav_prev
            a["w"] += q * p0 / nav_prev
            a["d"] += 1
            eq_open += q * p0
            eq_pnl += q * (p1 - p0)
        cash_w = (nav[k - 1].cash + flow) / nav_prev
        cash_w_sum += cash_w
        if eq_open > 0:
            cash_drag += link * (-cash_w) * (eq_pnl / eq_open)
        e = f = 0.0
        for t in apply(k):                              # trades applied before valuing day k
            sign = 1.0 if t.side == "buy" else -1.0
            e += sign * t.qty * (price(t.symbol, k) - t.price)
            f -= t.fee
        exec_total += link * e / nav_prev
        fees_total += link * f / nav_prev
        cum *= nav[k].nav / nav_prev

    rp = (cum - 1.0) if has_flows else nav[-1].nav / nav0 - 1.0
    rows = [{"symbol": s, "contribution": a["c"], "avg_weight_nav": a["w"] / a["d"],
             "days_held": a["d"], "held_now": qty.get(s, 0.0) > L.QTY_EPS} for s, a in acc.items()]
    rows.sort(key=lambda r: -r["contribution"])
    pos_sum = math.fsum(r["contribution"] for r in rows)
    resid = rp - (pos_sum + exec_total + fees_total)
    return {
        "partial": True, "partial_note": PARTIAL_NOTE, "method": METHOD,
        "unit": ("decimal of capital at work (start-of-period NAV; external flows applied at start of day)"
                 if has_flows else "decimal of start-of-period NAV (display ×100 as pp)"),
        "external_flows": has_flows,
        "n_obs": n - 1, "portfolio_return": rp, "positions": rows,
        "execution": {"value": exec_total, "note": EXEC_NOTE},
        "fees": {"value": fees_total, "note": FEES_NOTE},
        "execution_and_fees": {"value": exec_total + fees_total, "note": EXEC_NOTE + " " + FEES_NOTE},
        "cash_drag": {"value": cash_drag, "avg_cash_weight": cash_w_sum / (n - 1), "memo": True,
                      "note": CASH_DRAG_NOTE},
        "sum_check": {"positions": pos_sum, "execution": exec_total, "fees": fees_total,
                      "execution_and_fees": exec_total + fees_total, "portfolio_return": rp,
                      "residual": resid, "tolerance": RESIDUAL_TOL, "ok": abs(resid) <= RESIDUAL_TOL},
    }


SECTOR_NOTE = "Finnhub industry (not GICS); approximate. Unknown = no sector available for that symbol."


def by_sector(positions: Sequence[Mapping], sectors: Mapping[str, str | None]) -> list[dict]:
    """Sum position contributions per sector (sold positions included). Sums to the position total exactly."""
    agg: dict[str, dict] = {}
    for r in positions:
        k = sectors.get(r["symbol"]) or "Unknown"
        a = agg.setdefault(k, {"sector": k, "contribution": 0.0, "avg_weight_nav": 0.0, "symbols": []})
        a["contribution"] += r["contribution"]
        a["avg_weight_nav"] += r["avg_weight_nav"]     # sum of each symbol's own average weight while held
        a["symbols"].append(r["symbol"])
    out = list(agg.values())
    for a in out:
        a["contribution"] = math.fsum(r["contribution"] for r in positions
                                      if (sectors.get(r["symbol"]) or "Unknown") == a["sector"])
        a["symbols"].sort()
    return sorted(out, key=lambda r: -r["contribution"])


def pnl_breakdown(pos: Mapping[str, L.Position], prices: Mapping[str, float | None],
                  initial_cash: float, nav_end: float | None) -> dict:
    """USD P&L since the first trade, average-cost basis (matches ledger.positions).
    total = realized_gross + unrealized − fees; reconciles to NAV_end − initial_cash when every trade is valued."""
    rows, rg, fees, unr, incomplete = [], 0.0, 0.0, 0.0, []
    for s, p in sorted(pos.items()):
        held = p.qty > L.QTY_EPS
        px = prices.get(s)
        u = (px - p.avg_cost) * p.qty if held and px is not None else (0.0 if not held else None)
        if held and px is None:
            incomplete.append(s)
        rows.append({"symbol": s, "open_qty": p.qty, "avg_cost": p.avg_cost if held else None,
                     "price": px if held else None, "realized_gross": p.realized_pnl_gross, "fees": p.fees,
                     "unrealized": u,
                     "total_net": None if u is None else p.realized_pnl_gross + u - p.fees})
        rg += p.realized_pnl_gross
        fees += p.fees
        unr += u or 0.0
    total = rg + unr - fees
    out = {"basis": "average cost, fees not capitalized, split-adjusted, since first trade; "
                    "total = realized + unrealized − fees",
           "symbols": rows, "realized_gross": rg, "unrealized": unr, "fees_paid": fees, "total_net": total,
           "incomplete_symbols": incomplete}
    if nav_end is not None and not incomplete:
        diff = (nav_end - initial_cash) - total
        out["check"] = {"nav_change": nav_end - initial_cash, "total_net": total, "difference": diff,
                        "ok": abs(diff) <= 0.01}
        out["basis_note"] = "nav_change = NAV − capital contributed (initial cash + net deposits)"
    return out
