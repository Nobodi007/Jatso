import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request

from . import providers as p

log = logging.getLogger("stocks.screener")
router = APIRouter(prefix="/api/stocks", tags=["screener"])

SNAPSHOT_FILE = os.getenv("SCREENER_FILE", "/tmp/screener_snapshot.json")
REFRESH_SECONDS = 12 * 3600   # ดึงใหม่ทั้งชุดทุก 12 ชม.
PER_MINUTE = 40               # เหลือโควต้า Finnhub ให้หน้าอื่น ~15 ครั้ง/นาที

# ชื่อที่เลิกซื้อขาย/เปลี่ยนชื่อ ระบบจะข้ามเองและไม่ยิงซ้ำ เพิ่ม/ลบได้ตามต้องการ
UNIVERSE_RAW = """
AAPL MSFT NVDA AMZN GOOGL META TSLA AVGO ORCL ADBE CRM AMD INTC QCOM CSCO IBM TXN AMAT MU NOW
INTU PANW SNPS CDNS NFLX UBER SHOP PLTR ANET LRCX KLAC ADI MRVL ACN FTNT WDAY ADSK CRWD DDOG
SNOW TEAM NET ZS MSI APH TEL GLW HPQ HPE DELL NTAP WDC STX KEYS TYL FICO GDDY EPAM IT GEN AKAM
FFIV TRMB ZBRA PTC ROP MPWR ON NXPI MCHP SWKS QRVO TER ENTG SMCI ARM TSM ASML
DIS CMCSA T VZ TMUS CHTR WBD EA TTWO RBLX SPOT PINS SNAP LYV OMC MTCH
BRK.B JPM V MA BAC WFC GS MS C AXP BLK SCHW SPGI PGR CB MMC AON MCO ICE CME COF USB PNC TFC MET
PRU AIG ALL TRV AFL BK STT FITB HBAN RF KEY CFG NTRS MSCI TROW BX KKR APO ARES FIS GPN PYPL COIN
HOOD IBKR SYF AMP RJF NDAQ CBOE BRO AJG WTW HIG L CINF
UNH JNJ LLY ABBV MRK PFE TMO ABT DHR AMGN BMY GILD ISRG MDT CVS CI VRTX REGN ZTS SYK BSX EW BDX
HCA ELV HUM MCK COR CAH IDXX IQV A MTD WAT RMD DXCM GEHC BIIB MRNA ALGN ZBH STE HOLX COO LH DGX
PODD VTRS BAX TECH WST NVO
WMT COST HD PG KO PEP MCD NKE SBUX LOW TGT TJX BKNG MDLZ CL MO PM KMB GIS KHC HSY STZ KDP MNST
SYY ADM KR DG DLTR ROST ORLY AZO YUM DRI LULU DECK TSCO ULTA BBY EBAY EL KVUE CHD CLX HLT RCL CCL
NCLH LVS WYNN MGM DPZ TPR APTV GPC LKQ ABNB MAR CMG F GM RIVN TM MELI BABA PDD SE
XOM CVX COP EOG SLB OXY PSX MPC VLO WMB KMI OKE HAL BKR DVN FANG TRGP LNG CTRA EQT APA SHEL
CAT DE HON GE BA RTX LMT UPS UNP LIN ETN ITW EMR NOC GD FDX CSX NSC WM RSG PH CMI PCAR JCI TT
CARR OTIS MMM ROK AME FAST VRSK URI DAL UAL LUV GWW XYL IR DOV SWK HWM TDG LHX AXON CTAS PAYX
ADP ODFL EXPD CHRW JBHT FTV CPRT
NEE DUK SO D AEP EXC SRE XEL PEG ED WEC EIX PCG CEG VST NRG
AMT PLD EQIX O PSA CCI SPG WELL DLR VICI AVB EQR IRM SBAC EXR
SHW APD ECL FCX NEM NUE DOW DD LYB MLM VMC CTVA PPG ALB STLD
"""
UNIVERSE = list(dict.fromkeys(UNIVERSE_RAW.split()))
_UNI_SET = set(UNIVERSE)

_rows: dict[str, dict] = {}
_profiles: dict[str, dict] = {}
_dead: dict[str, float] = {}
_meta: dict = {"updatedAt": None, "fullAt": 0.0}
_refreshing = False


def _f(x):
    try:
        v = float(x)
        return v if v == v else None  # กัน NaN
    except (TypeError, ValueError):
        return None


def _save():
    try:
        tmp = SNAPSHOT_FILE + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({"rows": _rows, "profiles": _profiles, "dead": _dead, **_meta}, fh)
        os.replace(tmp, SNAPSHOT_FILE)
    except OSError as e:
        log.warning("cannot save snapshot: %s", e)


def _load():
    try:
        with open(SNAPSHOT_FILE) as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return
    rows = d.get("rows")
    if isinstance(rows, dict):
        _rows.update(rows)
    elif isinstance(rows, list):  # ไฟล์รุ่นเก่า: เก็บแค่ชื่อ/กลุ่ม ส่วนตัวเลขดึงใหม่
        for r in rows:
            if r.get("symbol") and (r.get("name") or r.get("industry")):
                _profiles[r["symbol"]] = {"name": r.get("name"), "industry": r.get("industry")}
    _profiles.update(d.get("profiles") or {})
    _dead.update(d.get("dead") or {})
    if d.get("updatedAt"):
        _meta["updatedAt"] = d["updatedAt"]
    if isinstance(d.get("fullAt"), (int, float)):
        _meta["fullAt"] = float(d["fullAt"])


async def _one(sym: str):
    need_profile = sym not in _profiles
    calls = [
        p.finnhub("/stock/metric", symbol=sym, metric="all"),
        p.finnhub("/quote", symbol=sym),
    ]
    if need_profile:
        calls.append(p.finnhub("/stock/profile2", symbol=sym))
    res = await asyncio.gather(*calls)
    m, q = res[0], res[1]

    price = _f((q or {}).get("c"))
    if not price:
        return None  # ไม่มีราคา = น่าจะเลิกซื้อขายหรือชื่อผิด

    if need_profile and res[2]:
        _profiles[sym] = {"name": res[2].get("name"), "industry": res[2].get("finnhubIndustry")}
    prof = _profiles.get(sym) or {}

    mm = (m or {}).get("metric") or {}
    hi = _f(mm.get("52WeekHigh"))
    return {
        "symbol": sym,
        "name": prof.get("name"),
        "industry": prof.get("industry"),
        "price": price,
        "changePercent": _f((q or {}).get("dp")),
        "marketCap": _f(mm.get("marketCapitalization")),          # ล้าน USD
        "pe": _f(mm.get("peTTM")),
        "pb": _f(mm.get("pbQuarterly")),
        "ps": _f(mm.get("psTTM")),
        "roe": _f(mm.get("roeTTM")),
        "roa": _f(mm.get("roaTTM")),
        "grossMargin": _f(mm.get("grossMarginTTM")),
        "operatingMargin": _f(mm.get("operatingMarginTTM")),
        "netMargin": _f(mm.get("netProfitMarginTTM")),
        "dividendYield": _f(mm.get("currentDividendYieldTTM")),
        "beta": _f(mm.get("beta")),
        "revenueGrowth": _f(mm.get("revenueGrowthTTMYoy")),
        "epsGrowth": _f(mm.get("epsGrowthTTMYoy")),
        "debtToEquity": _f(mm.get("totalDebt/totalEquityQuarterly")),
        "currentRatio": _f(mm.get("currentRatioQuarterly")),
        "fromHigh52w": ((price / hi - 1) * 100) if hi else None,   # 0 = อยู่ที่จุดสูงสุด
        "return13w": _f(mm.get("13WeekPriceReturnDaily")),
        "return52w": _f(mm.get("52WeekPriceReturnDaily")),
        "avgVolume": _f(mm.get("10DayAverageTradingVolume")),      # ล้านหุ้น
    }


async def _refresh(symbols: list[str], full: bool):
    global _refreshing
    if _refreshing:
        return
    _refreshing = True
    try:
        i = 0
        while i < len(symbols):
            # จัดกลุ่มให้จำนวนครั้งที่เรียก Finnhub ไม่เกิน PER_MINUTE
            chunk, calls = [], 0
            while i < len(symbols):
                s = symbols[i]
                c = 2 if s in _profiles else 3
                if chunk and calls + c > PER_MINUTE:
                    break
                chunk.append(s)
                calls += c
                i += 1

            t0 = time.time()
            results = await asyncio.gather(*(_one(s) for s in chunk), return_exceptions=True)
            for s, r in zip(chunk, results):
                if isinstance(r, dict):
                    _rows[s] = r
                    _dead.pop(s, None)
                elif r is None:
                    _dead[s] = time.time()
                else:
                    log.warning("screener skip %s: %r", s, r)  # โดน rate limit ฯลฯ รอบหน้าลองใหม่
            _meta["updatedAt"] = datetime.now(timezone.utc).isoformat()
            _save()

            wait = 60 - (time.time() - t0)
            if wait > 0 and i < len(symbols):
                await asyncio.sleep(wait)
        if full:
            _meta["fullAt"] = time.time()
            _save()
    finally:
        _refreshing = False


async def _loop():
    _load()
    while True:
        try:
            stale = time.time() - float(_meta.get("fullAt") or 0) >= REFRESH_SECONDS
            if stale:
                # ตัวที่ยังไม่มีข้อมูลมาก่อน แล้วค่อยตัวที่มีแล้ว
                order = [s for s in UNIVERSE if s not in _rows] + [s for s in UNIVERSE if s in _rows]
                await _refresh(order, True)
            else:
                missing = [s for s in UNIVERSE if s not in _rows and s not in _dead]
                if missing:
                    await _refresh(missing, False)
        except Exception:
            log.exception("screener refresh failed")
        await asyncio.sleep(600)


def start_background():
    """เรียกครั้งเดียวตอนแอปสตาร์ต"""
    asyncio.get_event_loop().create_task(_loop())


# พารามิเตอร์ {base}_min / {base}_max → ชื่อ field ในตาราง
FIELDS = {
    "pe": "pe", "pb": "pb", "ps": "ps",
    "roe": "roe", "roa": "roa", "gross": "grossMargin", "opm": "operatingMargin", "margin": "netMargin",
    "div": "dividendYield", "beta": "beta",
    "rev": "revenueGrowth", "eps_g": "epsGrowth",
    "de": "debtToEquity", "cr": "currentRatio",
    "mcap": "marketCap", "vol": "avgVolume",
    "from_high": "fromHigh52w", "ret13w": "return13w", "ret52w": "return52w",
}
SORTABLE = set(FIELDS.values()) | {"price", "changePercent", "symbol"}


@router.get("/screener")
async def screener(
    request: Request,
    sort: str = "marketCap",
    desc: bool = True,
    industry: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    rows = [r for s, r in _rows.items() if s in _UNI_SET]

    conds = []
    for base, field in FIELDS.items():
        for op in ("min", "max"):
            raw = request.query_params.get(f"{base}_{op}")
            if raw in (None, ""):
                continue
            try:
                conds.append((field, op, float(raw)))
            except ValueError:
                continue

    def ok(r):
        if industry and r.get("industry") != industry:
            return False
        for field, op, x in conds:
            v = r.get(field)
            if v is None:
                return False
            if op == "min" and v < x:
                return False
            if op == "max" and v > x:
                return False
        return True

    out = [r for r in rows if ok(r)]
    key = sort if sort in SORTABLE else "marketCap"
    have = [r for r in out if r.get(key) is not None]
    none = [r for r in out if r.get(key) is None]
    have.sort(key=lambda r: r[key], reverse=desc)
    out = have + none

    alive = len(UNIVERSE) - len([s for s in _dead if s in _UNI_SET])
    return {
        "updatedAt": _meta.get("updatedAt"),
        "partial": _refreshing and len(rows) < 0.9 * alive,
        "universe": len(UNIVERSE),
        "loaded": len(rows),
        "total": len(out),
        "industries": sorted({r["industry"] for r in rows if r.get("industry")}),
        "rows": out[:limit],
    }
