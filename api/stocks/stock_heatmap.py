"""Heatmap หุ้นสหรัฐ: S&P 500 / Dow Jones 30 / Nasdaq 100

- รายชื่อ S&P 500 + sector ดึงจากชุดข้อมูลสาธารณะบน GitHub (datasets/s-and-p-500-companies)
- Dow 30 และ Nasdaq 100 เป็นรายชื่อตายตัวด้านล่าง (แก้เองได้เมื่อมีการปรับดัชนี)
- ราคา/มูลค่าตลาดจาก Finnhub ทีละตัว ช้าๆ ในเธรดเบื้องหลัง (ไม่ชนโควต้า 60 ครั้ง/นาที)
- เก็บผลลง Supabase ตาราง stock_heat เพื่อให้ Render ที่ตื่นจากหลับมีข้อมูลทันที
- เธรดเริ่มทำงานเองตอนมีคนเรียก endpoint ครั้งแรก ไม่ต้องแก้ startup ใน server.py
"""
import csv
import io
import os
import threading
import time
from datetime import datetime, timezone

import requests
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/heatmap", tags=["stock-heatmap"])

FINNHUB_KEY = (
    os.getenv("FINNHUB_API_KEY") or os.getenv("FINNHUB_KEY") or os.getenv("FINNHUB_TOKEN") or ""
)
# หน่วงระหว่างการเรียก Finnhub แต่ละครั้ง (วินาที) 1.7 = ประมาณ 35 ครั้ง/นาที เหลือโควต้าให้ส่วนอื่นของเว็บ
DELAY = float(os.getenv("HEATMAP_DELAY", "1.7"))
CSV_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
TABLE = "stock_heat"

DOW = set(
    "AAPL AMGN AMZN AXP BA CAT CRM CSCO CVX DIS GS HD HON IBM JNJ JPM KO MCD MMM MRK MSFT "
    "NKE NVDA PG SHW TRV UNH V VZ WMT".split()
)
NDX = set(
    """AAPL ABNB ADBE ADI ADP ADSK AEP ALNY AMAT AMD AMGN AMZN APP ARM ASML AVGO AXON AZN BIIB BKNG BKR
    CCEP CDNS CEG CHTR CMCSA COST CPRT CRWD CSCO CSGP CSX CTAS CTSH DASH DDOG DXCM EA EXC FANG FAST FER
    FTNT GEHC GFS GILD GOOG GOOGL HON IDXX INSM INTC INTU ISRG KDP KHC KLAC LIN LRCX MAR MCHP MDLZ MELI
    META MNST MPWR MRVL MSFT MSTR MU NFLX NVDA NXPI ODFL ORLY PANW PAYX PCAR PDD PEP PLTR PYPL QCOM REGN
    ROP ROST SBUX SHOP SNPS STX TEAM TMUS TRI TSLA TTWO TXN VRSK VRTX WBD WDAY WDC XEL ZS""".split()
)
# sector ของตัวที่ไม่อยู่ใน S&P 500 (ใช้จัดกลุ่มใน heatmap)
EXTRA_SECTOR = {
    "ARM": "Information Technology", "ASML": "Information Technology", "GFS": "Information Technology",
    "SHOP": "Information Technology", "TEAM": "Information Technology", "ZS": "Information Technology",
    "MSTR": "Information Technology", "AZN": "Health Care", "ALNY": "Health Care", "INSM": "Health Care",
    "MELI": "Consumer Discretionary", "PDD": "Consumer Discretionary", "CCEP": "Consumer Staples",
    "FER": "Industrials", "TRI": "Industrials",
}

LOCK = threading.Lock()
CACHE: dict[str, dict] = {}
DIRTY: set[str] = set()
_started = False
_start_lock = threading.Lock()


# ---------------- Supabase (ไม่บังคับ: ถ้าไม่มี key ก็ทำงานในหน่วยความจำอย่างเดียว) ----------------
def _supabase():
    key = (
        os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    )
    url = os.getenv("SUPABASE_URL")
    if not (key and url):
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception as e:
        print(f"[heatmap] supabase ใช้ไม่ได้: {e}")
        return None


SB = _supabase()


def _row(sym: str) -> dict:
    r = CACHE.get(sym)
    if r is None:
        r = CACHE[sym] = {
            "symbol": sym, "name": "", "sector": "", "idx": set(),
            "market_cap": None, "shares": None, "price": None, "change_pct": None,
            "quote_at": None, "fails": 0,
        }
    return r


def _load_table():
    if not SB:
        return
    try:
        data = SB.table(TABLE).select("*").limit(2000).execute().data or []
    except Exception as e:
        print(f"[heatmap] อ่านตาราง {TABLE} ไม่ได้: {e}")
        return
    with LOCK:
        for d in data:
            r = _row(d["symbol"])
            r["name"] = d.get("name") or ""
            r["sector"] = d.get("sector") or ""
            r["idx"] = set(filter(None, (d.get("idx") or "").split(",")))
            r["market_cap"] = d.get("market_cap")
            r["shares"] = d.get("shares")
            r["price"] = d.get("price")
            r["change_pct"] = d.get("change_pct")
            qa = d.get("quote_at")
            if qa:
                try:
                    r["quote_at"] = datetime.fromisoformat(qa.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    pass


def _flush():
    if not SB:
        return
    with LOCK:
        syms = list(DIRTY)
        DIRTY.clear()
        rows = []
        for s in syms:
            r = CACHE[s]
            rows.append({
                "symbol": s, "name": r["name"], "sector": r["sector"], "idx": ",".join(sorted(r["idx"])),
                "market_cap": r["market_cap"], "shares": r["shares"], "price": r["price"],
                "change_pct": r["change_pct"],
                "quote_at": datetime.fromtimestamp(r["quote_at"], timezone.utc).isoformat() if r["quote_at"] else None,
            })
    if rows:
        try:
            SB.table(TABLE).upsert(rows).execute()
        except Exception as e:
            print(f"[heatmap] บันทึกตารางไม่สำเร็จ: {e}")


# ---------------- รายชื่อหุ้นในแต่ละดัชนี ----------------
def _build_universe():
    sp: dict[str, tuple[str, str]] = {}
    try:
        txt = requests.get(CSV_URL, timeout=15).text
        for r in csv.DictReader(io.StringIO(txt)):
            sp[r["Symbol"].strip().upper()] = (r.get("Security", "").strip(), r.get("GICS Sector", "").strip())
    except Exception as e:
        print(f"[heatmap] โหลดรายชื่อ S&P 500 ไม่ได้: {e}")
    with LOCK:
        for s, (name, sec) in sp.items():
            r = _row(s)
            r["name"] = r["name"] or name
            r["sector"] = sec or r["sector"]
            r["idx"].add("sp500")
        for s in DOW:
            _row(s)["idx"].add("dow")
        for s in NDX:
            r = _row(s)
            r["idx"].add("ndx")
            r["sector"] = r["sector"] or EXTRA_SECTOR.get(s, "")
        for r in CACHE.values():
            DIRTY.add(r["symbol"])


# ---------------- Finnhub ----------------
def _fh(path: str, **params):
    r = requests.get(
        f"https://finnhub.io/api/v1{path}", params={**params, "token": FINNHUB_KEY}, timeout=8
    )
    if r.status_code == 429:
        time.sleep(30)
        raise RuntimeError("finnhub rate limited")
    r.raise_for_status()
    return r.json()


def _market_open() -> bool:
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:
        return False
    h = now.hour + now.minute / 60
    return 13.4 <= h <= 21.1  # ครอบคลุมทั้งเวลาปกติและ DST


def _next_job():
    with LOCK:
        rows = list(CACHE.values())
    # Dow/Nasdaq 100 ก่อน แล้วค่อยหุ้น S&P 500 ที่เหลือ
    rows.sort(key=lambda r: (0 if r["idx"] & {"dow", "ndx"} else 1, r["symbol"]))
    for r in rows:
        if r["fails"] >= 3:
            continue
        if r["market_cap"] is None:
            return "profile", r
        if r["quote_at"] is None:
            return "quote", r
    if _market_open() and rows:
        return "quote", min(rows, key=lambda r: r["quote_at"] or 0)
    return None


def _do(job: str, r: dict):
    sym = r["symbol"]
    if job == "profile":
        p = _fh("/stock/profile2", symbol=sym)
        cap = p.get("marketCapitalization")  # หน่วยล้านดอลลาร์
        with LOCK:
            if cap:
                r["market_cap"] = float(cap)
                r["name"] = p.get("name") or r["name"]
                r["sector"] = r["sector"] or p.get("finnhubIndustry") or ""
            else:
                r["fails"] += 1
            DIRTY.add(sym)
    else:
        q = _fh("/quote", symbol=sym)
        c, dp = q.get("c"), q.get("dp")
        with LOCK:
            if c and dp is not None:
                r["price"], r["change_pct"], r["fails"] = float(c), float(dp), 0
                if r["shares"] is None and r["market_cap"]:
                    r["shares"] = r["market_cap"] / float(c)  # ล้านหุ้น ใช้ปรับขนาดตามราคาต่อไป
            else:
                r["fails"] += 1
            r["quote_at"] = time.time()
            DIRTY.add(sym)


def _run():
    _load_table()
    _build_universe()
    last_flush = time.time()
    while True:
        try:
            job = _next_job() if FINNHUB_KEY else None
            if job:
                _do(*job)
                time.sleep(DELAY)
            else:
                time.sleep(30)
        except Exception as e:
            print(f"[heatmap] {e}")
            time.sleep(5)
        if DIRTY and (len(DIRTY) >= 20 or time.time() - last_flush > 60):
            _flush()
            last_flush = time.time()


def _ensure_worker():
    global _started
    with _start_lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_run, daemon=True, name="heatmap-worker").start()


# ---------------- API ----------------
def _cap(r: dict):
    if r["shares"] and r["price"]:
        return r["shares"] * r["price"]
    return r["market_cap"]


@router.get("")
def heatmap(index: str = Query("sp500")):
    if index not in ("sp500", "dow", "ndx"):
        raise HTTPException(400, "invalid_index")
    _ensure_worker()
    with LOCK:
        members = [r for r in CACHE.values() if index in r["idx"]]
        items = []
        for r in members:
            cap = _cap(r)
            if not cap or not r["price"] or r["change_pct"] is None:
                continue
            items.append({
                "symbol": r["symbol"], "name": r["name"] or r["symbol"], "sector": r["sector"],
                "marketCap": round(cap, 1), "price": r["price"], "changePercent": r["change_pct"],
            })
        ts = max((r["quote_at"] or 0 for r in members), default=0)
    return {
        "index": index,
        "total": len(members),
        "ready": len(items),
        "updatedAt": datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None,
        "items": items,
    }
