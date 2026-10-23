# ---- added imports ----
import logging
import math
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from . import ledger as L
from . import risk_data as rd

log = logging.getLogger("stocks.stock_book")
FEE_BPS = Decimal(os.getenv("STOCK_FEE_BPS", "0"))          # default 0 = same as today
FEE_MIN = Decimal(os.getenv("STOCK_FEE_MIN_USD", "0"))
MAX_QTY = 1_000_000


class TradeIn(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=12, pattern=r"^[A-Za-z0-9.\-]+$")
    side: str = Field(..., pattern="^(buy|sell)$")
    qty: float = Field(..., gt=0, le=MAX_QTY)
    price: float | None = None   # DEPRECATED: ignored — server prices every trade
    fee: float | None = None     # DEPRECATED: ignored — server computes fee
    note: str | None = Field(None, max_length=280)


def _fee(notional: float) -> float:
    if FEE_BPS <= 0 and FEE_MIN <= 0:
        return 0.0
    fee = max(Decimal(str(notional)) * FEE_BPS / Decimal(10000), FEE_MIN)
    return float(fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


async def _server_price(sym: str) -> tuple[float, str | None]:
    q = await get_quote(sym)
    # ⚠️ VERIFY against get_quote's real return shape (Finnhub /quote: c=price, t=unix ts)
    raw, ts = (q.get("price", q.get("c")), q.get("t") or q.get("timestamp")) if isinstance(q, dict) else (q, None)
    try:
        price = float(raw)
    except (TypeError, ValueError):
        price = 0.0
    if not math.isfinite(price) or price <= 0:
        raise HTTPException(503, "Live quote unavailable; trade rejected.")
    quote_ts = datetime.fromtimestamp(int(ts), timezone.utc).isoformat() if isinstance(ts, (int, float)) and ts > 0 else None
    return price, quote_ts


async def _trades(email: str, symbol: str | None = None) -> list[dict]:
    rows = await rd.active_trades(email)          # now excludes voided (reset) trades
    return [r for r in rows if symbol is None or r["symbol"] == symbol]


@router.post("/trade")
async def trade(body: TradeIn, email: str = Depends(current_email)):
    sym = norm(body.symbol)
    acc = await _account(email)
    rows = await _trades(email)
    last_id = max((int(r["id"]) for r in rows), default=0)
    price, quote_ts = await _server_price(sym)
    qty = round(float(body.qty), 6)
    if qty <= 0:
        raise HTTPException(400, "Quantity too small.")
    fee = _fee(qty * price)
    realized = None
    if body.side == "sell":
        sym_rows = [r for r in rows if r["symbol"] == sym]
        try:
            spl = {sym: await rd.splits(sym)} if sym_rows else {}
        except Exception:
            log.warning("split data unavailable for %s; sell blocked", sym)
            raise HTTPException(503, "Corporate-action data unavailable; sell temporarily blocked.")
        pos = L.positions(L.adjust_for_splits(L.to_trades(sym_rows), spl)).get(sym)
        held = pos.qty if pos else 0.0
        if held + L.QTY_EPS < qty:
            raise HTTPException(400, f"Insufficient shares (held {held:g}).")
        realized = round((price - pos.avg_cost) * qty - fee, 2)
    elif qty * price + fee > float(acc["cash"]) + 1e-9:
        raise HTTPException(400, "Insufficient cash.")
    try:
        res = await sb("POST", "rpc/stock_execute_trade", json={
            "p_email": email, "p_symbol": sym, "p_side": body.side, "p_qty": qty, "p_price": price,
            "p_fee": fee, "p_realized_pnl": realized, "p_note": body.note, "p_quote_ts": quote_ts,
            "p_price_source": "finnhub_quote", "p_expected_last_id": last_id})
    except Exception as e:                         # ⚠️ VERIFY sb() error message format
        msg = str(e)
        if "ledger_changed" in msg:
            raise HTTPException(409, "Portfolio changed during submission; please retry.")
        if "insufficient_cash" in msg:
            raise HTTPException(400, "Insufficient cash.")
        log.exception("trade rpc failed")
        raise HTTPException(500, "Trade failed.")
    rd.invalidate(f"report:{email}")
    return res


@router.post("/reset")
async def reset(email: str = Depends(current_email)):
    await _account(email)
    res = await sb("POST", "rpc/stock_reset_account", json={"p_email": email})
    rd.invalidate(f"report:{email}")
    return res
