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


class PlanRestricted(ProviderError):
    """Provider refused: symbol/endpoint is outside our subscription."""


async def _get_json(url: str, params: dict):
    try:
        resp = await _client.get(url, params=params)
    except httpx.HTTPError as e:
        raise ProviderError(type(e).__name__) from e      # never echo the URL (it may carry an api key)
    if resp.status_code == 429:
        raise RateLimited(url)
    head = resp.text[:300].lower()
    if resp.status_code >= 400:
        if resp.status_code in (402, 403) or "subscription" in head:
            raise PlanRestricted(f"{url} -> {resp.status_code}")
        raise ProviderError(f"{url} -> {resp.status_code}")
    try:
        return resp.json()
    except ValueError:
        if "subscription" in head or head.startswith("premium"):
            raise PlanRestricted(f"{url} -> restricted")
        raise ProviderError(f"{url} -> non-JSON response")


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


# ---------- Yahoo Finance fallback (UNOFFICIAL; used only when FMP refuses/fails) ----------
import math
import time as _time
from datetime import time as _dtime
from zoneinfo import ZoneInfo

_NY = ZoneInfo("America/New_York")
_yf_sem = asyncio.Semaphore(2)
_fmp_denied: dict[str, float] = {}        # symbol -> time FMP said "not in plan"
_DENY_TTL = 24 * 3600


def _fmp_skipped(symbol: str) -> bool:
    t = _fmp_denied.get(symbol)
    return t is not None and _time.time() - t < _DENY_TTL


def _yf_sym(symbol: str) -> str:
    return symbol if symbol.startswith("^") else symbol.replace(".", "-")


def _yf_history_sync(symbol: str, start: date, end: date) -> list[dict]:
    import yfinance as yf
    df = yf.Ticker(_yf_sym(symbol)).history(
        start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
        auto_adjust=False, actions=False)                      # Close = split-adjusted, not dividend-adjusted
    now = datetime.now(_NY)
    out = []
    for ts, r in df.iterrows():
        try:
            o, h, l, c = (float(r[k]) for k in ("Open", "High", "Low", "Close"))
        except (KeyError, TypeError, ValueError):
            continue
        if not all(math.isfinite(x) for x in (o, h, l, c)) or c <= 0:
            continue
        d = ts.date()
        if d == now.date() and now.time() < _dtime(16, 15):    # drop today's unfinished bar
            continue
        out.append({"date": d.isoformat(), "open": o, "high": h, "low": l, "close": c, "src": "yahoo"})
    out.sort(key=lambda r: r["date"])
    return out


def _yf_splits_sync(symbol: str) -> list[dict]:
    import yfinance as yf
    df = yf.Ticker(_yf_sym(symbol)).history(period="max", interval="1d", auto_adjust=False, actions=True)
    if df is None or df.empty:
        raise ProviderError("yahoo: empty history")            # failure != "no splits"
    out = []
    col = df["Stock Splits"] if "Stock Splits" in df.columns else []
    for ts, ratio in (col.items() if len(col) else []):
        try:
            r = float(ratio)
        except (TypeError, ValueError):
            continue
        if r > 0 and math.isfinite(r) and r != 1.0:
            out.append({"date": ts.date().isoformat(), "ratio": r})
    return sorted(out, key=lambda r: r["date"])


async def _yahoo(fn, *args):
    async with _yf_sem:
        try:
            return await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout=25)
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"yahoo: {type(e).__name__}") from e


async def daily_history_range_any(symbol: str, start: date, end: date) -> list[dict]:
    """FMP first; Yahoo only if FMP refuses/fails/returns nothing. Rows carry src='fmp'|'yahoo'."""
    if not _fmp_skipped(symbol):
        try:
            rows = await daily_history_range(symbol, start, end)
            if rows:
                for r in rows:
                    r["src"] = "fmp"
                return rows
        except PlanRestricted:
            _fmp_denied[symbol] = _time.time()
        except ProviderError as e:                              # includes RateLimited
            log.info("fmp eod failed for %s (%s); trying yahoo", symbol, type(e).__name__)
    return await _yahoo(_yf_history_sync, symbol, start, end)


async def stock_splits_any(symbol: str) -> list[dict]:
    if not _fmp_skipped(symbol):
        try:
            return await stock_splits(symbol)
        except PlanRestricted:
            _fmp_denied[symbol] = _time.time()
        except ProviderError as e:
            log.info("fmp splits failed for %s (%s); trying yahoo", symbol, type(e).__name__)
    return await _yahoo(_yf_splits_sync, symbol)
