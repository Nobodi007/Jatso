import asyncio
import time
import re
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query

from . import providers as p
from .cache import ProviderError, RateLimited, cached


router = APIRouter(prefix="/api/stocks", tags=["stocks"])
SYMBOL_RE = re.compile(r"^[A-Z][A-Z.\-]{0,9}$")
INDEX_ETFS = {"SPY": "S&P 500", "QQQ": "Nasdaq 100", "DIA": "Dow Jones"}
from .stock_heatmap import router as heatmap_router
router.include_router(heatmap_router)
from .public_market import router as public_market_router
router.include_router(public_market_router)
from .stock_detail import router as stock_detail_router
router.include_router(stock_detail_router)
from .stock_insights import router as stock_insights_router
router.include_router(stock_insights_router)



def norm(symbol: str) -> str:
    s = symbol.upper().strip()
    if not SYMBOL_RE.match(s):
        raise HTTPException(400, "invalid_symbol")
    return s


async def guard(coro):
    """แปลง error จาก API ภายนอกเป็นรหัสที่ frontend เอาไปแปลภาษาได้"""
    try:
        return await coro
    except RateLimited:
        raise HTTPException(503, "rate_limited")
    except ProviderError:
        raise HTTPException(502, "provider_error")


async def get_quote(s: str) -> dict:
    q = await guard(cached(f"quote:{s}", 15, lambda: p.finnhub("/quote", symbol=s)))
    if not q or (q.get("c") == 0 and q.get("t") == 0):
        raise HTTPException(404, "symbol_not_found")
    return {
        "symbol": s, "price": q["c"], "change": q["d"], "changePercent": q["dp"],
        "open": q["o"], "high": q["h"], "low": q["l"], "prevClose": q["pc"],
        "timestamp": q["t"],
    }


# ---------- ภาพรวมตลาด ----------
@router.get("/market/overview")
async def market_overview():
    quotes = await asyncio.gather(*(get_quote(s) for s in INDEX_ETFS))
    return [{**q, "name": INDEX_ETFS[q["symbol"]]} for q in quotes]


_movers_fail_until = 0.0


@router.get("/market/movers")
async def market_movers():
    global _movers_fail_until
    if time.time() < _movers_fail_until:
        raise HTTPException(503, "rate_limited")
    try:
        return await cached("movers", 12 * 3600, p.top_movers)
    except RateLimited:
        _movers_fail_until = time.time() + 1800  # พัก 30 นาที ไม่ยิง Alpha ซ้ำ
        raise HTTPException(503, "rate_limited")
    except ProviderError:
        raise HTTPException(502, "provider_error")


# ---------- ค้นหา ----------
@router.get("/search")
async def search(q: str = Query(min_length=1, max_length=20)):
    data = await guard(cached(f"search:{q.lower()}", 3600, lambda: p.finnhub("/search", q=q)))
    return [
        {"symbol": x["symbol"], "name": x["description"], "type": x["type"]}
        for x in data.get("result", [])
        if "." not in x["symbol"]
    ][:10]


# ---------- หุ้นรายตัว ----------
@router.get("/{symbol}/quote")
async def quote(symbol: str):
    return await get_quote(norm(symbol))


@router.get("/{symbol}/profile")
async def profile(symbol: str):
    s = norm(symbol)
    d = await guard(cached(f"profile:{s}", 86400, lambda: p.finnhub("/stock/profile2", symbol=s)))
    if not d:
        raise HTTPException(404, "symbol_not_found")
    return {
        "symbol": s, "name": d.get("name"), "logo": d.get("logo"),
        "industry": d.get("finnhubIndustry"), "exchange": d.get("exchange"),
        "marketCap": d.get("marketCapitalization"),  # หน่วยล้าน USD
        "ipo": d.get("ipo"), "website": d.get("weburl"),
    }


@router.get("/{symbol}/news")
async def news(symbol: str):
    s = norm(symbol)
    to = date.today()
    frm = to - timedelta(days=7)
    items = await guard(cached(
        f"news:{s}", 1800,
        lambda: p.finnhub("/company-news", symbol=s, **{"from": frm.isoformat(), "to": to.isoformat()}),
    ))
    return [
        {k: n.get(k) for k in ("id", "headline", "summary", "source", "url", "image", "datetime")}
        for n in items[:15]
    ]


@router.get("/{symbol}/history")
async def history(symbol: str):
    s = norm(symbol)
    return await guard(cached(f"hist:{s}", 6 * 3600, lambda: p.daily_history(s)))
