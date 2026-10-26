import asyncio
import logging
import math
import os
import re
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

import jwt  # PyJWT
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from . import ledger as L
from . import risk_data as rd
from .db import SbError, sb
from .router import get_quote

log = logging.getLogger("stocks.stock_book")


def get_current_email(authorization: str = Header(default="")) -> str:
    token = authorization.removeprefix("Bearer ").strip()
    if not token or token in ("null", "undefined"):
        raise HTTPException(401, "unauthorized")
    try:
        data = jwt.decode(token, os.environ["AUTH_JWT_SECRET"], algorithms=["HS256"])
    except KeyError:
        log.error("AUTH_JWT_SECRET is not set")
        raise HTTPException(401, "unauthorized")
    except Exception:
        raise HTTPException(401, "unauthorized")       # never echo JWT errors/claims back to the caller
    email = data.get("email") or data.get("sub")
    if not email:
        raise HTTPException(401, "unauthorized")
    return str(email).lower()


router = APIRouter(prefix="/api/stock-book", tags=["stock-book"])

OWNER_EMAILS = {e.strip().lower() for e in os.getenv("STOCK_OWNER_EMAILS", "").split(",") if e.strip()}
OWNER_CASH = 100_000_000.0
DEFAULT_CASH = 1_000_000.0
FEE_BPS = Decimal(os.getenv("STOCK_FEE_BPS", "0"))
FEE_MIN = Decimal(os.getenv("STOCK_FEE_MIN_USD", "0"))
MAX_QTY = 1_000_000
SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-]{1,12}$")


class TradeIn(BaseModel):
    symbol: str
    side: str = Field(pattern="^(buy|sell)$")
    qty: float = Field(gt=0, le=MAX_QTY)
    price: float | None = None   # DEPRECATED: ignored, server prices every trade
    fee: float | None = None     # DEPRECATED: ignored, server computes fee
    note: str | None = Field(default=None, max_length=280)


def _fee(notional: float) -> float:
    if FEE_BPS <= 0 and FEE_MIN <= 0:
        return 0.0
    fee = max(Decimal(str(notional)) * FEE_BPS / Decimal(10000), FEE_MIN)
    return float(fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


async def _quote(sym: str) -> tuple[float, str | None]:
    try:
        q = await get_quote(sym)
        price = float(q["price"])
    except HTTPException as e:
        if e.status_code == 404:
            raise HTTPException(404, f"ไม่พบสัญลักษณ์ {sym}")
        raise HTTPException(503, f"ดึงราคา {sym} ไม่ได้ ปฏิเสธคำสั่ง")
    except Exception:
        raise HTTPException(503, f"ดึงราคา {sym} ไม่ได้ ปฏิเสธคำสั่ง")
    if not math.isfinite(price) or price <= 0:
        raise HTTPException(503, f"ดึงราคา {sym} ไม่ได้ ปฏิเสธคำสั่ง")
    ts = q.get("timestamp")
    quote_ts = (datetime.fromtimestamp(int(ts), timezone.utc).isoformat()
                if isinstance(ts, (int, float)) and ts > 0 else None)
    return price, quote_ts


async def _price_or_none(sym: str) -> float | None:
    try:
        return (await _quote(sym))[0]
    except Exception:
        return None


async def _account(email: str) -> dict:
    acc = await rd.account(email)
    if acc:
        return acc
    start = OWNER_CASH if email.lower() in OWNER_EMAILS else DEFAULT_CASH
    row = {"email": email, "initial_cash": start, "cash": start,
           "inception_at": datetime.now(timezone.utc).isoformat()}
    try:
        await sb("POST", "stock_accounts", json=row)
    except HTTPException as e:
        if e.status_code != 409:          # 409 = concurrent first request already created it
            raise
    return await rd.account(email) or row


async def _adjusted(rows: list[dict]) -> tuple[list[L.Trade], list[str]]:
    """Split-adjusted trades; best effort (warnings list symbols whose split data failed)."""
    tr = L.to_trades(rows)
    syms = sorted({t.symbol for t in tr})
    res = await asyncio.gather(*(rd.splits(s) for s in syms), return_exceptions=True)
    spl, warnings = {}, []
    for s, r in zip(syms, res):
        if isinstance(r, Exception):
            warnings.append(f"splits_unavailable:{s}")
        else:
            spl[s] = r
    return L.adjust_for_splits(tr, spl), warnings


@router.get("/portfolio")
async def portfolio(email: str = Depends(get_current_email)):
    acc = await _account(email)
    rows = await rd.active_trades(email)
    try:
        tr, warnings = await _adjusted(rows)
        pos = {s: p for s, p in L.positions(tr).items() if p.qty > L.QTY_EPS}
    except L.LedgerError:
        log.exception("ledger inconsistent for %s", email)
        raise HTTPException(409, "Trade history inconsistent.")
    syms = sorted(pos)
    prices = await asyncio.gather(*(_price_or_none(s) for s in syms))
    out, mv_total = [], 0.0
    for sym, px in zip(syms, prices):
        p = pos[sym]
        last = px or p.avg_cost
        mv = last * p.qty
        mv_total += mv
        out.append({
            "symbol": sym, "qty": p.qty, "avg_cost": p.avg_cost, "last": last,
            "last_source": "quote" if px else "avg_cost_fallback",
            "market_value": mv,
            "unrealized_pnl": (last - p.avg_cost) * p.qty,
            "unrealized_pct": (last / p.avg_cost - 1) * 100 if p.avg_cost else 0,
        })
    cash, init = float(acc["cash"]), float(acc["initial_cash"])
    equity = cash + mv_total
    return {
        "initial_cash": init, "cash": cash, "market_value": mv_total,
        "equity": equity, "pnl": equity - init, "pnl_pct": (equity / init - 1) * 100,
        "positions": sorted(out, key=lambda r: -r["market_value"]), "warnings": warnings,
    }


@router.get("/trades")
async def trades(email: str = Depends(get_current_email)):
    return list(reversed(await rd.active_trades(email)))


@router.post("/trade")
async def trade(body: TradeIn, email: str = Depends(get_current_email)):
    sym = body.symbol.strip().upper()
    if not SYMBOL_RE.match(sym):
        raise HTTPException(400, "Invalid symbol.")
    acc = await _account(email)
    rows = await rd.active_trades(email)
    last_id = max((int(r["id"]) for r in rows), default=0)
    price, quote_ts = await _quote(sym)
    qty = round(float(body.qty), 6)
    if qty <= 0:
        raise HTTPException(400, "Quantity too small.")
    fee = _fee(qty * price)
    realized = None
    warnings: list[str] = []
    if body.side == "sell":
        sym_rows = [r for r in rows if str(r["symbol"]).upper() == sym]
        try:
            spl = {sym: await rd.splits(sym)} if sym_rows else {}
        except Exception:
            log.warning("split data unavailable for %s; selling with unadjusted history", sym)
            spl = {}
            warnings.append(f"splits_unavailable:{sym}")
        try:
            pos = L.positions(L.adjust_for_splits(L.to_trades(sym_rows), spl)).get(sym)
        except L.LedgerError:
            log.exception("ledger inconsistent for %s", sym)
            raise HTTPException(409, "Trade history inconsistent.")
        held = pos.qty if pos else 0.0
        if held + L.QTY_EPS < qty:
            raise HTTPException(400, f"ถือไม่พอที่จะขาย (ถืออยู่ {held:g})")
        realized = round((price - pos.avg_cost) * qty - fee, 2)
    elif qty * price + fee > float(acc["cash"]) + 1e-9:
        raise HTTPException(400, "เงินสดไม่พอ")
    try:
        res = await sb("POST", "rpc/stock_execute_trade", raw_error=True, json={
            "p_email": email, "p_symbol": sym, "p_side": body.side, "p_qty": qty, "p_price": price,
            "p_fee": fee, "p_realized_pnl": realized, "p_note": body.note, "p_quote_ts": quote_ts,
            "p_price_source": "finnhub_quote", "p_expected_last_id": last_id})
    except SbError as e:
        if "ledger_changed" in e.body:
            raise HTTPException(409, "Portfolio changed during submission; please retry.")
        if "insufficient_cash" in e.body:
            raise HTTPException(400, "เงินสดไม่พอ")
        log.error("trade rpc failed: %s", e)
        raise HTTPException(500, "Trade failed.")
    rd.invalidate(f"report:{email}")
    return {"ok": True, "price": price, "cash": (res or {}).get("cash"), "realized_pnl": realized,
            "trade": (res or {}).get("trade"), "warnings": warnings}


@router.post("/reset")
async def reset(email: str = Depends(get_current_email)):
    await _account(email)
    res = await sb("POST", "rpc/stock_reset_account", json={"p_email": email})
    rd.invalidate(f"report:{email}")
    return {"ok": True, "result": res}
