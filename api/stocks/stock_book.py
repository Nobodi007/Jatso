import asyncio
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .auth import current_email
from .db import sb
from .router import get_quote, norm

router = APIRouter(prefix="/api/stock-book", tags=["stock-book"])

OWNER_EMAILS = {e.strip().lower() for e in os.getenv("STOCK_OWNER_EMAILS", "").split(",") if e.strip()}
OWNER_CASH = 100_000_000.0
DEFAULT_CASH = 1_000_000.0


# ... TradeIn และ _positions ของเดิมวางไว้ตรงนี้ ...


async def _account(email: str) -> dict:
    params = {"select": "*", "email": f"eq.{email}", "limit": "1"}
    rows = await sb("GET", "stock_accounts", params=params)
    if rows:
        return rows[0]
    start = OWNER_CASH if email in OWNER_EMAILS else DEFAULT_CASH
    row = {"email": email, "initial_cash": start, "cash": start}
    try:
        await sb("POST", "stock_accounts", json=row)
    except HTTPException as e:
        if e.status_code != 409:  # มีคนสร้างพร้อมกัน
            raise
        row = (await sb("GET", "stock_accounts", params=params))[0]
    return row


async def _trades(email: str, symbol: str | None = None) -> list[dict]:
    out: list[dict] = []
    offset = 0
    while True:  # ดึงทีละ 1000 แถว กันโดนตัดเงียบ
        params = {
            "select": "*", "email": f"eq.{email}",
            "order": "ts.asc,id.asc", "limit": "1000", "offset": str(offset),
        }
        if symbol:
            params["symbol"] = f"eq.{symbol}"
        page = await sb("GET", "stock_trades", params=params) or []
        out += page
        if len(page) < 1000:
            return out
        offset += 1000


@router.get("/portfolio")
async def portfolio(email: str = Depends(current_email)):
    acc = await _account(email)
    pos = _positions(await _trades(email))
    syms = list(pos)
    quotes = await asyncio.gather(*(get_quote(s) for s in syms), return_exceptions=True)

    rows, mv_total, partial = [], 0.0, False
    for sym, q in zip(syms, quotes):
        p = pos[sym]
        ok = isinstance(q, dict)
        partial = partial or not ok
        last = float(q["price"]) if ok else p["avg"]  # ราคาไม่ได้ = ใช้ต้นทุนแทน และติดธง
        mv = last * p["qty"]
        mv_total += mv
        rows.append({
            "symbol": sym, "qty": p["qty"], "avg_cost": p["avg"], "last": last,
            "price_ok": ok, "market_value": mv,
            "unrealized_pnl": (last - p["avg"]) * p["qty"],
            "unrealized_pct": (last / p["avg"] - 1) * 100 if p["avg"] else 0,
        })

    cash, init = float(acc["cash"]), float(acc["initial_cash"])
    equity = cash + mv_total
    return {
        "initial_cash": init, "cash": cash, "market_value": mv_total,
        "equity": equity, "pnl": equity - init, "pnl_pct": (equity / init - 1) * 100,
        "partial": partial,
        "positions": sorted(rows, key=lambda r: -r["market_value"]),
    }


@router.get("/trades")
async def trades(email: str = Depends(current_email)):
    return list(reversed(await _trades(email)))


@router.post("/trade")
async def trade(body: TradeIn, email: str = Depends(current_email)):
    sym = norm(body.symbol)
    acc = await _account(email)
    price = body.price or float((await get_quote(sym))["price"])

    cash = float(acc["cash"])
    realized = None
    if body.side == "buy":
        cost = body.qty * price + body.fee
        if cost > cash:
            raise HTTPException(400, "เงินสดไม่พอ")
        cash -= cost
    else:
        held = _positions(await _trades(email, sym)).get(sym)
        if not held or body.qty > held["qty"] + 1e-9:
            raise HTTPException(400, "ถือไม่พอที่จะขาย")
        realized = (price - held["avg"]) * body.qty - body.fee
        cash += body.qty * price - body.fee

    await sb("POST", "stock_trades", json={
        "email": email, "symbol": sym, "side": body.side, "qty": body.qty,
        "price": price, "fee": body.fee, "realized_pnl": realized, "note": body.note,
    })
    await sb("PATCH", "stock_accounts", params={"email": f"eq.{email}"}, json={"cash": cash})
    return {"ok": True, "price": price, "cash": cash, "realized_pnl": realized}


@router.post("/reset")
async def reset(email: str = Depends(current_email)):
    acc = await _account(email)
    await sb("DELETE", "stock_trades", params={"email": f"eq.{email}"})
    await sb("PATCH", "stock_accounts", params={"email": f"eq.{email}"}, json={"cash": acc["initial_cash"]})
    return {"ok": True}
