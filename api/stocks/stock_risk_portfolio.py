"""
Jatso / Nobodi - Stock Risk Portfolio API (standalone router)
============================================================

Read-only endpoint for the existing public.stock_trades table.
Does not place orders, insert/update/delete rows, or change existing routes.

After review, include this router in api/server.py:
    from api.stocks.stock_risk_portfolio import router as stock_risk_portfolio_router
    app.include_router(stock_risk_portfolio_router)

Do not wire it into production until tested in a local/staging environment.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from .auth import current_email
from .db import sb
from .router import get_quote

router = APIRouter(prefix="/api/stocks/risk", tags=["stock-risk"])

D0 = Decimal("0")


def _d(value: Any, field: str, default: str | None = None) -> Decimal:
    if value is None or value == "":
        if default is not None:
            return Decimal(default)
        raise HTTPException(502, f"invalid_trade_data:{field}")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(502, f"invalid_trade_data:{field}") from None
    if not result.is_finite():
        raise HTTPException(502, f"invalid_trade_data:{field}")
    return result


def _side(value: Any) -> str:
    side = str(value or "").strip().lower()
    if side not in {"buy", "sell"}:
        raise HTTPException(502, "invalid_trade_data:side")
    return side


def _build_positions(trades: list[dict]) -> dict[str, dict[str, Decimal]]:
    """Build positions with weighted-average cost, including purchase fees in basis."""
    positions: dict[str, dict[str, Decimal]] = {}

    def trade_key(row: dict) -> tuple[str, int]:
        try:
            row_id = int(row.get("id") or 0)
        except (TypeError, ValueError):
            row_id = 0
        return str(row.get("ts") or ""), row_id

    for trade in sorted(trades, key=trade_key):
        symbol = str(trade.get("symbol") or "").strip().upper()
        if not symbol:
            raise HTTPException(502, "invalid_trade_data:symbol")

        side = _side(trade.get("side"))
        qty = _d(trade.get("qty"), "qty")
        price = _d(trade.get("price"), "price")
        fee = _d(trade.get("fee"), "fee", "0")

        if qty <= 0 or price < 0 or fee < 0:
            raise HTTPException(502, "invalid_trade_data:negative_or_zero_value")

        p = positions.setdefault(symbol, {
            "qty": D0, "cost": D0, "realized": D0, "fees": D0,
        })
        p["fees"] += fee

        if side == "buy":
            p["qty"] += qty
            p["cost"] += qty * price + fee
        else:
            if qty > p["qty"]:
                raise HTTPException(409, f"trade_history_inconsistent:{symbol}:sell_exceeds_holdings")
            avg_cost = p["cost"] / p["qty"] if p["qty"] else D0
            p["realized"] += qty * price - fee - qty * avg_cost
            p["qty"] -= qty
            p["cost"] -= qty * avg_cost
            if p["qty"] == 0:
                p["cost"] = D0

    return positions


@router.get("/portfolio")
async def stock_risk_portfolio(email: str = Depends(current_email)):
    """
    Return read-only holdings and current unrealized P&L for the authenticated user.
    Supabase service-role calls must always include the user's email filter.
    """
    trades = await sb(
        "GET",
        "stock_trades",
        params={
            "select": "id,email,symbol,side,qty,price,fee,realized_pnl,ts",
            "email": f"eq.{email}",
            "order": "ts.asc,id.asc",
            "limit": "5000",
        },
    ) or []

    # Defensive check: do not calculate or return rows if the DB response crosses users.
    if any(str(row.get("email") or "").strip().lower() != email for row in trades):
        raise HTTPException(502, "user_data_isolation_check_failed")

    positions = _build_positions(trades)
    open_symbols = [symbol for symbol, p in positions.items() if p["qty"] > 0]

    # Reuse the existing quote implementation and provider/cache instead of adding a new API key.
    import asyncio
    quotes = await asyncio.gather(
        *(get_quote(symbol) for symbol in open_symbols),
        return_exceptions=True,
    )
    quote_by_symbol = {
        symbol: quote
        for symbol, quote in zip(open_symbols, quotes)
        if isinstance(quote, dict)
    }

    holdings = []
    total_cost = D0
    total_market_value = D0
    total_unrealized = D0
    partial = False

    for symbol in sorted(open_symbols):
        p = positions[symbol]
        qty, cost = p["qty"], p["cost"]
        avg_cost = cost / qty if qty else D0
        quote = quote_by_symbol.get(symbol)

        item = {
            "symbol": symbol,
            "quantity": float(qty),
            "averageCost": round(float(avg_cost), 6),
            "costBasis": round(float(cost), 2),
            "realizedPL": round(float(p["realized"]), 2),
            "price": None,
            "marketValue": None,
            "unrealizedPL": None,
            "unrealizedPLPercent": None,
            "changePercent": None,
            "priceStatus": "unavailable",
        }

        total_cost += cost
        if quote is None:
            partial = True
        else:
            price = _d(quote.get("price"), "quote.price")
            market_value = qty * price
            unrealized = market_value - cost
            item.update({
                "price": float(price),
                "marketValue": round(float(market_value), 2),
                "unrealizedPL": round(float(unrealized), 2),
                "unrealizedPLPercent": round(float(unrealized / cost * 100), 2) if cost else None,
                "changePercent": quote.get("changePercent"),
                "priceStatus": "available",
            })
            total_market_value += market_value
            total_unrealized += unrealized

        holdings.append(item)

    if total_market_value > 0:
        for item in holdings:
            if item["marketValue"] is not None:
                item["weightPercent"] = round(item["marketValue"] / float(total_market_value) * 100, 2)
            else:
                item["weightPercent"] = None
    else:
        for item in holdings:
            item["weightPercent"] = None

    holdings.sort(key=lambda item: item["marketValue"] or 0, reverse=True)

    # If any quote is missing, totals that depend on current market value are intentionally null.
    return {
        "source": "stock_trades",
        "currency": "USD",
        "readOnly": True,
        "partial": partial,
        "priceMethod": "existing_stock_quote_provider",
        "costMethod": "weighted_average_cost",
        "summary": {
            "tradeRows": len(trades),
            "openPositions": len(holdings),
            "costBasis": round(float(total_cost), 2),
            "marketValue": None if partial else round(float(total_market_value), 2),
            "unrealizedPL": None if partial else round(float(total_unrealized), 2),
            "unrealizedPLPercent": (
                round(float(total_unrealized / total_cost * 100), 2)
                if not partial and total_cost else None
            ),
            "realizedPLFromTradeHistory": round(
                sum(float(p["realized"]) for p in positions.values()), 2
            ),
        },
        "holdings": holdings,
        "warnings": (
            ["บางหุ้นดึงราคาไม่ได้ ตัวเลขมูลค่าตลาดและกำไร/ขาดทุนรวมจึงแสดงเป็น null เพื่อป้องกันยอดรวมคลาดเคลื่อน"]
            if partial else []
        ),
    }
