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

SCHEMA = 2  # เปลี่ยนเลขนี้เมื่อโครงสร้างแถวเปลี่ยน → ระบบจะทิ้งแถวเก่าและดึงใหม่
SNAPSHOT_FILE = os.getenv("SCREENER_FILE", "/tmp/screener_snapshot.json")
REFRESH_SECONDS = 12 * 3600
PER_MINUTE = 40

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
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def _g(mm: dict, *keys):
    """ค่าแรกที่ไม่ว่างจากรายชื่อ key (กันกรณีชื่อ key ของ Finnhub ต่างกันตามบริษัท/รุ่น)"""
    for k in keys:
        v = _f(mm.get(k))
        if v is not None:
            return v
    return None


# ───────────────────────── Metric registry ─────────────────────────
# เพิ่ม/ลบ/แก้ตัวกรองที่นี่ที่เดียว หน้าเว็บอ่านรายการนี้จาก /screener/meta เอง
# unit: usd | pct | x | mcap (ล้าน USD) | vol (ล้านหุ้น) | num
# tier: core | adv | quant

GROUPS = [
    ("A", "บริษัทและตลาด"),
    ("B", "มูลค่าหุ้น (Valuation)"),
    ("C", "การเติบโต (Growth)"),
    ("D", "ความสามารถทำกำไร"),
    ("E", "สุขภาพการเงิน"),
    ("F", "เงินปันผล"),
    ("Q", "Quant / เฉพาะทาง"),
]


def K(*keys):
    return lambda c: _g(c["mm"], *keys)


def _mcap(c):
    return _g(c["mm"], "marketCapitalization")


def _fcf(c):  # ล้าน USD = มูลค่าตลาด / (P/FCF)
    pf = _g(c["mm"], "pfcfShareTTM")
    mc = _mcap(c)
    return mc / pf if mc and pf else None


def _revenue(c):  # ล้าน USD = รายได้ต่อหุ้น × จำนวนหุ้น
    rps, mc, px = _g(c["mm"], "revenuePerShareTTM"), _mcap(c), c["price"]
    return rps * (mc / px) if rps and mc and px else None


def _peg(c):
    pe, g = _g(c["mm"], "peTTM"), _g(c["mm"], "epsGrowthTTMYoy")
    return pe / g if pe and pe > 0 and g and g > 0 else None


def _fcf_margin(c):
    f, r = _fcf(c), _revenue(c)
    return f / r * 100 if f is not None and r else None


def _ev_gp(c):
    ev, gm, r = _g(c["mm"], "enterpriseValue"), _g(c["mm"], "grossMarginTTM"), _revenue(c)
    return ev / (r * gm / 100) if ev and gm and r else None


def _debt_cap(c):
    de = _g(c["mm"], "totalDebt/totalEquityQuarterly")
    return de / (1 + de) * 100 if de is not None and de >= 0 else None


def _from_high(c):
    hi = _g(c["mm"], "52WeekHigh")
    return (c["price"] / hi - 1) * 100 if hi else None


def _from_low(c):
    lo = _g(c["mm"], "52WeekLow")
    return (c["price"] / lo - 1) * 100 if lo else None


# (id, label, group, tier, unit, placeholder, fn)
_SPEC = [
    # A. Company & Market
    ("price", "ราคาปัจจุบัน", "A", "core", "usd", "เช่น 50", lambda c: c["price"]),
    ("changePercent", "เปลี่ยนแปลงวันนี้ (%)", "A", "core", "pct", "เช่น 2", lambda c: c["dp"]),
    ("marketCap", "มูลค่าตลาด (ล้าน USD)", "A", "core", "mcap", "เช่น 10000", _mcap),
    ("avgVolume", "วอลุ่มเฉลี่ย 10 วัน (ล้านหุ้น)", "A", "core", "vol", "เช่น 5", K("10DayAverageTradingVolume")),
    ("high52w", "สูงสุด 52 สัปดาห์", "A", "core", "usd", "", K("52WeekHigh")),
    ("low52w", "ต่ำสุด 52 สัปดาห์", "A", "core", "usd", "", K("52WeekLow")),
    ("fromHigh52w", "ห่างจากสูงสุด 52 สัปดาห์ (%)", "A", "core", "pct", "เช่น -10 (ต่ำสุดที่รับได้)", _from_high),
    ("fromLow52w", "สูงกว่าต่ำสุด 52 สัปดาห์ (%)", "A", "core", "pct", "เช่น 30", _from_low),
    # B. Valuation
    ("pe", "P/E", "B", "core", "x", "เช่น 20", K("peTTM", "peBasicExclExtraTTM")),
    ("forwardPe", "P/E Forward", "B", "core", "x", "เช่น 18", K("forwardPE", "peForward")),
    ("ps", "P/S", "B", "core", "x", "เช่น 5", K("psTTM")),
    ("pb", "P/B", "B", "core", "x", "เช่น 3", K("pbQuarterly", "pbAnnual")),
    ("evEbitda", "EV/EBITDA", "B", "core", "x", "เช่น 12", K("evEbitdaTTM", "currentEv/ebitdaTTM", "ev/ebitdaTTM")),
    ("pfcf", "P/FCF", "B", "core", "x", "เช่น 20", K("pfcfShareTTM")),
    ("peg", "PEG (P/E ÷ EPS growth)", "B", "core", "x", "เช่น 1.5", _peg),
    ("evFcf", "EV/FCF", "B", "adv", "x", "เช่น 20", K("currentEv/freeCashFlowTTM")),
    ("pcf", "P/Cash flow", "B", "adv", "x", "เช่น 15", K("pcfShareTTM")),
    # C. Growth
    ("revenueGrowth", "รายได้โต YoY (%)", "C", "core", "pct", "เช่น 10", K("revenueGrowthTTMYoy")),
    ("epsGrowth", "EPS โต YoY (%)", "C", "core", "pct", "เช่น 10", K("epsGrowthTTMYoy")),
    ("ebitdaGrowth", "EBITDA โต (CAGR 5 ปี %)", "C", "core", "pct", "เช่น 8", K("ebitdaCagr5Y")),
    ("fcfGrowth", "FCF โต (CAGR 5 ปี %)", "C", "core", "pct", "เช่น 8", K("focfCagr5Y")),
    # D. Profitability
    ("grossMargin", "Gross margin (%)", "D", "core", "pct", "เช่น 40", K("grossMarginTTM")),
    ("operatingMargin", "Operating margin (%)", "D", "core", "pct", "เช่น 15", K("operatingMarginTTM")),
    ("netMargin", "Net margin (%)", "D", "core", "pct", "เช่น 10", K("netProfitMarginTTM")),
    ("roe", "ROE (%)", "D", "core", "pct", "เช่น 15", K("roeTTM")),
    ("roa", "ROA (%)", "D", "core", "pct", "เช่น 5", K("roaTTM")),
    ("roce", "ROCE ≈ ROI (%)", "D", "core", "pct", "เช่น 12", K("roiTTM")),
    ("fcfMargin", "FCF margin (%)", "D", "adv", "pct", "เช่น 10", _fcf_margin),
    # E. Financial Health
    ("debtToEquity", "Debt/Equity", "E", "core", "x", "เช่น 1", K("totalDebt/totalEquityQuarterly")),
    ("currentRatio", "Current ratio", "E", "core", "x", "เช่น 1.5", K("currentRatioQuarterly")),
    ("quickRatio", "Quick ratio", "E", "core", "x", "เช่น 1", K("quickRatioQuarterly")),
    ("interestCoverage", "Interest coverage", "E", "core", "x", "เช่น 5", K("netInterestCoverageTTM", "netInterestCoverageAnnual")),
    ("fcf", "Free cash flow (ล้าน USD)", "E", "core", "mcap", "เช่น 500", _fcf),
    # F. Dividends
    ("dividendYield", "ปันผล (%)", "F", "core", "pct", "เช่น 2", K("currentDividendYieldTTM", "dividendYieldIndicatedAnnual")),
    ("payoutRatio", "Payout ratio (%)", "F", "core", "pct", "เช่น 60", K("payoutRatioTTM")),
    ("dpsGrowth", "ปันผลต่อหุ้นโต (CAGR 5 ปี %)", "F", "core", "pct", "เช่น 5", K("dividendGrowthRate5Y")),
    # Quant
    ("debtToCapital", "Debt to capital (%)", "Q", "quant", "pct", "เช่น 40", _debt_cap),
    ("evGrossProfit", "EV/Gross profit", "Q", "quant", "x", "เช่น 15", _ev_gp),
    ("inventoryTurnover", "Inventory turnover", "Q", "quant", "x", "เช่น 5", K("inventoryTurnoverTTM", "inventoryTurnoverAnnual")),
    ("receivablesTurnover", "Receivables turnover", "Q", "quant", "x", "เช่น 8", K("receivablesTurnoverTTM", "receivablesTurnoverAnnual")),
    ("fixedAssetTurnover", "Fixed assets turnover", "Q", "quant", "x", "เช่น 3", K("fixedAssetTurnoverTTM", "fixedAssetTurnoverAnnual")),
]
METRICS = [dict(zip(("id", "label", "group", "tier", "unit", "ph", "fn"), s)) for s in _SPEC]
_IDS = [m["id"] for m in METRICS]
SORTABLE = set(_IDS) | {"symbol"}


# ───────────────────────── Storage ─────────────────────────

def _save():
    try:
        tmp = SNAPSHOT_FILE + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({"schema": SCHEMA, "rows": _rows, "profiles": _profiles, "dead": _dead, **_meta}, fh)
        os.replace(tmp, SNAPSHOT_FILE)
    except OSError as e:
        log.warning("cannot save snapshot: %s", e)


def _load():
    try:
        with open(SNAPSHOT_FILE) as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return
    _profiles.update(d.get("profiles") or {})
    _dead.update(d.get("dead") or {})
    if d.get("schema") != SCHEMA:
        return  # โครงสร้างเก่า: เก็บแค่โปรไฟล์ ส่วนตัวเลขดึงใหม่ทั้งหมด
    if isinstance(d.get("rows"), dict):
        _rows.update(d["rows"])
    if d.get("updatedAt"):
        _meta["updatedAt"] = d["updatedAt"]
    if isinstance(d.get("fullAt"), (int, float)):
        _meta["fullAt"] = float(d["fullAt"])


# ───────────────────────── Fetching ─────────────────────────

def _exch(s):
    u = (s or "").upper()
    if "NASDAQ" in u:
        return "NASDAQ"
    if "NEW YORK" in u or "NYSE" in u:
        return "NYSE"
    return s or None


def _has_profile(sym: str) -> bool:
    return "exchange" in (_profiles.get(sym) or {})


async def _one(sym: str):
    need_profile = not _has_profile(sym)
    calls = [p.finnhub("/stock/metric", symbol=sym, metric="all"), p.finnhub("/quote", symbol=sym)]
    if need_profile:
        calls.append(p.finnhub("/stock/profile2", symbol=sym))
    res = await asyncio.gather(*calls)
    m, q = res[0], res[1]

    # คืน None จาก provider = เรียกไม่สำเร็จ (ไม่ใช่เลิกซื้อขาย) → ให้รอบหน้าลองใหม่ ไม่ใส่ _dead
    # ถ้า p.finnhub ของคุณคืน {} ตอนพลาดแทน None ให้แก้เงื่อนไขนี้ให้ตรง
    if m is None or q is None:
        raise RuntimeError("finnhub call failed")

    price = _f(q.get("c"))
    if not price:
        return None  # ตอบกลับปกติแต่ไม่มีราคา = น่าจะเลิกซื้อขายหรือชื่อผิด

    if need_profile and res[2]:
        _profiles[sym] = {
            "name": res[2].get("name"),
            "industry": res[2].get("finnhubIndustry"),
            "exchange": _exch(res[2].get("exchange")),
        }
    prof = _profiles.get(sym) or {}

    c = {"mm": m.get("metric") or {}, "price": price, "dp": _f(q.get("dp"))}
    row = {"symbol": sym, "name": prof.get("name"), "industry": prof.get("industry"), "exchange": prof.get("exchange")}
    for mt in METRICS:
        try:
            row[mt["id"]] = mt["fn"](c)
        except (ZeroDivisionError, TypeError):
            row[mt["id"]] = None
    return row


async def _refresh(symbols: list[str], full: bool):
    global _refreshing
    if _refreshing:
        return
    _refreshing = True
    try:
        i = 0
        while i < len(symbols):
            chunk, calls = [], 0
            while i < len(symbols):
                s = symbols[i]
                n = 2 if _has_profile(s) else 3
                if chunk and calls + n > PER_MINUTE:
                    break
                chunk.append(s)
                calls += n
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
                    log.warning("screener skip %s: %r", s, r)
            _meta["updatedAt"] = datetime.now(timezone.utc).isoformat()
            await asyncio.to_thread(_save)

            wait = 60 - (time.time() - t0)
            if wait > 0 and i < len(symbols):
                await asyncio.sleep(wait)
        if full:
            _meta["fullAt"] = time.time()
            await asyncio.to_thread(_save)
    finally:
        _refreshing = False


async def _loop():
    _load()
    while True:
        try:
            stale = time.time() - float(_meta.get("fullAt") or 0) >= REFRESH_SECONDS
            if stale:
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


# ───────────────────────── API ─────────────────────────

def _universe_rows():
    return [r for s, r in _rows.items() if s in _UNI_SET]


@router.get("/screener/meta")
async def screener_meta():
    rows = _universe_rows()
    return {
        "groups": [{"id": i, "title": t} for i, t in GROUPS],
        "metrics": [{k: v for k, v in m.items() if k != "fn"} for m in METRICS],
        "industries": sorted({r["industry"] for r in rows if r.get("industry")}),
        "exchanges": sorted({r["exchange"] for r in rows if r.get("exchange")}),
    }


@router.get("/screener/raw/{symbol}")
async def screener_raw(symbol: str):
    """ดู key ทั้งหมดที่ Finnhub ส่งมาจริง ใช้ตรวจว่า metric ไหนต้องแก้ชื่อ key"""
    m = await p.finnhub("/stock/metric", symbol=symbol.upper(), metric="all")
    return (m or {}).get("metric") or {}


@router.get("/screener")
async def screener(
    request: Request,
    sort: str = "marketCap",
    desc: bool = True,
    industry: str | None = None,
    exchange: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    rows = _universe_rows()

    conds = []
    for mid in _IDS:
        for op in ("min", "max"):
            raw = request.query_params.get(f"{mid}_{op}")
            if raw in (None, ""):
                continue
            try:
                conds.append((mid, op, float(raw)))
            except ValueError:
                continue

    def ok(r):
        if industry and r.get("industry") != industry:
            return False
        if exchange and r.get("exchange") != exchange:
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
        "partial": len(rows) < 0.9 * alive,
        "universe": len(UNIVERSE),
        "loaded": len(rows),
        "total": len(out),
        # จำนวนหุ้นที่มีข้อมูลของแต่ละตัวชี้วัด ใช้ปิดตัวกรองที่ไม่มีข้อมูลเลย
        "coverage": {mid: sum(1 for r in rows if r.get(mid) is not None) for mid in _IDS},
        "rows": out[:limit],
    }
