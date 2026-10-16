import os

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
    if not take_quota("alpha", 25, 86400):
        raise RateLimited("alphavantage")
    data = await _get_json("https://www.alphavantage.co/query", {**params, "apikey": ALPHA_KEY})
    if "Note" in data or "Information" in data:  # Alpha ตอบ 200 แม้โดน limit
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


def _parse_movers(rows: list[dict]) -> list[dict]:
    out = []
    for x in rows:
        price, vol = float(x["price"]), int(x["volume"])
        if price < 5 or vol < 500_000:  # ตัดหุ้นราคาต่ำและวอลุ่มน้อยออก
            continue
        out.append({
            "symbol": x["ticker"],
            "price": price,
            "change": float(x["change_amount"]),
            "changePercent": float(x["change_percentage"].rstrip("%")),
            "volume": vol,
        })
    return out[:10]


async def top_movers() -> dict:
    d = await alpha(function="TOP_GAINERS_LOSERS")
    return {
        "gainers": _parse_movers(d.get("top_gainers", [])),
        "losers": _parse_movers(d.get("top_losers", [])),
        "mostActive": _parse_movers(d.get("most_actively_traded", [])),
        "updatedAt": d.get("last_updated"),
    }
