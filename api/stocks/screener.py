import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from . import providers as p
from .cache import ProviderError, RateLimited

log = logging.getLogger("stocks.screener")
router = APIRouter(prefix="/api/stocks", tags=["screener"])

SNAPSHOT_FILE = os.getenv("SCREENER_FILE", "/tmp/screener_snapshot.json")
REFRESH_SECONDS = 12 * 3600      # ทำใหม่ทุก 12 ชม.
PER_MINUTE = 40                  # เหลือโควต้า Finnhub ให้หน้าอื่นใช้ ~15 ครั้ง/นาที

# รายชื่อเริ่มต้น: หุ้นใหญ่สหรัฐ (เพิ่ม/ลดได้ตามต้องการ)
UNIVERSE = """
AAPL MSFT NVDA AMZN GOOGL META TSLA AVGO ORCL ADBE CRM AMD INTC QCOM CSCO IBM TXN AMAT MU NOW
INTU PANW SNPS CDNS NFLX UBER SHOP PLTR ANET LRCX KLAC ADI MRVL
BRK.B JPM V MA BAC WFC GS MS C AXP BLK SCHW SPGI PGR CB MMC
UNH JNJ LLY ABBV MRK PFE TMO ABT DHR AMGN BMY GILD ISRG MDT CVS CI VRTX REGN ZTS
WMT COST HD PG KO PEP MCD NKE SBUX LOW TGT TJX BKNG MDLZ CL MO PM
XOM CVX COP EOG SLB OXY PSX MPC
CAT DE HON GE BA RTX LMT UPS UNP LIN ETN ITW EMR
DIS CMCSA T VZ TMUS
NEE DUK SO AMT PLD EQIX O
F GM ABNB MAR CMG
""".split()

_snapshot: dict = {"updatedAt": None, "rows": []}
_refreshing = False


def _f(x):
    try:
        v = float(x)
        return v if v == v else None   # กัน NaN
    except (TypeError, ValueError):
        return None


async def _one(sym: str):
    m_task = p.finnhub("/stock/metric", symbol=sym, metric="all")
    q_task = p.finnhub("/quote", symbol=sym)
    prof_task = p.finnhub("/stock/profile2", symbol=sym)
    m, q, prof = await asyncio.gather(m_task, q_task, prof_task)
    mm = (m or {}).get("metric") or {}
    price = _f((q or {}).get("c"))
    if not price:
        return None
    return {
        "symbol": sym,
        "name": (prof or {}).get("name"),
        "industry": (prof or {}).get("finnhubIndustry"),
        "price": price,
        "changePercent": _f((q or {}).get("dp")),
        "marketCap": _f(mm.get("marketCapitalization")),   # ล้าน USD
        "pe": _f(mm.get("peTTM")),
        "pb": _f(mm.get("pbQuarterly")),
        "roe": _f(mm.get("roeTTM")),
        "netMargin": _f(mm.get("netProfitMarginTTM")),
        "dividendYield": _f(mm.get("currentDividendYieldTTM")),
        "beta": _f(mm.get("beta")),
        "revenueGrowth": _f(mm.get("revenueGrowthTTMYoy")),
    }


async def _refresh():
    global _refreshing, _snapshot
    if _refreshing:
        return
    _refreshing = True
    rows, done = [], 0
    try:
        # แต่ละตัวใช้ 3 ครั้ง → ทำทีละกลุ่มเล็กๆ ให้ไม่เกินโควต้าต่อนาที
        batch = max(1, PER_MINUTE // 3)
        for i in range(0, len(UNIVERSE), batch):
            chunk = UNIVERSE[i:i + batch]
            t0 = time.time()
            results = await asyncio.gather(*(_one(s) for s in chunk), return_exceptions=True)
            for s, r in zip(chunk, results):
                if isinstance(r, dict):
                    rows.append(r)
                elif isinstance(r, (RateLimited, ProviderError)):
                    log.warning("screener skip %s: %s", s, r)
                elif isinstance(r, Exception):
                    log.warning("screener error %s: %r", s, r)
            done += len(chunk)
            # ครบ 1 นาทีต่อกลุ่ม
            wait = 60 - (time.time() - t0)
            if wait > 0 and done < len(UNIVERSE):
                await asyncio.sleep(wait)
            # เก็บผลระหว่างทาง ผู้ใช้จะเห็นข้อมูลบางส่วนก่อนครบ
            _snapshot = {"updatedAt": datetime.now(timezone.utc).isoformat(), "rows": rows[:], "partial": True}
        _snapshot = {"updatedAt": datetime.now(timezone.utc).isoformat(), "rows": rows, "partial": False}
        try:
            with open(SNAPSHOT_FILE, "w") as fh:
                json.dump(_snapshot, fh)
        except OSError as e:
            log.warning("cannot save snapshot: %s", e)
    finally:
        _refreshing = False


async def _loop():
    global _snapshot
    try:
        with open(SNAPSHOT_FILE) as fh:
            _snapshot = json.load(fh)
    except (OSError, ValueError):
        pass
    while True:
        age = float("inf")
        if _snapshot.get("updatedAt") and not _snapshot.get("partial"):
            age = time.time() - datetime.fromisoformat(_snapshot["updatedAt"]).timestamp()
        if age >= REFRESH_SECONDS:
            try:
                await _refresh()
            except Exception:
                log.exception("screener refresh failed")
        await asyncio.sleep(600)


def start_background():
    """เรียกครั้งเดียวตอนแอปสตาร์ต"""
    asyncio.get_event_loop().create_task(_loop())


@router.get("/screener")
async def screener(
    pe_max: float | None = None,
    pe_min: float | None = None,
    roe_min: float | None = None,
    margin_min: float | None = None,
    div_min: float | None = None,
    beta_max: float | None = None,
    mcap_min: float | None = Query(None, description="ล้าน USD"),
    sort: str = "marketCap",
    desc: bool = True,
    limit: int = Query(50, ge=1, le=200),
):
    rows = _snapshot.get("rows", [])

    def ok(r):
        def chk(v, lo=None, hi=None):
            if lo is None and hi is None:
                return True
            if v is None:
                return False
            return (lo is None or v >= lo) and (hi is None or v <= hi)
        return (
            chk(r["pe"], pe_min, pe_max)
            and chk(r["roe"], roe_min)
            and chk(r["netMargin"], margin_min)
            and chk(r["dividendYield"], div_min)
            and chk(r["beta"], None, beta_max)
            and chk(r["marketCap"], mcap_min)
        )

    out = [r for r in rows if ok(r)]
    key = sort if sort in {"marketCap", "pe", "pb", "roe", "netMargin", "dividendYield", "beta", "revenueGrowth", "changePercent", "price"} else "marketCap"
    out.sort(key=lambda r: (r.get(key) is None, r.get(key) or 0), reverse=False)
    if desc:
        have = [r for r in out if r.get(key) is not None]
        none = [r for r in out if r.get(key) is None]
        out = sorted(have, key=lambda r: r[key], reverse=True) + none
    return {
        "updatedAt": _snapshot.get("updatedAt"),
        "partial": bool(_snapshot.get("partial")),
        "universe": len(UNIVERSE),
        "loaded": len(rows),
        "total": len(out),
        "rows": out[:limit],
    }
