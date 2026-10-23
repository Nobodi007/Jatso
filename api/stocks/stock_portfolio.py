"""
Jatso / Nobodi - Stock Portfolio Calculator
===========================================

Read-only calculation helpers for US-stock positions sourced from public.stock_trades.

This module does NOT connect to Supabase, fetch market prices, execute orders, or modify data.
The caller must authenticate the user and pass only that user's rows into build_portfolio().
Prices are supplied by the caller (for example, from the existing stock-price provider).

Expected trade fields:
    email, symbol, side, qty, price, fee, realized_pnl, ts, id

Supported side values: buy / sell (case-insensitive).
Cost method: weighted-average cost. Fees are included in purchase cost and deducted from
sale proceeds. Monetary values are calculated in the currency used by the supplied prices
(typically USD for US stocks).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping


class PortfolioDataError(ValueError):
    """Raised when trade data is invalid or internally inconsistent."""


def _decimal(value: Any, field: str, *, default: str | None = None) -> Decimal:
    if value is None or value == "":
        if default is not None:
            return Decimal(default)
        raise PortfolioDataError(f"Missing required field: {field}")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise PortfolioDataError(f"Invalid numeric value for {field}: {value!r}") from None
    if not result.is_finite():
        raise PortfolioDataError(f"Non-finite numeric value for {field}")
    return result


def _side(value: Any) -> str:
    side = str(value or "").strip().lower()
    if side not in {"buy", "sell"}:
        raise PortfolioDataError(f"Unsupported side value: {value!r}; expected buy or sell")
    return side


def _trade_sort_key(row: Mapping[str, Any]) -> tuple[str, int]:
    ts = str(row.get("ts") or "")
    try:
        row_id = int(row.get("id") or 0)
    except (TypeError, ValueError):
        row_id = 0
    return ts, row_id


def build_portfolio(
    trades: Iterable[Mapping[str, Any]],
    latest_prices: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Calculate open positions from chronologically ordered or unordered trade rows.

    Args:
        trades: Rows already filtered to a single authenticated user's email.
        latest_prices: Mapping such as {"CRDO": 170.25}. Missing prices are allowed;
            market value and unrealized P&L are returned as None for those positions.

    Returns:
        JSON-serializable dictionary containing positions and portfolio totals.

    Raises:
        PortfolioDataError: invalid trades, missing required fields, or overselling.
    """
    rows = [dict(row) for row in trades]
    rows.sort(key=_trade_sort_key)

    states: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {"qty": Decimal("0"), "cost": Decimal("0"), "realized_pnl": Decimal("0")}
    )
    warnings: list[str] = []

    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            raise PortfolioDataError("Trade has an empty symbol")

        side = _side(row.get("side"))
        qty = _decimal(row.get("qty"), "qty")
        price = _decimal(row.get("price"), "price")
        fee = _decimal(row.get("fee"), "fee", default="0")

        if qty <= 0:
            raise PortfolioDataError(f"{symbol}: qty must be greater than zero")
        if price < 0 or fee < 0:
            raise PortfolioDataError(f"{symbol}: price and fee cannot be negative")

        state = states[symbol]
        if side == "buy":
            state["qty"] += qty
            state["cost"] += qty * price + fee
        else:
            if qty > state["qty"]:
                raise PortfolioDataError(
                    f"{symbol}: sell quantity ({qty}) exceeds available quantity ({state['qty']})"
                )
            average_cost = state["cost"] / state["qty"] if state["qty"] else Decimal("0")
            state["realized_pnl"] += qty * price - fee - qty * average_cost
            state["qty"] -= qty
            state["cost"] -= qty * average_cost
            if state["qty"] == 0:
                state["cost"] = Decimal("0")

    positions: list[dict[str, Any]] = []
    total_cost = Decimal("0")
    total_market_value = Decimal("0")
    total_unrealized = Decimal("0")
    all_prices_available = True

    normalized_prices: dict[str, Decimal] = {}
    for key, value in latest_prices.items():
        normalized_prices[str(key).strip().upper()] = _decimal(value, f"latest_prices[{key}]")

    for symbol in sorted(states):
        state = states[symbol]
        qty = state["qty"]
        if qty <= 0:
            continue

        cost = state["cost"]
        avg_cost = cost / qty
        market_price = normalized_prices.get(symbol)
        market_value = qty * market_price if market_price is not None else None
        unrealized = market_value - cost if market_value is not None else None
        unrealized_pct = (unrealized / cost * Decimal("100")) if unrealized is not None and cost > 0 else None

        total_cost += cost
        if market_value is None or unrealized is None:
            all_prices_available = False
        else:
            total_market_value += market_value
            total_unrealized += unrealized

        positions.append({
            "symbol": symbol,
            "quantity": float(qty),
            "average_cost": round(float(avg_cost), 6),
            "cost_basis": round(float(cost), 2),
            "latest_price": float(market_price) if market_price is not None else None,
            "market_value": round(float(market_value), 2) if market_value is not None else None,
            "unrealized_pnl": round(float(unrealized), 2) if unrealized is not None else None,
            "unrealized_pnl_pct": round(float(unrealized_pct), 4) if unrealized_pct is not None else None,
            "currency": "USD",
        })

    return {
        "method": "weighted_average_cost",
        "read_only": True,
        "positions": positions,
        "totals": {
            "open_positions": len(positions),
            "cost_basis": round(float(total_cost), 2),
            "market_value": round(float(total_market_value), 2) if all_prices_available else None,
            "unrealized_pnl": round(float(total_unrealized), 2) if all_prices_available else None,
            "all_latest_prices_available": all_prices_available,
            "currency": "USD",
        },
        "warnings": warnings,
    }


def summarize_buy_only_position(
    symbol: str,
    quantity: Any,
    purchase_price: Any,
    fee: Any = 0,
    latest_price: Any | None = None,
) -> dict[str, Any]:
    """Small helper for a single buy-only position; useful for quick tests."""
    symbol = str(symbol).strip().upper()
    qty = _decimal(quantity, "quantity")
    price = _decimal(purchase_price, "purchase_price")
    fee_value = _decimal(fee, "fee", default="0")
    if not symbol or qty <= 0 or price < 0 or fee_value < 0:
        raise PortfolioDataError("symbol must be set, quantity positive, and price/fee non-negative")

    cost = qty * price + fee_value
    result: dict[str, Any] = {
        "symbol": symbol,
        "quantity": float(qty),
        "average_cost": round(float(cost / qty), 6),
        "cost_basis": round(float(cost), 2),
        "latest_price": None,
        "market_value": None,
        "unrealized_pnl": None,
        "unrealized_pnl_pct": None,
        "currency": "USD",
    }
    if latest_price is not None:
        market_price = _decimal(latest_price, "latest_price")
        market_value = qty * market_price
        pnl = market_value - cost
        result.update({
            "latest_price": float(market_price),
            "market_value": round(float(market_value), 2),
            "unrealized_pnl": round(float(pnl), 2),
            "unrealized_pnl_pct": round(float(pnl / cost * Decimal("100")), 4) if cost else None,
        })
    return result


if __name__ == "__main__":
    # Safe local smoke tests; no external services or user data are accessed.
    p = summarize_buy_only_position("CRDO", 500, "162.29", 0, "170.00")
    assert p["cost_basis"] == 81145.0
    assert p["market_value"] == 85000.0
    assert p["unrealized_pnl"] == 3855.0

    sample = [
        {"id": 1, "symbol": "CRDO", "side": "buy", "qty": 500, "price": "162.29", "fee": 0, "ts": "2026-10-22T18:00:00Z"}
    ]
    portfolio = build_portfolio(sample, {"CRDO": "170.00"})
    assert portfolio["positions"][0]["quantity"] == 500.0
    assert portfolio["totals"]["unrealized_pnl"] == 3855.0
    print("stock_portfolio.py smoke tests: PASS")
