"""
ระบบส่งคำสั่งซื้อขายหุ้น (แยกจากฝั่งคริปโตทั้งหมด)

ตอนนี้เป็น paper-trading engine: จับคู่ที่ราคา Finnhub, เก็บเงินสด/หุ้น/คำสั่งในฐานข้อมูล
ถ้าจะส่งเข้าโบรกเกอร์จริง ให้ทำ adapter แทนฟังก์ชัน `_execute_*` (ดูท้ายไฟล์)

ติดตั้ง:  app.include_router(stocks_trade.router)   # prefix = /api/stocks/trade
"""
import asyncio
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, time as dtime
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .router import get_quote, norm          # TODO: ปรับ path ให้ตรงกับไฟล์ router หุ้นเดิม
from .auth import current_user_id            # TODO: dependency ที่อ่าน Bearer token แล้วคืน user id (ไม่ผ่าน -> 401)

router = APIRouter(prefix="/api/stocks/trade", tags=["stocks-trade"])

DB_PATH = os.getenv("STOCKS_TRADE_DB", "stocks_trade.db")
START_CASH = float(os.getenv("PAPER_START_CASH", "100000"))
IGNORE_HOURS = os.getenv("PAPER_IGNORE_MARKET_HOURS") == "1"   # เปิดไว้ตอนเทสนอกเวลาตลาด
NY = ZoneInfo("America/New_York")


# ---------- DB ----------
@contextmanager
def db():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    try:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (user_id TEXT PRIMARY KEY, cash REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS positions (
                user_id TEXT, symbol TEXT, qty INTEGER NOT NULL, avg_cost REAL NOT NULL,
                PRIMARY KEY (user_id, symbol));
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, symbol TEXT NOT NULL,
                side TEXT NOT NULL, type TEXT NOT NULL, qty INTEGER NOT NULL, limit_price REAL,
                status TEXT NOT NULL, fill_price REAL, reason TEXT, created_at TEXT NOT NULL, filled_at TEXT);
            CREATE INDEX IF NOT EXISTS idx_orders_user ON orders (user_id, status);
            """
        )
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _ensure_account(c, uid) -> float:
    row = c.execute("SELECT cash FROM accounts WHERE user_id=?", (uid,)).fetchone()
    if row:
        return row["cash"]
    c.execute("INSERT INTO accounts (user_id, cash) VALUES (?, ?)", (uid, START_CASH))
    return START_CASH


def _order_dict(r) -> dict:
    return {
        "id": r["id"], "symbol": r["symbol"], "side": r["side"], "type": r["type"], "qty": r["qty"],
        "limitPrice": r["limit_price"], "status": r["status"], "fillPrice": r["fill_price"],
        "createdAt": r["created_at"], "filledAt": r["filled_at"], "reason": r["reason"],
    }


def market_is_open() -> bool:
    """จันทร์-ศุกร์ 09:30-16:00 เวลา New York (ยังไม่รวมวันหยุดตลาด)"""
    if IGNORE_HOURS:
        return True
    t = datetime.now(NY)
    return t.weekday() < 5 and dtime(9, 30) <= t.time() < dtime(16, 0)


# ---------- core: apply a fill ----------
def _fill(c, uid, order_id: int, side: str, symbol: str, qty: int, price: float) -> Optional[str]:
    """ตัดเงิน/หุ้นแล้วปิดคำสั่ง; คืนเหตุผลถ้าทำไม่ได้"""
    cash = _ensure_account(c, uid)
    pos = c.execute("SELECT qty, avg_cost FROM positions WHERE user_id=? AND symbol=?", (uid, symbol)).fetchone()

    if side == "buy":
        cost = price * qty
        if cost > cash + 1e-9:
            return "insufficient_cash"
        new_qty = (pos["qty"] if pos else 0) + qty
        new_avg = ((pos["avg_cost"] * pos["qty"] if pos else 0) + cost) / new_qty
        c.execute("UPDATE accounts SET cash = cash - ? WHERE user_id=?", (cost, uid))
        c.execute(
            "INSERT INTO positions (user_id, symbol, qty, avg_cost) VALUES (?,?,?,?) "
            "ON CONFLICT(user_id, symbol) DO UPDATE SET qty=excluded.qty, avg_cost=excluded.avg_cost",
            (uid, symbol, new_qty, new_avg),
        )
    else:
        if not pos or pos["qty"] < qty:
            return "insufficient_shares"
        c.execute("UPDATE accounts SET cash = cash + ? WHERE user_id=?", (price * qty, uid))
        left = pos["qty"] - qty
        if left == 0:
            c.execute("DELETE FROM positions WHERE user_id=? AND symbol=?", (uid, symbol))
        else:  # ขายบางส่วน ต้นทุนเฉลี่ยคงเดิม
            c.execute("UPDATE positions SET qty=? WHERE user_id=? AND symbol=?", (left, uid, symbol))

    c.execute(
        "UPDATE orders SET status='filled', fill_price=?, filled_at=? WHERE id=?", (price, _now(), order_id)
    )
    return None


def _reserved(c, uid, symbol: Optional[str] = None) -> tuple[float, int]:
    """เงินที่ถูกกันไว้สำหรับ Limit ซื้อ และจำนวนหุ้นที่ถูกกันไว้สำหรับ Limit ขาย"""
    buy = c.execute(
        "SELECT COALESCE(SUM(qty*limit_price),0) s FROM orders WHERE user_id=? AND status='open' AND side='buy'", (uid,)
    ).fetchone()["s"]
    sell = c.execute(
        "SELECT COALESCE(SUM(qty),0) s FROM orders WHERE user_id=? AND status='open' AND side='sell' AND symbol=?",
        (uid, symbol or ""),
    ).fetchone()["s"]
    return buy, sell


# ---------- จับคู่ Limit ที่ค้างอยู่ (เรียกแบบ lazy ทุกครั้งที่มีคนเปิดหน้า) ----------
async def match_open_orders(uid):
    if not market_is_open():
        return
    with db() as c:
        open_rows = c.execute("SELECT * FROM orders WHERE user_id=? AND status='open'", (uid,)).fetchall()
    if not open_rows:
        return
    symbols = {r["symbol"] for r in open_rows}
    got = await asyncio.gather(*(get_quote(s) for s in symbols), return_exceptions=True)
    prices = {s: g["price"] for s, g in zip(symbols, got) if isinstance(g, dict)}

    with db() as c:
        for r in open_rows:
            px = prices.get(r["symbol"])
            if px is None:
                continue
            hit = px <= r["limit_price"] if r["side"] == "buy" else px >= r["limit_price"]
            if not hit:
                continue
            why = _fill(c, uid, r["id"], r["side"], r["symbol"], r["qty"], px)
            if why:
                c.execute("UPDATE orders SET status='rejected', reason=? WHERE id=?", (why, r["id"]))


# ---------- schemas ----------
class OrderIn(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    type: Literal["market", "limit"]
    qty: int = Field(gt=0, le=1_000_000)
    limitPrice: Optional[float] = Field(default=None, gt=0)


# ---------- endpoints ----------
async def _positions_priced(uid) -> list[dict]:
    with db() as c:
        rows = c.execute("SELECT symbol, qty, avg_cost FROM positions WHERE user_id=? ORDER BY symbol", (uid,)).fetchall()
    got = await asyncio.gather(*(get_quote(r["symbol"]) for r in rows), return_exceptions=True)
    return [
        {"symbol": r["symbol"], "qty": r["qty"], "avgCost": r["avg_cost"],
         "price": g["price"] if isinstance(g, dict) else r["avg_cost"]}  # ดึงราคาไม่ได้ -> ใช้ต้นทุนไปก่อน
        for r, g in zip(rows, got)
    ]


@router.get("/account")
async def account(uid=Depends(current_user_id)):
    await match_open_orders(uid)
    with db() as c:
        cash = _ensure_account(c, uid)
    pos = await _positions_priced(uid)
    mv = sum(p["price"] * p["qty"] for p in pos)
    return {"cash": cash, "marketValue": mv, "equity": cash + mv}


@router.get("/positions")
async def positions(uid=Depends(current_user_id)):
    return await _positions_priced(uid)


@router.get("/orders")
async def orders(uid=Depends(current_user_id)):
    with db() as c:
        rows = c.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 100", (uid,)).fetchall()
    return [_order_dict(r) for r in rows]


@router.post("/orders")
async def place_order(body: OrderIn, uid=Depends(current_user_id)):
    s = norm(body.symbol)
    if body.type == "limit" and not body.limitPrice:
        raise HTTPException(400, "invalid_limit")
    quote = await get_quote(s)                       # await ก่อนเปิด transaction
    price = quote["price"]

    if body.type == "market" and not market_is_open():
        raise HTTPException(409, "market_closed")

    with db() as c:
        cash = _ensure_account(c, uid)
        res_cash, res_sh = _reserved(c, uid, s)
        if body.side == "buy":
            ref = body.limitPrice if body.type == "limit" else price
            if ref * body.qty > cash - res_cash + 1e-9:
                raise HTTPException(400, "insufficient_cash")
        else:
            row = c.execute("SELECT qty FROM positions WHERE user_id=? AND symbol=?", (uid, s)).fetchone()
            if (row["qty"] if row else 0) - res_sh < body.qty:
                raise HTTPException(400, "insufficient_shares")

        cur = c.execute(
            "INSERT INTO orders (user_id, symbol, side, type, qty, limit_price, status, created_at) "
            "VALUES (?,?,?,?,?,?, 'open', ?)",
            (uid, s, body.side, body.type, body.qty, body.limitPrice, _now()),
        )
        oid = cur.lastrowid

        # Market = จับคู่ทันที, Limit = จับคู่ทันทีถ้าราคาถึงแล้ว (และตลาดเปิด) ไม่งั้นรอ
        immediate = body.type == "market" or (
            market_is_open()
            and ((body.side == "buy" and price <= body.limitPrice) or (body.side == "sell" and price >= body.limitPrice))
        )
        if immediate:
            why = _fill(c, uid, oid, body.side, s, body.qty, price)
            if why:
                raise HTTPException(400, why)
        row = c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    return _order_dict(row)


@router.delete("/orders/{order_id}", status_code=204)
async def cancel_order(order_id: int, uid=Depends(current_user_id)):
    with db() as c:
        row = c.execute("SELECT status FROM orders WHERE id=? AND user_id=?", (order_id, uid)).fetchone()
        if not row:
            raise HTTPException(404, "not_found")
        if row["status"] != "open":
            raise HTTPException(409, "not_cancellable")
        c.execute("UPDATE orders SET status='cancelled' WHERE id=?", (order_id,))


# ---------- จุดเสียบโบรกเกอร์จริง ----------
# เมื่อได้บัญชีโบรกเกอร์ (เช่น Alpaca / Interactive Brokers) ให้เปลี่ยน:
#   1) place_order  -> ส่ง order ไปโบรกเกอร์แทนการเรียก _fill แล้วเก็บ broker_order_id
#   2) /account, /positions -> ดึงจากโบรกเกอร์แทนตารางในไฟล์นี้
#   3) match_open_orders -> เปลี่ยนเป็นรับ webhook/ polling สถานะจากโบรกเกอร์
# Frontend ไม่ต้องแก้ เพราะ contract ของ endpoint เหมือนเดิม
