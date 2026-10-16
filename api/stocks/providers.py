import os

import httpx

from .cache import ProviderError, RateLimited, take_quota

FINNHUB_KEY = os.getenv("FINNHUB_KEY", "")
ALPHA_KEY = os.getenv("ALPHA_KEY", "")

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
    data = await alpha(function="TIME_SERIES_DAILY", symbol=symbol, outputsize="compact")
    series = data.get("Time Series (Daily)", {})
    return [
        {
            "time": d,
            "open": float(v["1. open"]),
            "high": float(v["2. high"]),
            "low": float(v["3. low"]),
            "close": float(v["4. close"]),
            "volume": int(v["5. volume"]),
        }
        for d, v in sorted(series.items())
    ]


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
