import asyncio
import time
import re
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query

from . import providers as p
from .cache import ProviderError, RateLimited, cached

from .search_rank import clean_query, provider_query, rank_search


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
from .valuation_router import router as _valuation_router
router.include_router(_valuation_router)



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


# ===== แทนที่ฟังก์ชัน search เดิมใน router.py (ส่วน "# ---------- ค้นหา ----------") =====
# เพิ่ม import นี้ไว้ใกล้ ๆ import อื่นด้านบนไฟล์:
#   from .search_rank import clean_query, provider_query, rank_search

@router.get("/search")
async def search(q: str = Query(min_length=1, max_length=40), limit: int = Query(10, ge=1, le=20)):
    """ค้นหาหุ้น: ดึงผล Finnhub (cache 1 ชม.) แล้วจัดอันดับใหม่ในเครื่อง (ดู search_rank.py)
    ถ้า Finnhub ล่ม/โดน rate limit จะตอบจากรายการหุ้นยอดนิยมในเครื่องแทน ถ้าไม่มีผลเลยค่อยตอบ error เดิม"""
    q = clean_query(q)
    if not q:
        return []
    raw, err = None, None
    pq = provider_query(q)
    if pq:
        try:
            data = await cached(f"search:{pq.lower()}", 3600, lambda: p.finnhub("/search", q=pq))
            raw = data.get("result", []) if isinstance(data, dict) else []
        except RateLimited:
            err = HTTPException(503, "rate_limited")
        except ProviderError:
            err = HTTPException(502, "provider_error")
    out = rank_search(q, raw, limit)
    if not out and err:
        raise err
    return out


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
