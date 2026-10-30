"""Canonical stock ledger: parsing, split adjustment, average-cost positions, daily NAV. Pure."""
from __future__ import annotations

import re
import math
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
MARKET_CLOSE = time(16, 0)
QTY_EPS = 1e-9
_FRAC = re.compile(r"\.(\d+)")


class LedgerError(ValueError):
    pass


@dataclass(frozen=True)
class Trade:
    id: int
    symbol: str
    side: str
    qty: float
    price: float
    fee: float
    ts: datetime
    session_date: date


@dataclass(frozen=True)
class Position:
    symbol: str
    qty: float
    avg_cost: float
    realized_pnl_gross: float
    fees: float


@dataclass(frozen=True)
class NavPoint:
    date: date
    nav: float | None
    cash: float
    market_value: float | None
    stale: tuple[str, ...]
    flow: float = 0.0   # external cash flow applied at the START of this day (deposit +, withdrawal −); 0 on the base day


@dataclass(frozen=True)
class CashFlow:
    """External cash flow (deposit +, withdrawal −) effective from the START of `date`.
    Weekend/holiday dates take effect on the next trading day in the calendar."""
    id: int
    date: date
    amount: float


def to_flows(rows: list[dict]) -> list[CashFlow]:
    out = []
    for r in rows:
        try:
            amt = float(r["amount"])
            d = date.fromisoformat(str(r["flow_date"])[:10])
            fid = int(r["id"])
        except (KeyError, TypeError, ValueError) as e:
            raise LedgerError(f"unparseable cash flow id={r.get('id')}: {e}") from None
        if not math.isfinite(amt) or amt == 0:
            raise LedgerError(f"invalid cash flow id={r.get('id')}")
        out.append(CashFlow(fid, d, amt))
    out.sort(key=lambda f: (f.date, f.id))
    return out


def parse_ts(v) -> datetime:
    s = str(v).strip().replace(" ", "T").replace("Z", "+00:00")
    s = _FRAC.sub(lambda m: "." + (m.group(1) + "000000")[:6], s, count=1)
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        raise LedgerError(f"naive timestamp: {v}")
    return dt.astimezone(timezone.utc)


def session_date(ts_utc: datetime) -> date:
    """Trades at/after 16:00 ET belong to the next session (applied from the next trading day)."""
    et = ts_utc.astimezone(ET)
    return et.date() if et.time() < MARKET_CLOSE else et.date() + timedelta(days=1)


def to_trades(rows: list[dict]) -> list[Trade]:
    out = []
    for r in rows:
        try:
            side = str(r["side"]).lower()
            qty, price, fee = float(r["qty"]), float(r["price"]), float(r.get("fee") or 0)
            ts = parse_ts(r["ts"])
        except (KeyError, TypeError, ValueError) as e:
            raise LedgerError(f"unparseable trade id={r.get('id')}: {e}") from None
        if side not in ("buy", "sell") or not (qty > 0 and price > 0 and fee >= 0):
            raise LedgerError(f"invalid trade id={r.get('id')}")
        out.append(Trade(int(r["id"]), str(r["symbol"]).upper(), side, qty, price, fee, ts, session_date(ts)))
    out.sort(key=lambda t: (t.ts, t.id))
    return out


def adjust_for_splits(trades: list[Trade], splits: dict[str, list[tuple[date, float]]]) -> list[Trade]:
    """Restate trades in today's split-adjusted units. Split applies if ex-date > ET calendar date of the fill
    (after-hours fills before the ex-date still carry pre-split prices)."""
    out = []
    for t in trades:
        f = 1.0
        for d, ratio in splits.get(t.symbol, []):
            if d > t.ts.astimezone(ET).date():
                f *= ratio
        out.append(t if f == 1.0 else replace(t, qty=t.qty * f, price=t.price / f))
    return out


def cash_delta(t: Trade) -> float:
    return -(t.qty * t.price + t.fee) if t.side == "buy" else t.qty * t.price - t.fee


def replay_cash(trades: list[Trade], initial_cash: float) -> float:
    return initial_cash + sum(cash_delta(t) for t in trades)


def positions(trades: list[Trade]) -> dict[str, Position]:
    """Average cost; fees tracked separately (not capitalized)."""
    book: dict[str, list[float]] = {}
    for t in trades:
        q, avg, real, fees = book.get(t.symbol, [0.0, 0.0, 0.0, 0.0])
        if t.side == "buy":
            nq = q + t.qty
            avg = (q * avg + t.qty * t.price) / nq
            q = nq
        else:
            if t.qty > q + QTY_EPS:
                raise LedgerError(f"oversell in trade id={t.id} ({t.symbol})")
            real += (t.price - avg) * t.qty
            q -= t.qty
            if q < QTY_EPS:
                q, avg = 0.0, 0.0
        book[t.symbol] = [q, avg, real, fees + t.fee]
    return {s: Position(s, *v) for s, v in book.items()}


def build_nav(trades: list[Trade], initial_cash: float, calendar: list[date],
              closes: dict[str, dict[date, float]], max_ffill: int = 5,
              flows: list[CashFlow] | None = None) -> tuple[list[NavPoint], list[dict]]:
    """NAV_t = cash_t + Σ q_i,t · close_i,t. Trades with session_date ≤ t are applied before valuing t.
    flows (optional): external cash flows with date ≤ t are added to cash at the start of t, before trades.
    Flows dated on/before calendar[0] are part of the opening balance (NavPoint.flow = 0 on the base day)."""
    flows = flows or []
    qty: dict[str, float] = {}
    cash, i, j = initial_cash, 0, 0
    last: dict[str, tuple[int, float]] = {}
    for sym, series in closes.items():                     # seed with last close before window
        prior = [d for d in series if d < calendar[0] and series[d] > 0]
        if prior:
            last[sym] = (-1, series[max(prior)])
    issues: dict[tuple[str, str], dict] = {}
    points = []
    for k, d in enumerate(calendar):
        flow_today = 0.0
        while j < len(flows) and flows[j].date <= d:
            cash += flows[j].amount
            if k > 0:
                flow_today += flows[j].amount
            j += 1
        while i < len(trades) and trades[i].session_date <= d:
            t = trades[i]
            held = qty.get(t.symbol, 0.0)
            if t.side == "sell" and t.qty > held + QTY_EPS:
                raise LedgerError(f"oversell in trade id={t.id} ({t.symbol})")
            qty[t.symbol] = held + t.qty if t.side == "buy" else held - t.qty
            cash += cash_delta(t)
            i += 1
        for sym, series in closes.items():
            c = series.get(d)
            if c is not None and c > 0:
                last[sym] = (k, c)
        mv, ok, stale = 0.0, True, []
        for sym, q in qty.items():
            if q <= QTY_EPS:
                continue
            hit = last.get(sym)
            code = None
            if hit is None:
                code = "missing_price"
            elif k - hit[0] > max_ffill:
                code = "stale_price_beyond_limit"
            if code:
                ok = False
                rec = issues.setdefault((code, sym), {"code": code, "symbol": sym, "first_date": d.isoformat(), "days": 0})
                rec["days"] += 1
                continue
            if k - hit[0] > 0:
                stale.append(sym)
            mv += q * hit[1]
        points.append(NavPoint(d, cash + mv if ok else None, cash, mv if ok else None, tuple(stale), flow_today))
    return points, list(issues.values())


def returns_from_nav(nav: list[NavPoint]) -> list[float]:
    """Daily time-weighted returns. External flows arrive at the start of the day, so the capital at work is
    NAV_{t−1} + flow_t:  r_t = NAV_t / (NAV_{t−1} + flow_t) − 1.  With no flows this is exactly NAV_t/NAV_{t−1} − 1."""
    out = []
    for i in range(1, len(nav)):
        if nav[i].nav is None or nav[i - 1].nav is None:
            raise LedgerError("NAV unavailable")
        base = nav[i - 1].nav + nav[i].flow
        if base <= 0:
            raise LedgerError(f"no capital at start of {nav[i].date.isoformat()} (NAV + flow ≤ 0)")
        out.append(nav[i].nav / base - 1)
    return out
