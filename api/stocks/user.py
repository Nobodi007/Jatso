import asyncio
import os
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .auth import current_email
from .db import sb
from .router import get_quote, norm

router = APIRouter(prefix="/api/stocks", tags=["stocks-user"])

D0 = Decimal("0")
MAX_WATCH = 30
MAX_ALERTS = 20
TICK_MAX_SYMBOLS = 40  # Finnhub ให้ประมาณ 60 ครั้ง/นาที จึงเว้นไว้ให้ส่วนอื่นใช้ด้วย
_http = httpx.AsyncClient(timeout=10)


def D(x) -> Decimal:
    return Decimal(str(x)) if x is not None else D0


def fl(x: Decimal, nd: int = 4) -> float:
    return float(round(x, nd))


def eq(v) -> str:
    return f"eq.{v}"


# =====================================================
# Watchlist
# =====================================================
class SymbolIn(BaseModel):
    symbol: str


@router.get("/me/watchlist")
async def watchlist(email: str = Depends(current_email)):
    rows = await sb("GET", "stock_watchlist", params={
        "select": "symbol", "user_email": eq(email), "order": "created_at.asc",
    }) or []
    syms = [r["symbol"] for r in rows]
    quotes = await asyncio.gather(*(get_quote(s) for s in syms), return_exceptions=True)
    return [
        q if isinstance(q, dict) else {"symbol": s, "error": "quote_unavailable"}
        for s, q in zip(syms, quotes)
    ]


@router.post("/me/watchlist", status_code=201)
async def watchlist_add(body: SymbolIn, email: str = Depends(current_email)):
    s = norm(body.symbol)
    rows = await sb("GET", "stock_watchlist", params={"select": "id", "user_email": eq(email)}) or []
    if len(rows) >= MAX_WATCH:
        raise HTTPException(400, "watchlist_full")
    await get_quote(s)  # ถ้าไม่มีหุ้นตัวนี้จะได้ 404
    await sb("POST", "stock_watchlist", json={"user_email": email, "symbol": s})
    return {"symbol": s}


@router.delete("/me/watchlist/{symbol}", status_code=204)
async def watchlist_remove(symbol: str, email: str = Depends(current_email)):
    await sb("DELETE", "stock_watchlist", params={"user_email": eq(email), "symbol": eq(norm(symbol))})


# =====================================================
# Portfolio (คิดต้นทุนแบบถัวเฉลี่ย หน่วย USD)
# =====================================================
class TxIn(BaseModel):
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    price: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    fee: Decimal = Field(default=D0, ge=0, max_digits=18, decimal_places=4)
    traded_at: datetime
    note: str | None = Field(default=None, max_length=500)


async def _txs(email: str, symbol: str | None = None) -> list[dict]:
    params = {"select": "*", "user_email": eq(email), "order": "traded_at.asc,id.asc"}
    if symbol:
        params["symbol"] = eq(symbol)
    return await sb("GET", "stock_transactions", params=params) or []


def _positions(txs: list[dict]) -> dict[str, dict]:
    pos: dict[str, dict] = {}
    for t in txs:
        p = pos.setdefault(t["symbol"], {"qty": D0, "cost": D0, "realized": D0, "fees": D0})
        q, price, fee = D(t["quantity"]), D(t["price"]), D(t["fee"])
        p["fees"] += fee
        if t["side"] == "BUY":
            p["qty"] += q
            p["cost"] += q * price + fee  # รวมค่าธรรมเนียมเข้าไปในต้นทุน
        else:
            q = min(q, p["qty"])
            if q <= 0:
                continue
            avg = p["cost"] / p["qty"]
            p["realized"] += q * price - fee - avg * q
            p["qty"] -= q
            p["cost"] -= avg * q
    return pos


@router.get("/me/transactions")
async def tx_list(symbol: str | None = None, email: str = Depends(current_email)):
    return await _txs(email, norm(symbol) if symbol else None)


@router.post("/me/transactions", status_code=201)
async def tx_add(body: TxIn, email: str = Depends(current_email)):
    s = norm(body.symbol)
    if body.side == "SELL":
        held = _positions(await _txs(email, s)).get(s, {}).get("qty", D0)
        if body.quantity > held:
            raise HTTPException(400, "sell_exceeds_holdings")
    else:
        await get_quote(s)

    traded_at = body.traded_at
    if traded_at.tzinfo is None:
        traded_at = traded_at.replace(tzinfo=timezone.utc)

    rows = await sb("POST", "stock_transactions", prefer="return=representation", json={
        "user_email": email, "symbol": s, "side": body.side,
        "quantity": str(body.quantity), "price": str(body.price), "fee": str(body.fee),
        "traded_at": traded_at.isoformat(), "note": body.note,
    })
    return rows[0]


@router.delete("/me/transactions/{tx_id}", status_code=204)
async def tx_delete(tx_id: int, email: str = Depends(current_email)):
    rows = await sb("DELETE", "stock_transactions", prefer="return=representation",
                    params={"id": eq(tx_id), "user_email": eq(email)})
    if not rows:
        raise HTTPException(404, "not_found")


@router.get("/me/portfolio")
async def portfolio(email: str = Depends(current_email)):
    pos = _positions(await _txs(email))
    open_syms = [s for s, p in pos.items() if p["qty"] > 0]
    quotes = await asyncio.gather(*(get_quote(s) for s in open_syms), return_exceptions=True)
    qmap = {s: q for s, q in zip(open_syms, quotes) if isinstance(q, dict)}

    holdings = []
    t_cost = t_value = t_day = t_realized = D0
    partial = False

    for s, p in pos.items():
        t_realized += p["realized"]
        if p["qty"] <= 0:
            continue
        item = {
            "symbol": s,
            "quantity": fl(p["qty"], 6),
            "avgCost": fl(p["cost"] / p["qty"]),
            "costBasis": fl(p["cost"], 2),
            "realizedPL": fl(p["realized"], 2),
        }
        q = qmap.get(s)
        if q:
            value = D(q["price"]) * p["qty"]
            upl = value - p["cost"]
            day = D(q["change"]) * p["qty"]
            item.update({
                "price": q["price"],
                "changePercent": q["changePercent"],
                "marketValue": fl(value, 2),
                "unrealizedPL": fl(upl, 2),
                "unrealizedPLPercent": fl(upl / p["cost"] * 100, 2) if p["cost"] else None,
                "dayPL": fl(day, 2),
            })
            t_cost += p["cost"]
            t_value += value
            t_day += day
        else:
            item["error"] = "quote_unavailable"
            partial = True
        holdings.append(item)

    for h in holdings:
        h["weightPercent"] = round(h["marketValue"] / float(t_value) * 100, 2) \
            if t_value and "marketValue" in h else None

    holdings.sort(key=lambda h: h.get("marketValue") or 0, reverse=True)
    upl = t_value - t_cost
    return {
        "currency": "USD",
        "partial": partial,  # true = มีบางตัวดึงราคาไม่ได้ ตัวเลขรวมจึงยังไม่ครบ
        "summary": {
            "marketValue": fl(t_value, 2),
            "costBasis": fl(t_cost, 2),
            "unrealizedPL": fl(upl, 2),
            "unrealizedPLPercent": fl(upl / t_cost * 100, 2) if t_cost else None,
            "realizedPL": fl(t_realized, 2),
            "dayPL": fl(t_day, 2),
        },
        "holdings": holdings,
    }


# =====================================================
# แจ้งเตือนราคา
# =====================================================
class AlertIn(BaseModel):
    symbol: str
    condition: Literal["above", "below"]
    target: Decimal = Field(gt=0, max_digits=18, decimal_places=4)


@router.get("/me/alerts")
async def alerts_list(email: str = Depends(current_email)):
    return await sb("GET", "stock_alerts", params={
        "select": "*", "user_email": eq(email), "order": "created_at.desc", "limit": "100",
    }) or []


@router.post("/me/alerts", status_code=201)
async def alerts_add(body: AlertIn, email: str = Depends(current_email)):
    s = norm(body.symbol)
    active = await sb("GET", "stock_alerts", params={
        "select": "id", "user_email": eq(email), "is_active": "eq.true",
    }) or []
    if len(active) >= MAX_ALERTS:
        raise HTTPException(400, "alerts_full")
    q = await get_quote(s)
    rows = await sb("POST", "stock_alerts", prefer="return=representation", json={
        "user_email": email, "symbol": s,
        "condition": body.condition, "target": str(body.target),
    })
    return {**rows[0], "currentPrice": q["price"]}


@router.delete("/me/alerts/{alert_id}", status_code=204)
async def alerts_delete(alert_id: int, email: str = Depends(current_email)):
    rows = await sb("DELETE", "stock_alerts", prefer="return=representation",
                    params={"id": eq(alert_id), "user_email": eq(email)})
    if not rows:
        raise HTTPException(404, "not_found")


# =====================================================
# ตั้งค่า Telegram ของแต่ละคน
# =====================================================
class SettingsIn(BaseModel):
    telegram_chat_id: str | None = Field(default=None, pattern=r"^-?\d{5,20}$")


async def send_telegram(chat_id: str | None, text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token or not chat_id:
        return False
    try:
        r = await _http.post(f"https://api.telegram.org/bot{token}/sendMessage",
                             json={"chat_id": chat_id, "text": text})
        return r.status_code == 200
    except httpx.HTTPError:
        return False


@router.get("/me/settings")
async def settings_get(email: str = Depends(current_email)):
    rows = await sb("GET", "stock_user_settings", params={"select": "*", "user_email": eq(email)}) or []
    return rows[0] if rows else {"user_email": email, "telegram_chat_id": None}


@router.put("/me/settings")
async def settings_put(body: SettingsIn, email: str = Depends(current_email)):
    if body.telegram_chat_id:
        ok = await send_telegram(body.telegram_chat_id, "เชื่อมต่อการแจ้งเตือนหุ้นสำเร็จ ✅")
        if not ok:
            raise HTTPException(400, "telegram_failed")  # ส่วนใหญ่เป็นเพราะยังไม่ได้กด /start กับบอท
    rows = await sb("POST", "stock_user_settings",
                    prefer="resolution=merge-duplicates,return=representation",
                    json={"user_email": email, "telegram_chat_id": body.telegram_chat_id,
                          "updated_at": datetime.now(timezone.utc).isoformat()})
    return rows[0]


# =====================================================
# Cron เรียก endpoint นี้ทุก 5 นาทีเพื่อเช็กแจ้งเตือน
# =====================================================
@router.post("/internal/alerts-tick", include_in_schema=False)
async def alerts_tick(x_tick_secret: str = Header(default="")):
    expected = os.getenv("STOCKS_TICK_SECRET") or os.getenv("BOTS_TICK_SECRET") or ""
    if not expected or not secrets.compare_digest(x_tick_secret, expected):
        raise HTTPException(403, "forbidden")

    alerts = await sb("GET", "stock_alerts", params={
        "select": "*", "is_active": "eq.true", "order": "created_at.asc", "limit": "1000",
    }) or []
    symbols = list(dict.fromkeys(a["symbol"] for a in alerts))[:TICK_MAX_SYMBOLS]
    quotes = await asyncio.gather(*(get_quote(s) for s in symbols), return_exceptions=True)
    prices = {s: D(q["price"]) for s, q in zip(symbols, quotes)
              if isinstance(q, dict) and q.get("price")}

    fired = []
    now = datetime.now(timezone.utc).isoformat()
    for a in alerts:
        price = prices.get(a["symbol"])
        if price is None:
            continue
        target = D(a["target"])
        hit = price >= target if a["condition"] == "above" else price <= target
        if not hit:
            continue
        # มีเงื่อนไข is_active=true ด้วย กันการแจ้งซ้ำถ้า cron 2 รอบทำงานทับกัน
        upd = await sb("PATCH", "stock_alerts", prefer="return=representation",
                       params={"id": eq(a["id"]), "is_active": "eq.true"},
                       json={"is_active": False, "triggered_at": now, "triggered_price": str(price)})
        if upd:
            fired.append({**a, "price": price})

    sent = 0
    if fired:
        emails = sorted({a["user_email"] for a in fired})
        in_list = ",".join(f'"{e}"' for e in emails)
        rows = await sb("GET", "stock_user_settings", params={
            "select": "user_email,telegram_chat_id", "user_email": f"in.({in_list})",
        }) or []
        chat = {r["user_email"]: r["telegram_chat_id"] for r in rows}
        for a in fired:
            word = "ขึ้นถึง" if a["condition"] == "above" else "ลงถึง"
            text = (f"🔔 {a['symbol']} {word}เป้าแล้ว\n"
                    f"ราคาตอนนี้ ${a['price']:.2f} (เป้า ${D(a['target']):.2f})")
            if await send_telegram(chat.get(a["user_email"]), text):
                sent += 1

    return {"checked": len(alerts), "symbols": len(symbols), "fired": len(fired), "sent": sent}
