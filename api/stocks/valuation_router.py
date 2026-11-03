# valuation_router.py -- endpoint ดึงข้อมูล Valuation จาก Supabase (อ่านอย่างเดียว)
#
# ติดตั้งใน FastAPI ของมึง (ที่มี prefix /api/stocks อยู่แล้ว):
#     from valuation_router import router as valuation_router
#     app.include_router(valuation_router, prefix="/api/stocks")
#
# ต้องมี env บน Render: SUPABASE_URL, SUPABASE_SERVICE_KEY  (และ pip: supabase)
# ถ้าหลังบ้านมีตัวต่อ Supabase อยู่แล้ว ให้แก้ฟังก์ชัน _sb() ให้คืน client ตัวนั้นแทน
import os
import re
import time

from fastapi import APIRouter, HTTPException

router = APIRouter()

_SYM = re.compile(r"^[A-Z][A-Z.\-]{0,9}$")
_TTL = 600  # วินาที ข้อมูลอัปเดตวันละครั้ง cache ไว้ 10 นาทีพอ
_cache: dict = {}
_client = None


def _sb():
    global _client
    if _client is None:
        from supabase import create_client
        _client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    return _client


def _f(x):
    """แปลงเป็น float หรือ None (กัน NaN/inf ที่ JSON ไม่รองรับ)"""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and v not in (float("inf"), float("-inf")) else None


@router.get("/{symbol}/valuation")
def valuation(symbol: str):
    sym = symbol.strip().upper()
    if not _SYM.match(sym):
        raise HTTPException(status_code=400, detail="invalid_symbol")

    hit = _cache.get(sym)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]

    try:
        sb = _sb()
        alt = sym.replace("-", ".")  # BRK-B / BRK.B ใช้ได้ทั้งคู่
        latest = (sb.table("valuation_latest").select("*").in_("ticker", [sym, alt]).limit(1).execute().data)
        if not latest:
            raise HTTPException(status_code=404, detail="no_valuation")
        row = latest[0]
        sym = row["ticker"]
        comp = (sb.table("companies").select("sector,industry,valuation_model")
                .eq("ticker", sym).limit(1).execute().data) or [{}]
        hist = (sb.table("valuation_monthly")
                .select("month_end,price,market_cap,pe,ps,pfcf,ev_ebitda")
                .eq("ticker", sym).order("month_end", desc=True).limit(61).execute().data) or []
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="provider_error")

    hist.reverse()
    out = {
        "symbol": sym,
        "asOf": row.get("as_of"),
        "status": row.get("model_status") or "insufficient_data",
        "model": comp[0].get("valuation_model"),
        "sector": comp[0].get("sector"),
        "price": _f(row.get("price")),
        "marketCap": _f(row.get("market_cap")),
        "multiples": {
            "pe": _f(row.get("pe")), "ps": _f(row.get("ps")),
            "pfcf": _f(row.get("pfcf")), "evEbitda": _f(row.get("ev_ebitda")),
        },
        # 0-1 : สัดส่วนของเดือนในอดีต 5 ปีที่ตัวคูณต่ำกว่าปัจจุบัน (ยิ่งสูงยิ่งแพงเมื่อเทียบกับตัวเอง)
        "percentile5y": {
            "pe": _f(row.get("pe_pct_5y")), "ps": _f(row.get("ps_pct_5y")), "pfcf": _f(row.get("pfcf_pct_5y")),
        },
        "peVsPeers": _f(row.get("pe_vs_industry")),   # 0.15 = แพงกว่ามัธยฐานกลุ่ม 15%
        "impliedGrowth": _f(row.get("implied_growth")),
        "histRevCagr5y": _f(row.get("hist_rev_cagr_5y")),
        "assumptions": {"discountRate": 0.10, "terminalGrowth": 0.025, "years": 10},
        "history": [
            {"month": h["month_end"], "price": _f(h.get("price")), "pe": _f(h.get("pe")),
             "ps": _f(h.get("ps")), "pfcf": _f(h.get("pfcf")), "evEbitda": _f(h.get("ev_ebitda"))}
            for h in hist
        ],
    }
    _cache[sym] = (time.time(), out)
    return out
