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
