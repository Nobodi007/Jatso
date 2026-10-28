"""
Stock detail page endpoints (Yahoo Finance style)

GET /api/stocks/{symbol}/summary   -> ราคา + key stats + ข้อมูลบริษัท
GET /api/stocks/{symbol}/chart?range=1d|5d|1mo|6mo|ytd|1y|5y|max

แหล่งข้อมูล:
- ราคาสด / profile / metric / earnings : Finnhub (ผ่าน providers.finnhub ที่มีโควตาอยู่แล้ว)
- bid/ask, volume, target, description, pre/post, กราฟ intraday : yfinance (ผ่าน providers._yahoo)
"""
from __future__ import annotations

import asyncio
import math
import re
from datetime import date, datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query

from . import providers as p
from .cache import cached

router = APIRouter()

NY = ZoneInfo("America/New_York")
_SYM_RE = re.compile(r"^[A-Z0-9.\-^]{1,12}$")


# ---------------------------------------------------------------- helpers
def _norm(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if not _SYM_RE.match(s):
        raise HTTPException(400, "invalid_symbol")
    return s


async def _guard(aw):
    """แปลง error ของ provider เป็น HTTP error (เหมือน guard ใน router.py)"""
    try:
        return await aw
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        if type(e).__name__ == "RateLimited":
            raise HTTPException(503, "rate_limited") from e
        raise HTTPException(502, "provider_error") from e


async def _soft(aw):
    """ข้อมูลเสริม: ดึงไม่ได้ให้คืน None แทนที่จะทำทั้งหน้าพัง"""
    try:
        return await aw
    except Exception:  # noqa: BLE001
        return None


def _num(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _iso(ts):
    if ts in (None, 0, ""):
        return None
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return str(ts)


def _market_state_by_clock() -> str:
    n = datetime.now(NY)
    if n.weekday() >= 5:
        return "CLOSED"
    t = n.time()
    if dtime(4) <= t < dtime(9, 30):
        return "PRE"
    if dtime(9, 30) <= t < dtime(16):
        return "REGULAR"
    if dtime(16) <= t < dtime(20):
        return "POST"
    return "CLOSED"


# ---------------------------------------------------------------- yfinance (sync, รันใน thread ผ่าน p._yahoo)
def _yf_info_sync(symbol: str) -> dict:
    import yfinance as yf

    try:
        return yf.Ticker(p._yf_sym(symbol)).info or {}
    except Exception:  # noqa: BLE001
        return {}


def _yf_chart_sync(symbol: str, period: str, interval: str, prepost: bool) -> list[dict]:
    import yfinance as yf

    df = yf.Ticker(p._yf_sym(symbol)).history(
        period=period,
        interval=interval,
        prepost=prepost,
        auto_adjust=False,
        actions=False,
    )
    if df is None or df.empty:
        return []

    out: list[dict] = []
    for ts, row in df.iterrows():
        c = row.get("Close")
        if c is None or c != c:  # NaN
            continue
        v = row.get("Volume")
        ny = ts.tz_convert(NY) if ts.tzinfo else ts
        out.append(
            {
                "t": int(ts.timestamp() * 1000),
                "c": round(float(c), 4),
                "v": int(v) if v is not None and v == v else 0,
                "d": ny.strftime("%Y-%m-%d"),
            }
        )
    return out


async def _yahoo_call(fn, *args):
    """เรียกผ่าน p._yahoo (มี semaphore) ถ้าไม่มีให้ fallback เป็น to_thread"""
    yahoo = getattr(p, "_yahoo", None)
    if yahoo is not None:
        return await yahoo(fn, *args)
    return await asyncio.to_thread(fn, *args)


# ---------------------------------------------------------------- /summary
@router.get("/{symbol}/summary")
async def stock_summary(symbol: str):
    s = _norm(symbol)
    today = date.today()

    raw_q, prof, met, earn, info = await asyncio.gather(
        _guard(cached(f"quote:{s}", 15, lambda: p.finnhub("/quote", symbol=s))),
        _soft(cached(f"profile:{s}", 86400, lambda: p.finnhub("/stock/profile2", symbol=s))),
        _soft(cached(f"metric:{s}", 3600, lambda: p.finnhub("/stock/metric", symbol=s, metric="all"))),
        _soft(
            cached(
                f"earn:{s}",
                6 * 3600,
                lambda: p.finnhub(
                    "/calendar/earnings",
                    symbol=s,
                    **{"from": today.isoformat(), "to": (today + timedelta(days=120)).isoformat()},
                ),
            )
        ),
        _soft(cached(f"yfinfo:{s}", 600, lambda: _yahoo_call(_yf_info_sync, s))),
    )

    q = raw_q or {}
    prof = prof or {}
    info = info or {}
    m = (met or {}).get("metric") or {}

    # รองรับทั้งรูปแบบ raw ของ Finnhub (c, d, dp...) และแบบที่แปลงแล้ว
    price = _num(q.get("c", q.get("price")))
    if not price:
        raise HTTPException(404, "symbol_not_found")

    earn_list = (earn or {}).get("earningsCalendar") or []
    next_earn = min((e["date"] for e in earn_list if e.get("date")), default=None)

    mcap_m = _num(prof.get("marketCapitalization"))  # Finnhub หน่วย = ล้าน USD
    avg_m = _num(m.get("3MonthAverageTradingVolume")) or _num(m.get("10DayAverageTradingVolume"))  # ล้านหุ้น

    yf_state = info.get("marketState")
    market_state = yf_state if yf_state in {"PRE", "PREPRE", "REGULAR", "POST", "POSTPOST", "CLOSED"} else _market_state_by_clock()

    return {
        "symbol": s,
        "name": prof.get("name") or info.get("longName") or info.get("shortName") or s,
        "logo": prof.get("logo") or None,
        "exchange": prof.get("exchange") or info.get("fullExchangeName") or "",
        "currency": prof.get("currency") or info.get("currency") or "USD",
        "marketState": market_state,
        "time": _iso(q.get("t", q.get("timestamp"))),
        "price": price,
        "change": _num(q.get("d", q.get("change"))),
        "changePercent": _num(q.get("dp", q.get("changePercent"))),
        "preMarketPrice": _num(info.get("preMarketPrice")),
        "preMarketChange": _num(info.get("preMarketChange")),
        "preMarketChangePercent": _num(info.get("preMarketChangePercent")),
        "postMarketPrice": _num(info.get("postMarketPrice")),
        "postMarketChange": _num(info.get("postMarketChange")),
        "postMarketChangePercent": _num(info.get("postMarketChangePercent")),
        "previousClose": _num(q.get("pc", q.get("prevClose"))),
        "open": _num(q.get("o", q.get("open"))),
        "dayLow": _num(q.get("l", q.get("low"))),
        "dayHigh": _num(q.get("h", q.get("high"))),
        "bid": _num(info.get("bid")),
        "bidSize": _num(info.get("bidSize")),
        "ask": _num(info.get("ask")),
        "askSize": _num(info.get("askSize")),
        "fiftyTwoWeekLow": _num(m.get("52WeekLow")) or _num(info.get("fiftyTwoWeekLow")),
        "fiftyTwoWeekHigh": _num(m.get("52WeekHigh")) or _num(info.get("fiftyTwoWeekHigh")),
        "volume": _num(info.get("regularMarketVolume") or info.get("volume")),
        "avgVolume": avg_m * 1e6 if avg_m else _num(info.get("averageVolume")),
        "marketCap": mcap_m * 1e6 if mcap_m else _num(info.get("marketCap")),
        "beta": _num(m.get("beta")) or _num(info.get("beta")),
        "peRatio": _num(m.get("peTTM")) or _num(m.get("peBasicExclExtraTTM")) or _num(info.get("trailingPE")),
        "eps": _num(m.get("epsTTM")) or _num(m.get("epsBasicExclExtraItemsTTM")) or _num(info.get("trailingEps")),
        "earningsDate": next_earn,
        "dividendRate": _num(m.get("dividendPerShareAnnual")) or _num(info.get("dividendRate")),
        "dividendYield": _num(m.get("dividendYieldIndicatedAnnual")),  # หน่วย % แล้ว
        "targetPrice": _num(info.get("targetMeanPrice")),
        "sector": info.get("sector"),
        "industry": info.get("industry") or prof.get("finnhubIndustry"),
        "description": info.get("longBusinessSummary"),
        "website": prof.get("weburl") or info.get("website"),
        "employees": _num(info.get("fullTimeEmployees")),
    }


# ---------------------------------------------------------------- /chart
# range -> (yf period, interval, prepost, เก็บกี่วันล่าสุด)
_CHART = {
    "1d": ("5d", "5m", True, 1),
    "5d": ("1mo", "30m", False, 5),
    "1mo": ("1mo", "1d", False, None),
    "6mo": ("6mo", "1d", False, None),
    "ytd": ("ytd", "1d", False, None),
    "1y": ("1y", "1d", False, None),
    "5y": ("5y", "1wk", False, None),
    "max": ("max", "1mo", False, None),
}


@router.get("/{symbol}/chart")
async def stock_chart(symbol: str, rng: str = Query("1d", alias="range")):
    s = _norm(symbol)
    cfg = _CHART.get(rng)
    if not cfg:
        raise HTTPException(400, "invalid_range")

    period, interval, prepost, keep = cfg
    ttl = 60 if interval.endswith("m") else 900

    bars = await _guard(
        cached(
            f"chart:{s}:{rng}",
            ttl,
            lambda: _yahoo_call(_yf_chart_sync, s, period, interval, prepost),
        )
    )
    bars = bars or []

    if keep:
        days = sorted({b["d"] for b in bars})[-keep:]
        bars = [b for b in bars if b["d"] in days]

    return {
        "symbol": s,
        "range": rng,
        "bars": [{"t": b["t"], "c": b["c"], "v": b["v"]} for b in bars],
    }
