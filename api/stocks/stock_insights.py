"""
stock_insights.py  -  ข้อมูลเพิ่มเติมหน้า Company (Finnhub ก่อน, Yahoo เป็น fallback)
  GET /api/stocks/{symbol}/executives
  GET /api/stocks/{symbol}/ownership
  GET /api/stocks/{symbol}/analyst
  GET /api/stocks/{symbol}/insiders

เพิ่มใน router.py:
    from .stock_insights import router as stock_insights_router
    router.include_router(stock_insights_router)
"""
import asyncio
import importlib.metadata as _md
import logging
import math
import os
import re
import time

from fastapi import APIRouter, HTTPException

from . import providers as p
from .cache import ProviderError, RateLimited, cached

log = logging.getLogger("stocks.insights")
router = APIRouter(tags=["stocks-insights"])
SYMBOL_RE = re.compile(r"^[A-Z][A-Z.\-]{0,9}$")


def norm(symbol: str) -> str:
    s = symbol.upper().strip()
    if not SYMBOL_RE.match(s):
        raise HTTPException(400, "invalid_symbol")
    return s


async def guard(coro):
    try:
        return await coro
    except RateLimited:
        raise HTTPException(503, "rate_limited")
    except ProviderError:
        raise HTTPException(502, "provider_error")


async def optional(coro):
    """ล้มเหลว/ติดแพ็กเกจ -> None (ไม่ทำให้ทั้งหน้าพัง) แต่ rate limit ยังส่งต่อให้ frontend"""
    try:
        return await coro
    except RateLimited:
        raise HTTPException(503, "rate_limited")
    except ProviderError as e:
        print(f"[insights] provider failed: {type(e).__name__}: {str(e)[:200]}")
        return None


_EMPTY_UNTIL: dict = {}


def _nonempty(key, fn, ok):
    """ไม่ให้ cache ผลที่ว่าง: ถ้าว่างให้ raise (cached จะไม่เก็บ) และพัก 5 นาทีก่อนลองใหม่"""
    async def run():
        if time.time() < _EMPTY_UNTIL.get(key, 0):
            raise ProviderError("empty (recent)")
        r = await fn()
        if not ok(r):
            _EMPTY_UNTIL[key] = time.time() + 300
            raise ProviderError("empty result")
        return r
    return run


def _f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _day(ts):
    try:
        return ts.date().isoformat()
    except AttributeError:
        return str(ts)[:10] if ts is not None else None


# ====================== Yahoo (sync, รันผ่าน p._yahoo) ======================
def _yf_officers(symbol):
    import yfinance as yf
    info = yf.Ticker(p._yf_sym(symbol)).info or {}
    return [
        {"name": o.get("name"), "title": o.get("title"), "since": None,
         "age": o.get("age"), "compensation": o.get("totalPay")}
        for o in info.get("companyOfficers") or [] if o.get("name")
    ]


def _yf_holders(symbol):
    import yfinance as yf
    t = yf.Ticker(p._yf_sym(symbol))
    out = {"institutionsPercent": None, "insidersPercent": None, "holders": []}
    try:
        mh = t.major_holders
        if mh is not None and not mh.empty:
            col = mh.columns[0]
            for key, field in (("institutionsPercentHeld", "institutionsPercent"),
                               ("insidersPercentHeld", "insidersPercent")):
                if key in mh.index:
                    v = _f(mh.loc[key, col])
                    out[field] = round(v * 100, 2) if v is not None else None
    except Exception:
        pass
    df = t.institutional_holders
    if df is not None and not df.empty:
        pct_col = "pctHeld" if "pctHeld" in df.columns else ("% Out" if "% Out" in df.columns else None)
        for _, r in df.iterrows():
            pct = _f(r.get(pct_col)) if pct_col else None
            chg = _f(r.get("pctChange"))
            sh = _f(r.get("Shares"))
            out["holders"].append({
                "name": r.get("Holder"), "shares": sh,
                "percent": round(pct * 100, 2) if pct is not None else None,
                # Yahoo ให้เป็น % เปลี่ยนแปลง ไม่ใช่จำนวนหุ้น -> แปลงเป็นจำนวนหุ้นโดยประมาณ
                "change": round(sh * chg / (1 + chg)) if sh and chg not in (None, -1) else None,
                "date": _day(r.get("Date Reported")),
            })
    return out


def _yf_analyst(symbol):
    import yfinance as yf
    t = yf.Ticker(p._yf_sym(symbol))
    res = {"rating": None, "target": None}
    try:
        pt = t.analyst_price_targets or {}
        if pt.get("mean"):
            res["target"] = {"mean": _f(pt.get("mean")), "median": _f(pt.get("median")),
                             "high": _f(pt.get("high")), "low": _f(pt.get("low")), "updatedAt": None}
    except Exception:
        pass
    try:
        rs = t.recommendations_summary
        if rs is not None and not rs.empty:
            r = rs.iloc[0]
            res["rating"] = {k: int(_f(r.get(k)) or 0) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")}
            res["rating"]["period"] = str(r.get("period", ""))
    except Exception:
        pass
    return res


def _yf_insiders(symbol):
    import yfinance as yf
    df = yf.Ticker(p._yf_sym(symbol)).insider_transactions
    out = []
    if df is None or df.empty:
        return out
    for _, r in df.iterrows():
        text = f"{r.get('Transaction') or ''} {r.get('Text') or ''}".lower()
        if "sale" in text or "sold" in text:
            typ = "SELL"
        elif "purchase" in text or "bought" in text or "buy" in text:
            typ = "BUY"
        else:
            continue  # ข้าม award / exercise / gift
        sh, val = _f(r.get("Shares")), _f(r.get("Value"))
        if not sh:
            continue
        out.append({
            "name": r.get("Insider"), "title": r.get("Position") or None, "type": typ,
            "shares": abs(sh), "price": round(val / abs(sh), 2) if val else None,
            "value": round(abs(val)) if val else None, "date": _day(r.get("Start Date")),
        })
    return out


# ====================== FMP fallback (ใช้โควต้า fmp รวมกับส่วนอื่น) ======================
async def _fmp_officers(s):
    rows = await p._fmp("/key-executives", symbol=s)
    return [
        {"name": r.get("name"), "title": r.get("title"), "since": r.get("titleSince"),
         "age": None, "compensation": r.get("pay")}
        for r in (rows if isinstance(rows, list) else []) if r.get("name")
    ]


async def _fmp_target(s):
    rows = await p._fmp("/price-target-consensus", symbol=s)
    r = rows[0] if isinstance(rows, list) and rows else None
    if not r or not (r.get("targetConsensus") or r.get("targetMedian")):
        return None
    return {"mean": _f(r.get("targetConsensus")), "median": _f(r.get("targetMedian")),
            "high": _f(r.get("targetHigh")), "low": _f(r.get("targetLow")), "updatedAt": None}


# ====================== 2) CEO / ผู้บริหาร ======================
def _is_ceo(t):
    t = (t or "").lower()
    return "chief executive" in t or re.search(r"\bceo\b", t) is not None


@router.get("/{symbol}/executives")
async def executives(symbol: str):
    s = norm(symbol)
    d = await optional(cached(f"exec:{s}", 86400, lambda: p.finnhub("/stock/executive", symbol=s)))
    officers = [
        {"name": x.get("name"), "title": x.get("position"), "since": x.get("since"),
         "age": x.get("age"), "compensation": x.get("compensation")}
        for x in (d or {}).get("executive") or [] if x.get("name")
    ]
    src = "finnhub"
    if not officers:
        officers = await optional(cached(f"exec_y:{s}", 86400, _nonempty(f"exec_y:{s}", lambda: p._yahoo(_yf_officers, s), bool))) or []
        src = "yahoo"
    if not officers:
        officers = await optional(cached(f"exec_f:{s}", 86400, _nonempty(f"exec_f:{s}", lambda: _fmp_officers(s), bool))) or []
        src = "fmp"
    ceo = next((o for o in officers if _is_ceo(o["title"])), None)
    return {"ceo": ceo, "officers": officers[:12], "source": src if officers else None}


# ====================== 1) ผู้ถือหุ้น ======================
@router.get("/{symbol}/ownership")
async def ownership(symbol: str):
    s = norm(symbol)
    own, prof = await asyncio.gather(
        optional(cached(f"own:{s}", 86400, lambda: p.finnhub("/stock/ownership", symbol=s, limit=20))),
        optional(cached(f"profile:{s}", 86400, lambda: p.finnhub("/stock/profile2", symbol=s))),
    )
    shares_out = ((prof or {}).get("shareOutstanding") or 0) * 1e6
    holders = []
    for h in (own or {}).get("ownership") or []:
        sh = h.get("share")
        holders.append({
            "name": h.get("name"), "shares": sh,
            "percent": round(sh / shares_out * 100, 2) if sh and shares_out else None,
            "change": h.get("change"), "date": h.get("filingDate"),
        })
    if holders:
        holders.sort(key=lambda x: x["shares"] or 0, reverse=True)
        return {"institutionsPercent": None, "insidersPercent": None, "holders": holders, "source": "finnhub"}

    y = await optional(cached(f"own_y:{s}", 86400, _nonempty(f"own_y:{s}", lambda: p._yahoo(_yf_holders, s), lambda r: bool(r.get("holders")))))
    if y:
        return {**y, "source": "yahoo"}
    return {"institutionsPercent": None, "insidersPercent": None, "holders": [], "source": None}


# ====================== 3) บทวิเคราะห์ + ราคาเป้าหมาย ======================
@router.get("/{symbol}/analyst")
async def analyst(symbol: str):
    s = norm(symbol)
    rec, pt = await asyncio.gather(
        optional(cached(f"rec:{s}", 6 * 3600, lambda: p.finnhub("/stock/recommendation", symbol=s))),
        optional(cached(f"pt:{s}", 6 * 3600, lambda: p.finnhub("/stock/price-target", symbol=s))),
    )
    rating = None
    if rec:
        r = rec[0]
        rating = {k: r.get(k, 0) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")}
        rating["period"] = r.get("period")
    target = None
    if pt and pt.get("targetMean"):
        target = {"mean": pt.get("targetMean"), "median": pt.get("targetMedian"),
                  "high": pt.get("targetHigh"), "low": pt.get("targetLow"), "updatedAt": pt.get("lastUpdated")}

    if rating is None or target is None:  # เติมส่วนที่ขาดจาก Yahoo
        y = await optional(cached(f"an_y:{s}", 6 * 3600, _nonempty(f"an_y:{s}", lambda: p._yahoo(_yf_analyst, s), lambda r: bool(r.get("rating") or r.get("target"))))) or {}
        rating = rating or y.get("rating")
        target = target or y.get("target")
    if target is None:
        target = await optional(cached(f"pt_f:{s}", 6 * 3600, _nonempty(f"pt_f:{s}", lambda: _fmp_target(s), bool)))
    return {"rating": rating, "target": target}


# ====================== 4) ผู้บริหารซื้อขายหุ้น ======================
@router.get("/{symbol}/insiders")
async def insiders(symbol: str):
    s = norm(symbol)
    d = await optional(cached(f"ins:{s}", 3600, lambda: p.finnhub("/stock/insider-transactions", symbol=s)))
    out = []
    for t in (d or {}).get("data") or []:
        code = t.get("transactionCode")
        if code not in ("P", "S"):  # P = ซื้อในตลาด, S = ขายในตลาด
            continue
        qty = abs(t.get("change") or 0)
        price = t.get("transactionPrice") or 0
        if not qty:
            continue
        out.append({
            "name": t.get("name"), "title": None,
            "type": "BUY" if code == "P" else "SELL",
            "shares": qty, "price": price or None,
            "value": round(qty * price) if price else None,
            "date": t.get("transactionDate") or t.get("filingDate"),
        })
    if not out:
        out = await optional(cached(f"ins_y:{s}", 3600, _nonempty(f"ins_y:{s}", lambda: p._yahoo(_yf_insiders, s), bool))) or []
    out.sort(key=lambda x: x["date"] or "", reverse=True)
    return out[:30]



def _yf_raw(symbol):
    import yfinance as yf
    t = yf.Ticker(p._yf_sym(symbol))
    out = {}
    for name in ("info", "major_holders", "institutional_holders", "analyst_price_targets",
                 "recommendations_summary", "insider_transactions"):
        try:
            v = getattr(t, name)
            out[name] = {
                "type": type(v).__name__,
                "len": len(v) if hasattr(v, "__len__") else None,
                "keys": list(v.keys())[:6] if isinstance(v, dict) else None,
            }
        except Exception as e:
            out[name] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    return out


# ====================== วินิจฉัย (เปิดด้วย env INSIGHTS_DEBUG=1 แล้วลบทิ้งเมื่อเสร็จ) ======================
@router.get("/{symbol}/_debug")
async def insights_debug(symbol: str):
    if os.environ.get("INSIGHTS_DEBUG", "") != "1":
        raise HTTPException(404, "not_found")
    s = norm(symbol)

    async def probe(coro):
        try:
            r = await coro
            size = len(r) if hasattr(r, "__len__") else None
            return {"ok": True, "size": size, "sample": str(r)[:250]}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:250]}"}

    try:
        yf_ver = _md.version("yfinance")
    except Exception:
        yf_ver = "NOT INSTALLED"

    names = ["finnhub_executive", "finnhub_ownership", "finnhub_price_target",
             "yahoo_officers", "yahoo_holders", "yahoo_analyst", "fmp_officers", "fmp_target", "yahoo_raw"]
    results = await asyncio.gather(
        probe(p.finnhub("/stock/executive", symbol=s)),
        probe(p.finnhub("/stock/ownership", symbol=s, limit=5)),
        probe(p.finnhub("/stock/price-target", symbol=s)),
        probe(p._yahoo(_yf_officers, s)),
        probe(p._yahoo(_yf_holders, s)),
        probe(p._yahoo(_yf_analyst, s)),
        probe(_fmp_officers(s)),
        probe(_fmp_target(s)),
        probe(p._yahoo(_yf_raw, s)),
    )
    return {"yfinance_version": yf_ver, **dict(zip(names, results))}
