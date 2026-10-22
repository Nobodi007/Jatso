import os
import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

# TODO: แก้ 2 บรรทัดนี้ให้ตรงของจริงใน server.py
import jwt  # PyJWT
from fastapi import Header
from supabase import create_client

_SB_KEY = (
    os.getenv("SUPABASE_KEY")
    or os.getenv("SUPABASE_SERVICE_KEY")
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
)
if not _SB_KEY:
    raise RuntimeError("ไม่เจอ Supabase key ใน env ตั้งชื่ออะไรไว้ใน Render ให้ใส่ชื่อนั้น")

supabase = create_client(os.environ["SUPABASE_URL"], _SB_KEY)


def get_current_email(authorization: str = Header(default="")) -> str:
    token = authorization.removeprefix("Bearer ").strip()
    if not token or token in ("null", "undefined"):
        raise HTTPException(401, "frontend ไม่ได้ส่ง token มา (getStocksToken คืนค่าว่าง)")
    try:
        data = jwt.decode(token, os.environ["AUTH_JWT_SECRET"], algorithms=["HS256"])
    except KeyError:
        raise HTTPException(401, "ไม่มี env AUTH_JWT_SECRET")
    except Exception as e:
        raise HTTPException(401, f"decode ไม่ผ่าน: {type(e).__name__}: {e}")
    email = data.get("email") or data.get("sub")
    if not email:
        raise HTTPException(401, f"ไม่มีอีเมลใน token (claims: {list(data.keys())})")
    return str(email).lower()

router = APIRouter(prefix="/api/stock-book", tags=["stock-book"])

OWNER_EMAILS = {e.strip().lower() for e in os.getenv("STOCK_OWNER_EMAILS", "").split(",") if e.strip()}
OWNER_CASH = 100_000_000.0
DEFAULT_CASH = 1_000_000.0
FINNHUB_KEY = os.getenv("FINNHUB_API_KEY", "")


class TradeIn(BaseModel):
    symbol: str
    side: str = Field(pattern="^(buy|sell)$")
    qty: float = Field(gt=0)
    price: float | None = Field(default=None, gt=0)  # ไม่ใส่ = ใช้ราคาตลาด
    fee: float = Field(default=0, ge=0)
    note: str | None = None


def _quote(sym: str) -> float | None:
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": sym, "token": FINNHUB_KEY},
            timeout=8,
        ).json()
        c = r.get("c")
        return float(c) if c else None
    except Exception:
        return None


def _account(email: str) -> dict:
    res = supabase.table("stock_accounts").select("*").eq("email", email).execute().data
    if res:
        return res[0]
    start = OWNER_CASH if email.lower() in OWNER_EMAILS else DEFAULT_CASH
    row = {"email": email, "initial_cash": start, "cash": start}
    supabase.table("stock_accounts").insert(row).execute()
    return row


def _trades(email: str, symbol: str | None = None) -> list[dict]:
    q = supabase.table("stock_trades").select("*").eq("email", email)
    if symbol:
        q = q.eq("symbol", symbol)
    return q.order("ts").order("id").execute().data


def _positions(trades: list[dict]) -> dict[str, dict]:
    pos: dict[str, dict] = {}
    for t in trades:
        p = pos.setdefault(t["symbol"], {"qty": 0.0, "avg": 0.0})
        q, px = float(t["qty"]), float(t["price"])
        if t["side"] == "buy":
            total = p["qty"] * p["avg"] + q * px + float(t["fee"])
            p["qty"] += q
            p["avg"] = total / p["qty"]
        else:
            p["qty"] -= q
            if p["qty"] <= 1e-9:
                p["qty"], p["avg"] = 0.0, 0.0
    return {s: p for s, p in pos.items() if p["qty"] > 0}


@router.get("/portfolio")
def portfolio(email: str = Depends(get_current_email)):
    acc = _account(email)
    pos = _positions(_trades(email))
    rows, mv_total = [], 0.0
    for sym, p in pos.items():
        last = _quote(sym) or p["avg"]
        mv = last * p["qty"]
        mv_total += mv
        rows.append({
            "symbol": sym, "qty": p["qty"], "avg_cost": p["avg"], "last": last,
            "market_value": mv,
            "unrealized_pnl": (last - p["avg"]) * p["qty"],
            "unrealized_pct": (last / p["avg"] - 1) * 100 if p["avg"] else 0,
        })
    cash = float(acc["cash"])
    equity = cash + mv_total
    init = float(acc["initial_cash"])
    return {
        "initial_cash": init, "cash": cash, "market_value": mv_total,
        "equity": equity, "pnl": equity - init, "pnl_pct": (equity / init - 1) * 100,
        "positions": sorted(rows, key=lambda r: -r["market_value"]),
    }


@router.get("/trades")
def trades(email: str = Depends(get_current_email)):
    return list(reversed(_trades(email)))


@router.post("/trade")
def trade(body: TradeIn, email: str = Depends(get_current_email)):
    sym = body.symbol.strip().upper()
    acc = _account(email)
    price = body.price or _quote(sym)
    if not price:
        raise HTTPException(400, f"ดึงราคา {sym} ไม่ได้ ใส่ราคาเองได้")

    cash = float(acc["cash"])
    realized = None
    if body.side == "buy":
        cost = body.qty * price + body.fee
        if cost > cash:
            raise HTTPException(400, "เงินสดไม่พอ")
        cash -= cost
    else:
        held = _positions(_trades(email, sym)).get(sym)
        if not held or body.qty > held["qty"] + 1e-9:
            raise HTTPException(400, "ถือไม่พอที่จะขาย")
        realized = (price - held["avg"]) * body.qty - body.fee
        cash += body.qty * price - body.fee

    supabase.table("stock_trades").insert({
        "email": email, "symbol": sym, "side": body.side, "qty": body.qty,
        "price": price, "fee": body.fee, "realized_pnl": realized, "note": body.note,
    }).execute()
    supabase.table("stock_accounts").update({"cash": cash}).eq("email", email).execute()
    return {"ok": True, "price": price, "cash": cash, "realized_pnl": realized}


@router.post("/reset")
def reset(email: str = Depends(get_current_email)):
    acc = _account(email)
    supabase.table("stock_trades").delete().eq("email", email).execute()
    supabase.table("stock_accounts").update({"cash": acc["initial_cash"]}).eq("email", email).execute()
    return {"ok": True}
