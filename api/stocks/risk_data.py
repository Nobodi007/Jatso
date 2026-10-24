"""I/O for the stock Risk Center: Supabase reads + FMP fetches with in-process caching."""
from __future__ import annotations

import asyncio
import time
from datetime import date, timedelta
from typing import Any, Awaitable, Callable

from . import providers as p
from .cache import ProviderError, RateLimited
from .db import sb

SECTOR_TTL = 7 * 24 * 3600
BENCHMARK = "^GSPC"
LOOKBACK_DAYS = 400
MAX_SYMBOLS = 40
EOD_TTL, SPLIT_TTL, RF_TTL, FAIL_TTL = 6 * 3600, 24 * 3600, 12 * 3600, 300
MAX_KEYS = 300

_cache: dict[str, tuple[float, Any]] = {}
_failed: dict[str, float] = {}
_locks: dict[str, asyncio.Lock] = {}
_slots = asyncio.Semaphore(4)


async def memo(key: str, ttl: float, factory: Callable[[], Awaitable[Any]], *, provider_call: bool = True):
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    if provider_call and time.monotonic() - _failed.get(key, -1e9) < FAIL_TTL:
        raise ProviderError("recent provider failure (cooldown)")
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < ttl:
            return hit[1]
        try:
            if provider_call:
                async with _slots:
                    val = await factory()
            else:
                val = await factory()
        except (ProviderError, RateLimited):
            if provider_call:
                _failed[key] = time.monotonic()
            raise
        if len(_cache) >= MAX_KEYS:
            _cache.pop(min(_cache, key=lambda k: _cache[k][0]), None)
        _cache[key] = (time.monotonic(), val)
        return val


def invalidate(key: str) -> None:
    _cache.pop(key, None)


def window(today: date) -> tuple[date, date]:
    return today - timedelta(days=LOOKBACK_DAYS), today


async def eod(symbol: str, start: date, end: date) -> list[dict]:
    return await memo(f"eod:{symbol}:{start}:{end}", EOD_TTL, lambda: p.daily_history_range_any(symbol, start, end))


async def splits(symbol: str) -> list[tuple[date, float]]:
    rows = await memo(f"split:{symbol}", SPLIT_TTL, lambda: p.stock_splits_any(symbol))
    return [(date.fromisoformat(r["date"]), r["ratio"]) for r in rows]


async def sector(symbol: str) -> str | None:
    """Finnhub industry label (NOT GICS)."""
    d = await memo(f"sector:{symbol}", SECTOR_TTL, lambda: p.finnhub("/stock/profile2", symbol=symbol))
    return ((d or {}).get("finnhubIndustry") or None) if isinstance(d, dict) else None


async def risk_free(start: date, end: date) -> dict[date, float]:
    rows = await memo(f"rf3m:{start}:{end}", RF_TTL, lambda: p.treasury_3m(start, end))
    return {date.fromisoformat(r["date"]): r["rate"] for r in rows}


async def account(email: str) -> dict | None:
    rows = await sb("GET", "stock_accounts", params={"email": f"eq.{email}", "select": "*", "limit": "1"})
    return rows[0] if rows else None


async def active_trades(email: str) -> list[dict]:
    """User-scoped, excludes voided (reset) trades. Email must come from the verified JWT only."""
    out, offset = [], 0
    while True:
        rows = await sb("GET", "stock_trades", params={
            "email": f"eq.{email}", "voided_at": "is.null", "select": "*",
            "order": "ts.asc,id.asc", "limit": "1000", "offset": str(offset)}) or []
        out.extend(rows)
        if len(rows) < 1000:
            return out
        offset += 1000
