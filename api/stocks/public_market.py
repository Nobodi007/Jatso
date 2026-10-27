"""ตารางตลาดหุ้นสหรัฐแบบสาธารณะ (ไม่ต้องล็อกอิน) สำหรับหน้า landing

หลักการ (กันโควต้า + กัน egress):
- ใช้รายชื่อหุ้นตายตัวในโค้ด ไม่รับ symbol จากผู้ใช้ จึงกินโควต้าได้ไม่เกินที่คำนวณไว้
- ราคา: ดึงทั้งตารางทีเดียวฝั่งเซิร์ฟเวอร์ แล้ว cache ก้อนเดียว 90 วินาที ผู้เข้าชมกี่คนก็ใช้ก้อนเดียวกัน
  (กรณีแย่สุด = หุ้น 20 ตัว / 90 วินาที ~ 13 ครั้ง/นาที จากโควต้า Finnhub 55 ครั้ง/นาทีที่แชร์กับในแอป)
- กราฟ 7 วัน: แยก endpoint และ cache รายตัว 24 ชม. (FMP ~20 ครั้ง/วัน จากโควต้า 240 ที่แชร์กับหน้างบการเงิน)
- ไม่แตะ Supabase เลย: ทุกอย่างอยู่ในหน่วยความจำของเซิร์ฟเวอร์ (ถ้า Render หลับแล้วตื่น cache จะหายและดึงใหม่)
"""
import asyncio
import logging
import re
import time

from fastapi import APIRouter, HTTPException, Query, Response

from . import providers as p
from .cache import ProviderError, RateLimited, cached, take_quota

log = logging.getLogger("stocks.public_market")

router = APIRouter(prefix="/public/market", tags=["stocks-public"])

# (symbol, ชื่อบริษัท, กลุ่ม) / กลุ่ม: tech, comm, consumer, fin, health, energy
UNIVERSE: list[tuple[str, str, str]] = [
    ("NVDA", "NVIDIA", "tech"),
    ("AAPL", "Apple", "tech"),
    ("MSFT", "Microsoft", "tech"),
    ("GOOGL", "Alphabet", "comm"),
    ("AMZN", "Amazon", "consumer"),
    ("META", "Meta Platforms", "comm"),
    ("TSLA", "Tesla", "consumer"),
    ("AVGO", "Broadcom", "tech"),
    ("NFLX", "Netflix", "comm"),
    ("AMD", "AMD", "tech"),
    ("JPM", "JPMorgan Chase", "fin"),
    ("V", "Visa", "fin"),
    ("KO", "Coca-Cola", "consumer"),
    ("DIS", "Walt Disney", "comm"),
    ("COST", "Costco", "consumer"),
    ("WMT", "Walmart", "consumer"),
    ("LLY", "Eli Lilly", "health"),
    ("XOM", "Exxon Mobil", "energy"),
    ("MCD", "McDonald's", "consumer"),
    ("NKE", "Nike", "consumer"),
]

QUOTES_TTL = 90          # วินาที
SPARK_TTL = 24 * 3600    # 24 ชม.
SPARK_DAYS = 7           # จำนวนวันทำการล่าสุดที่โชว์
SPARK_RETRY_AFTER = 1800  # ตัวที่ดึงพลาด พักไว้ 30 นาทีก่อนลองใหม่ (กันยิงซ้ำตอน provider พัง)

_spark_fail_until: dict[str, float] = {}


async def _fetch_quote(sym: str):
    q = await p.finnhub("/quote", symbol=sym)
    # Finnhub คืน c=0,t=0 เมื่อไม่รู้จัก symbol
    if not q or (q.get("c") == 0 and q.get("t") == 0):
        return None
    return q


async def _build_table() -> dict:
    results = await asyncio.gather(*(_fetch_quote(s) for s, _, _ in UNIVERSE), return_exceptions=True)
    rows = []
    for (sym, name, sector), r in zip(UNIVERSE, results):
        if r is None:
            continue
        if isinstance(r, BaseException):
            if not isinstance(r, ProviderError):
                log.warning("public_market quote %s failed: %s", sym, type(r).__name__)
            continue
        rows.append({
            "symbol": sym,
            "name": name,
            "sector": sector,
            "price": r.get("c"),
            "change": r.get("d"),
            "changePercent": r.get("dp"),
            "high": r.get("h"),
            "low": r.get("l"),
            "prevClose": r.get("pc"),
            "timestamp": r.get("t"),
        })
    if not rows:
        # ให้ cached() คืนค่า stale เดิมถ้ามี ไม่งั้นโยนต่อให้ endpoint แปลงเป็น 5xx
        raise ProviderError("no quotes")
    stamps = [x["timestamp"] for x in rows if x.get("timestamp")]
    return {
        "updatedAt": int(time.time()),
        "asOf": max(stamps) if stamps else None,  # เวลาของราคาล่าสุด (วินาที unix) ใช้โชว์ "ราคาปิดล่าสุด" ตอนตลาดปิด
        "rows": rows,
    }


@router.get("")
async def public_market_table(response: Response):
    try:
        data = await cached("pubmkt:table", QUOTES_TTL, _build_table)
    except RateLimited:
        raise HTTPException(503, "rate_limited")
    except ProviderError:
        raise HTTPException(502, "provider_error")
    response.headers["Cache-Control"] = "public, max-age=30"
    return data


async def _spark_one(sym: str):
    if _spark_fail_until.get(sym, 0) > time.time():
        return None

    async def fetch():
        rows = await p.daily_history(sym)
        closes = [round(float(r["close"]), 2) for r in rows[-SPARK_DAYS:] if r.get("close") is not None]
        if len(closes) < 2:
            raise ProviderError("not enough history")
        return closes

    try:
        return await cached(f"pubspark:{sym}", SPARK_TTL, fetch)
    except ProviderError:
        _spark_fail_until[sym] = time.time() + SPARK_RETRY_AFTER
        return None


@router.get("/sparks")
async def public_market_sparks(response: Response):
    sem = asyncio.Semaphore(4)  # ตอน cache ว่าง อย่ายิง FMP พร้อมกันทั้ง 20 ตัว

    async def one(sym: str):
        async with sem:
            return sym, await _spark_one(sym)

    pairs = await asyncio.gather(*(one(s) for s, _, _ in UNIVERSE))
    sparks = {sym: closes for sym, closes in pairs if closes}
    # ได้ครบหรือเกือบครบค่อยให้เบราว์เซอร์ cache ยาว ถ้าขาดเยอะให้ลองใหม่เร็วขึ้น
    response.headers["Cache-Control"] = "public, max-age=3600" if len(sparks) >= len(UNIVERSE) - 2 else "public, max-age=120"
    return {"sparks": sparks, "days": SPARK_DAYS}


# ---------- ค้นหาหุ้นนอกรายการ 20 ตัว (ช่องค้นหาหน้า landing) ----------
# งบเฉพาะของหน้าสาธารณะ: ยิง Finnhub /search ได้ไม่เกิน 10 ครั้ง/นาที รวมทุกผู้เข้าชม
# จะได้ไม่ไปแย่งโควต้า 55 ครั้ง/นาทีที่ผู้ใช้ในแอปใช้ร่วมกัน (คำที่เคยค้นแล้วอ่านจาก cache ไม่นับงบ)
_SEARCH_RE = re.compile(r"^[A-Za-z0-9 .&'\-]{1,20}$")
SEARCH_BUDGET = (10, 60)
SEARCH_TTL = 3600


@router.get("/search")
async def public_market_search(response: Response, q: str = Query(min_length=1, max_length=20)):
    q = q.strip()
    if not _SEARCH_RE.match(q):  # ตัวอักษรไทย/สัญลักษณ์แปลกๆ ไม่ต้องไปถาม provider
        return []

    async def fetch():
        if not take_quota("public_search", *SEARCH_BUDGET):
            raise RateLimited("public_search")
        return await p.finnhub("/search", q=q)

    try:
        data = await cached(f"pubsearch:{q.lower()}", SEARCH_TTL, fetch)
    except RateLimited:
        raise HTTPException(503, "rate_limited")
    except ProviderError:
        raise HTTPException(502, "provider_error")
    response.headers["Cache-Control"] = "public, max-age=300"
    out = []
    for x in (data or {}).get("result", []):
        sym = x.get("symbol") or ""
        if not sym or "." in sym:  # ตัดหุ้นต่างตลาด (มีจุด) เหมือน /api/stocks/search
            continue
        out.append({"symbol": sym, "name": x.get("description") or "", "type": x.get("type") or ""})
    return out[:8]
