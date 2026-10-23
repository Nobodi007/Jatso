import os

import asyncio
from datetime import datetime, timezone

import logging
log = logging.getLogger("stocks.providers")

import httpx

from .cache import ProviderError, RateLimited, take_quota

FINNHUB_KEY = os.getenv("FINNHUB_KEY", "")
ALPHA_KEY = os.getenv("ALPHA_KEY", "")
FMP_KEY = os.getenv("FMP_KEY", "")

_client = httpx.AsyncClient(timeout=10)


async def _get_json(url: str, params: dict):
    try:
        resp = await _client.get(url, params=params)
    except httpx.HTTPError as e:
        raise ProviderError(str(e)) from e
    if resp.status_code == 429:
        raise RateLimited(url)
    if resp.status_code >= 400:
        raise ProviderError(f"{url} -> {resp.status_code}")
    return resp.json()


# ---------- Finnhub ----------
async def finnhub(path: str, **params):
    if not take_quota("finnhub", 55, 60):
        raise RateLimited("finnhub")
    return await _get_json(f"https://finnhub.io/api/v1{path}", {**params, "token": FINNHUB_KEY})


# ---------- Alpha Vantage ----------
async def alpha(**params):
    if not ALPHA_KEY:
        raise ProviderError("ALPHA_KEY not set")
    if not take_quota("alpha", 25, 86400):
        log.warning("alpha: local quota counter exhausted")
        raise RateLimited("alphavantage")
    data = await _get_json("https://www.alphavantage.co/query", {**params, "apikey": ALPHA_KEY})
    msg = data.get("Note") or data.get("Information")
    if msg:
        log.warning("alpha: %s", msg[:200])
        raise RateLimited("alphavantage")
    if "Error Message" in data:
        raise ProviderError(data["Error Message"])
    return data


async def daily_history(symbol: str) -> list[dict]:
    if not FMP_KEY:
        raise ProviderError("FMP_KEY not set")
    if not take_quota("fmp", 240, 86400):  # ใช้ชื่อเดียวกับ fundamentals.py จะได้นับโควต้ารวมกัน
        raise RateLimited("fmp")
    data = await _get_json(
        "https://financialmodelingprep.com/stable/historical-price-eod/full",
        {"symbol": symbol, "apikey": FMP_KEY},
    )
    if not isinstance(data, list):
        raise ProviderError(str(data)[:200])
    rows = [
        {"time": x["date"], "open": x["open"], "high": x["high"],
         "low": x["low"], "close": x["close"], "volume": int(x.get("volume") or 0)}
        for x in data[:120]
    ]
    return sorted(rows, key=lambda r: r["time"])


def _parse_fmp_movers(rows: list[dict]) -> list[dict]:
    out = []
    for x in rows or []:
        try:
            price = float(x["price"])
            if price < 5:  # ตัดหุ้นราคาต่ำ (penny stock) ออก
                continue
            out.append({
                "symbol": x["symbol"],
                "name": x.get("name"),
                "price": price,
                "change": float(x["change"]),
                "changePercent": float(x["changesPercentage"]),
                "volume": int(x.get("volume") or 0),
            })
        except (KeyError, ValueError, TypeError):
            continue
    return out[:10]


async def _fmp_list(path: str) -> list[dict]:
    if not FMP_KEY:
        raise ProviderError("FMP_KEY not set")
    if not take_quota("fmp", 240, 86400):
        raise RateLimited("fmp")
    data = await _get_json(f"https://financialmodelingprep.com/stable{path}", {"apikey": FMP_KEY})
    if not isinstance(data, list):
        raise ProviderError(str(data)[:200])
    return data


async def top_movers() -> dict:
    gainers, losers, active = await asyncio.gather(
        _fmp_list("/biggest-gainers"),
        _fmp_list("/biggest-losers"),
        _fmp_list("/most-actives"),
    )
    return {
        "gainers": _parse_fmp_movers(gainers),
        "losers": _parse_fmp_movers(losers),
        "mostActive": _parse_fmp_movers(active),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }

# ---- Risk Center additions (do not modify daily_history above; charts depend on it) ----
from datetime import date, timedelta

FMP_BASE = "https://financialmodelingprep.com/stable"

async def _fmp(path: str, **params):
    if not FMP_KEY:
        raise ProviderError("fmp key missing")
    if not take_quota("fmp", 240, 86400):          # shares the existing 'fmp' bucket
        raise RateLimited("fmp")
    data = await _get_json(f"{FMP_BASE}{path}", {**params, "apikey": FMP_KEY})
    if isinstance(data, dict) and ("Error Message" in data or "error" in data):
        raise ProviderError(f"fmp {path}: rejected (plan/permission)")
    return data

async def daily_history_range(symbol: str, start: date, end: date) -> list[dict]:
    """Split-adjusted (verify via probe), NOT dividend-adjusted EOD bars, ascending."""
    data = await _fmp("/historical-price-eod/full", symbol=symbol,
                      **{"from": start.isoformat(), "to": end.isoformat()})
    rows = data if isinstance(data, list) else (data or {}).get("historical", [])
    out = []
    for r in rows:
        try:
            out.append({"date": str(r["date"])[:10], "open": float(r["open"]), "high": float(r["high"]),
                        "low": float(r["low"]), "close": float(r["close"])})
        except (KeyError, TypeError, ValueError):
            continue
    out.sort(key=lambda r: r["date"])
    return out

async def stock_splits(symbol: str) -> list[dict]:
    data = await _fmp("/splits", symbol=symbol)
    out = []
    for r in data or []:
        try:
            num, den = float(r["numerator"]), float(r["denominator"])
            if num > 0 and den > 0:
                out.append({"date": str(r["date"])[:10], "ratio": num / den})
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(out, key=lambda r: r["date"])

async def treasury_3m(start: date, end: date) -> list[dict]:
    """3M Treasury yield as annual decimal. Chunked in 90-day windows."""
    out, cur = {}, start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=89), end)
        data = await _fmp("/treasury-rates", **{"from": cur.isoformat(), "to": chunk_end.isoformat()})
        for r in data or []:
            v = r.get("month3")
            if v is not None:
                out[str(r["date"])[:10]] = float(v) / 100.0
        cur = chunk_end + timedelta(days=1)
    return [{"date": d, "rate": out[d]} for d in sorted(out)]
