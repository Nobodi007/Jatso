"""Phase 4: risk limits + alert history (stock-risk).

ไฟล์ใหม่ ไม่แก้ไฟล์เดิม ใช้ตาราง stock_risk_limits / stock_risk_alerts / audit_log
- GET  /api/stocks/risk/limits            อ่านลิมิตของผู้ใช้
- PUT  /api/stocks/risk/limits            แก้ลิมิต (เขียน audit_log ทุกฟิลด์ที่เปลี่ยน)
- POST /api/stocks/risk/alerts/evaluate   ประเมินลิมิตกับสถานะ ณ ราคาปิดล่าสุด เปิด/ปิด alert
- GET  /api/stocks/risk/alerts            ดูประวัติ alert (กรอง status / acknowledged ได้)
- POST /api/stocks/risk/alerts/{id}/acknowledge  รับทราบ alert ที่ยัง active (ไม่ปิด alert)

กฎ 9 ข้อ: drawdown, single_weight, hhi, low_cash, sector_weight, daily_loss, volatility,
tracking_error, stale_data (earnings ยังไม่ทำ: ยังไม่ยืนยันแหล่งข้อมูล)
ลิมิตของผู้ใช้ที่ยังไม่มีแถวเลยใช้ค่าเริ่มต้น DEFAULT_LIMITS (GET /limits ระบุ source ว่า default/custom/off)

alert ทั้งหมดอิงสถานะ ณ ราคาปิดล่าสุด (as_of) ไม่ใช่ราคาสด
ถ้าข้อมูลยังไม่พร้อม จะไม่เปิดและไม่ปิด alert ใด ๆ (กันปิดผิดจากข้อมูลขาด)
ยกเว้นไม่มีเทรด active เลย (no_activity เช่นหลัง Soft Reset): ไม่มีอะไรละเมิดลิมิตได้ ปิดทั้งหมด
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from . import risk_data as rd
from . import risk_exposure as X
from .cache import ProviderError, RateLimited
from .db import sb
from .ledger import ET
from .risk_api import STALE_AFTER_DAYS, _report, current_email
from .risk_ratelimit import make_limiter

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stocks/risk", tags=["stock-risk-alerts"])

# evaluate เรียก FMP/Yahoo ทุกครั้ง: จำกัด 5 ครั้ง/นาที/ผู้ใช้
_evaluate_limit = make_limiter(current_email, 5, 60, "evaluate")
_limits_write = make_limiter(current_email, 20, 60, "limits")

LIMIT_FIELDS = ("max_drawdown", "max_single_weight", "max_hhi", "min_cash_weight",
                "max_sector_weight", "max_daily_loss", "max_volatility", "max_tracking_error")
ALERT_TYPES = ("drawdown", "single_weight", "hhi", "low_cash",
               "sector_weight", "daily_loss", "volatility", "tracking_error", "stale_data")
# ค่าเริ่มต้นสำหรับผู้ใช้ที่ยังไม่เคยตั้งลิมิตเลย (ตัวอย่างทั่วไป ไม่ใช่คำแนะนำการลงทุน: ผู้ใช้ปรับได้)
DEFAULT_LIMITS = {"max_drawdown": 0.20, "max_single_weight": 0.25, "max_hhi": 0.40, "min_cash_weight": 0.05,
                  "max_sector_weight": 0.40, "max_daily_loss": 0.03, "max_volatility": 0.30,
                  "max_tracking_error": 0.10}
SEVERITIES = ("info", "warning", "critical")
_SEV_RANK = {s: i for i, s in enumerate(SEVERITIES)}
CRITICAL_RATIO = 1.25  # ค่าที่วัดได้เลยลิมิตตั้งแต่ 25% ขึ้นไป = critical (low_cash กลับด้าน)
NON_SECTOR = ("Unknown", "n/a")
MIN_DD_OBS = 20  # drawdown alert ต้องมีข้อมูลอย่างน้อยเท่านี้ ไม่งั้นข้าม
# risk_engine ติดป้าย limited_sample ให้ drawdown ทุกค่าที่มีน้อยกว่า 250 observation (ค่ายังคำนวณได้ปกติ)
# ถ้าข้ามเพราะป้ายนี้ alert drawdown จะเงียบไปเกือบปี จึงรับทั้งสองสถานะ แล้วกันด้วย MIN_DD_OBS แทน
DD_OK_STATUSES = ("ok", "limited_sample")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num(x):
    return None if x is None else float(x)

def _same(a, b) -> bool:
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) < 1e-9)


# ------------------------------------------------------------------ limits
class LimitsIn(BaseModel):
    """ส่งเฉพาะฟิลด์ที่จะแก้ ส่ง null = ลบลิมิตข้อนั้น (ไม่เตือน) ช่วงค่าตรงกับ CHECK ใน DB"""
    max_drawdown: float | None = Field(default=None, gt=0, le=1)
    max_single_weight: float | None = Field(default=None, gt=0, le=1)
    max_hhi: float | None = Field(default=None, gt=0, le=1)
    min_cash_weight: float | None = Field(default=None, ge=0, lt=1)
    max_sector_weight: float | None = Field(default=None, gt=0, le=1)
    max_daily_loss: float | None = Field(default=None, gt=0, le=1)
    max_volatility: float | None = Field(default=None, gt=0, le=5)
    max_tracking_error: float | None = Field(default=None, gt=0, le=5)


async def _get_limits(email: str) -> dict:
    rows = await sb("GET", "stock_risk_limits",
                    params={"email": f"eq.{email}", "select": "*"})
    return rows[0] if rows else {}


def _public_limits(row: dict) -> dict:
    return {k: _num(row.get(k)) for k in LIMIT_FIELDS}


def _effective_limits(row: dict) -> dict:
    """ไม่มีแถวเลย = ผู้ใช้ยังไม่เคยตั้ง ใช้ค่าเริ่มต้น / มีแถวแล้ว null = ผู้ใช้ปิดลิมิตข้อนั้น"""
    return dict(DEFAULT_LIMITS) if not row else _public_limits(row)


def _limit_sources(row: dict) -> dict:
    if not row:
        return {k: "default" for k in LIMIT_FIELDS}
    return {k: ("custom" if row.get(k) is not None else "off") for k in LIMIT_FIELDS}


@router.get("/limits")
async def get_limits(email: str = Depends(current_email)):
    row = await _get_limits(email)
    return {"limits": _effective_limits(row), "source": _limit_sources(row),
            "defaults": dict(DEFAULT_LIMITS), "updated_at": row.get("updated_at")}


@router.put("/limits")
async def put_limits(body: LimitsIn, email: str = Depends(_limits_write)):
    changes = {k: getattr(body, k) for k in body.model_fields_set if k in LIMIT_FIELDS}
    if not changes:
        raise HTTPException(400, "no_fields")
    old = await _get_limits(email)
    old_eff = _effective_limits(old)
    diff = {k: v for k, v in changes.items() if not _same(old_eff.get(k), v)}
    if not diff:
        return {"ok": True, "changed": [], "limits": old_eff, "source": _limit_sources(old),
                "seeded_defaults": [], "audit_written": True}

    # ผู้ใช้ยังไม่มีแถว: บันทึกค่าเริ่มต้นของข้ออื่นลงไปด้วย ไม่งั้นการแก้ข้อเดียวจะปิดข้ออื่นเงียบ ๆ
    seeded = {k: v for k, v in DEFAULT_LIMITS.items() if k not in diff} if not old else {}
    saved = await sb("POST", "stock_risk_limits",
                     params={"on_conflict": "email"},
                     json=[{"email": email, "updated_at": _now(), **seeded, **diff}],
                     prefer="resolution=merge-duplicates,return=representation")
    new_row = saved[0] if saved else {**old, **seeded, **diff}

    ts = _now()
    audit = [{"ts": ts, "actor": email, "event": "risk_limit_changed", "param": k,
              "old_value": _num(old_eff.get(k)), "new_value": v} for k, v in diff.items()]
    audit += [{"ts": ts, "actor": email, "event": "risk_limit_default_seeded", "param": k,
               "old_value": None, "new_value": v} for k, v in seeded.items()]
    audit_ok = True
    try:
        await sb("POST", "audit_log", json=audit, prefer="return=minimal")
    except HTTPException as e:  # ลิมิตบันทึกแล้ว แต่ audit พลาด ให้รู้ ไม่ปิดเงียบ
        audit_ok = False
        log.error("audit_log write failed for risk limits: %s", e.detail)
    return {"ok": True, "changed": sorted(diff), "limits": _public_limits(new_row),
            "source": _limit_sources(new_row), "seeded_defaults": sorted(seeded),
            "audit_written": audit_ok}


# ------------------------------------------------------------------ evaluation
def _severity(alert_type: str, observed, threshold) -> str:
    """critical เมื่อเลยลิมิตตั้งแต่ CRITICAL_RATIO เท่า (low_cash: ต่ำกว่าลิมิต/CRITICAL_RATIO) ไม่งั้น warning"""
    if observed is None or threshold is None:
        return "warning"
    if alert_type == "low_cash":
        return "critical" if observed <= threshold / CRITICAL_RATIO else "warning"
    return "critical" if threshold > 0 and observed >= threshold * CRITICAL_RATIO else "warning"


def _drawdown_metrics(analysis: dict | None):
    """คืน (current_drawdown, max_drawdown) จาก analysis["tail"] เป็น dict ของ Metric หรือ None"""
    tail = (analysis or {}).get("tail")
    if not isinstance(tail, dict):
        return None, None
    cur, mx = tail.get("current_drawdown"), tail.get("max_drawdown")
    return (cur if isinstance(cur, dict) else None), (mx if isinstance(mx, dict) else None)


def _find_conditions(exp: dict, analysis: dict | None, limits: dict, extras: dict | None = None):
    """คืน (found, evaluated, skipped)
    found: {(alert_type, symbol|""): cond}   เงื่อนไขที่ละเมิดลิมิตตอนนี้
    evaluated: ชนิดที่ประเมินได้จริง (ใช้ตัดสินว่า alert เก่าชนิดนั้นปิดได้)
    skipped: ชนิดที่ตั้งลิมิตแต่ข้อมูลไม่พอ (ไม่เปิดไม่ปิด)
    extras (ไม่ส่ง = กฎใหม่ที่ต้องใช้ข้อมูลเสริมจะไม่ถูกประเมิน ไม่เปิดไม่ปิด):
      sector_fetched: bool            exp["sectors"] มาจากการดึง sector จริง (ไม่ใช่ "n/a")
      daily_return: {date, value}|None  ผลตอบแทน NAV ของวันล่าสุด
      data: {freshness, days_old, missing: [{code, symbol}]}  สุขภาพข้อมูล สำหรับ stale_data
    """
    ex = extras or {}
    lim = {k: _num(limits.get(k)) for k in LIMIT_FIELDS}
    found: dict = {}
    evaluated: set = set()
    skipped: list = []

    # น้ำหนักตัวเดียว (ต่อ NAV)
    evaluated.add("single_weight")
    if lim["max_single_weight"] is not None:
        for p in exp.get("positions", []):
            w = p.get("weight_nav")
            if w is not None and w > lim["max_single_weight"]:
                found[("single_weight", p["symbol"])] = {
                    "alert_type": "single_weight", "symbol": p["symbol"],
                    "threshold": lim["max_single_weight"], "observed_value": w,
                    "detail": {"market_value": p.get("market_value"), "basis": "weight_nav"}}

    # HHI (น้ำหนักในกลุ่มหุ้น)
    h = exp.get("hhi") or {}
    if lim["max_hhi"] is None:
        evaluated.add("hhi")
    elif h.get("status") == "ok" and h.get("value") is not None:
        evaluated.add("hhi")
        if h["value"] > lim["max_hhi"]:
            found[("hhi", "")] = {
                "alert_type": "hhi", "symbol": None, "threshold": lim["max_hhi"],
                "observed_value": h["value"],
                "detail": {"n_positions": h.get("n_obs"), "basis": "equity weights"}}
    elif not exp.get("positions"):
        evaluated.add("hhi")  # ไม่มีตำแหน่งหุ้น: ไม่มีอะไรละเมิดได้ alert hhi เก่าปิดได้
    else:
        skipped.append({"alert_type": "hhi", "reason": h.get("reason") or h.get("status")})

    # เงินสดต่ำ
    cw = exp.get("cash_weight")
    if lim["min_cash_weight"] is None:
        evaluated.add("low_cash")
    elif cw is not None:
        evaluated.add("low_cash")
        if cw < lim["min_cash_weight"]:
            found[("low_cash", "")] = {
                "alert_type": "low_cash", "symbol": None, "threshold": lim["min_cash_weight"],
                "observed_value": cw, "detail": {"basis": "cash / NAV"}}
    else:
        skipped.append({"alert_type": "low_cash", "reason": "cash_weight_unavailable"})

    # drawdown = ขาดทุนปัจจุบันจากจุดสูงสุดของช่วงรายงาน (tail.current_drawdown) กลับขึ้นมาแล้ว alert ปิดเอง
    # ไม่ใช้ max drawdown ของช่วง เพราะละเมิดครั้งเดียวแล้วค่านั้นค้างอยู่ทั้งปี alert จะไม่มีวันปิด
    # max drawdown ของช่วงเก็บไว้ใน detail เป็นข้อมูลประกอบ
    cur, mx = _drawdown_metrics(analysis)
    if lim["max_drawdown"] is None:
        evaluated.add("drawdown")
    elif cur is None:
        skipped.append({"alert_type": "drawdown", "reason": "analysis_unavailable"})
    elif cur.get("status") not in DD_OK_STATUSES or cur.get("value") is None:
        skipped.append({"alert_type": "drawdown",
                        "reason": cur.get("reason") or cur.get("status") or "drawdown_unavailable"})
    elif (cur.get("n_obs") or 0) < MIN_DD_OBS:
        skipped.append({"alert_type": "drawdown",
                        "reason": f"insufficient_data: n_obs={cur.get('n_obs') or 0} < {MIN_DD_OBS}"})
    else:
        evaluated.add("drawdown")
        dd = abs(float(cur["value"]))
        if dd > lim["max_drawdown"]:
            found[("drawdown", "")] = {
                "alert_type": "drawdown", "symbol": None, "threshold": lim["max_drawdown"],
                "observed_value": dd,
                "detail": {"n_obs": cur.get("n_obs"), "basis": "current drawdown from peak over report period",
                           "max_drawdown_period": None if not mx else mx.get("value")}}

    perf = (analysis or {}).get("performance") if isinstance(analysis, dict) else None

    # sector (Finnhub industry ไม่ใช่ GICS) alert ที่เจอแล้วใช้ได้เสมอ (น้ำหนัก sector ที่รู้ชัดเป็นค่าจริงอย่างน้อย)
    # แต่ถ้ามีหุ้นที่ไม่รู้ sector ห้ามถือว่า "ไม่เกิน" จึงไม่ปิด alert เก่า
    if lim["max_sector_weight"] is None:
        evaluated.add("sector_weight")
    elif not ex.get("sector_fetched"):
        pass
    else:
        secs = exp.get("sectors") or []
        for r in secs:
            if r["sector"] in NON_SECTOR:
                continue
            if r["weight_nav"] > lim["max_sector_weight"]:
                found[("sector_weight", r["sector"])] = {
                    "alert_type": "sector_weight", "symbol": None, "sector": r["sector"],
                    "threshold": lim["max_sector_weight"], "observed_value": r["weight_nav"],
                    "detail": {"market_value": r.get("market_value"), "basis": "weight_nav",
                               "classification": "Finnhub industry (not GICS); approximate"}}
        if any(r["sector"] in NON_SECTOR for r in secs):
            skipped.append({"alert_type": "sector_weight", "reason": "sector_unavailable_for_some_holdings"})
        else:
            evaluated.add("sector_weight")

    # ขาดทุนรายวัน: ผลตอบแทน NAV ของ session ล่าสุด (ไม่ใช่ราคาสด)
    if lim["max_daily_loss"] is None:
        evaluated.add("daily_loss")
    elif "daily_return" not in ex:
        pass
    elif ex["daily_return"] is None:
        skipped.append({"alert_type": "daily_loss", "reason": "daily_return_unavailable"})
    else:
        evaluated.add("daily_loss")
        dr = ex["daily_return"]
        loss = -float(dr["value"]) if dr["value"] < 0 else 0.0
        if loss > lim["max_daily_loss"]:
            found[("daily_loss", "")] = {
                "alert_type": "daily_loss", "symbol": None, "threshold": lim["max_daily_loss"],
                "observed_value": loss,
                "detail": {"date": dr.get("date"), "basis": "latest session NAV return"}}

    # ความผันผวน / tracking error (annualized) ต้องมี observation อย่างน้อย MIN_DD_OBS
    for a_type, field, key, basis in (
            ("volatility", "max_volatility", "volatility", "annualized volatility of portfolio returns"),
            ("tracking_error", "max_tracking_error", "tracking_error", "annualized tracking error vs benchmark")):
        if lim[field] is None:
            evaluated.add(a_type)
            continue
        m = (perf or {}).get(key)
        if not isinstance(m, dict):
            skipped.append({"alert_type": a_type, "reason": "analysis_unavailable"})
        elif m.get("status") not in DD_OK_STATUSES or m.get("value") is None:
            skipped.append({"alert_type": a_type, "reason": m.get("reason") or m.get("status") or f"{key}_unavailable"})
        elif (m.get("n_obs") or 0) < MIN_DD_OBS:
            skipped.append({"alert_type": a_type,
                            "reason": f"insufficient_data: n_obs={m.get('n_obs') or 0} < {MIN_DD_OBS}"})
        else:
            evaluated.add(a_type)
            v = float(m["value"])
            if v > lim[field]:
                found[(a_type, "")] = {
                    "alert_type": a_type, "symbol": None, "threshold": lim[field], "observed_value": v,
                    "detail": {"n_obs": m.get("n_obs"), "basis": basis}}

    # ข้อมูลเก่า/ขาด: เปิดตลอด ไม่มีลิมิตให้ตั้ง (threshold = จำนวนวันที่ยอมรับได้ STALE_AFTER_DAYS)
    d = ex.get("data")
    if isinstance(d, dict) and d.get("days_old") is not None:
        evaluated.add("stale_data")
        stale = d.get("freshness") == "stale"
        missing = d.get("missing") or []
        if stale or missing:
            days = d["days_old"]
            found[("stale_data", "")] = {
                "alert_type": "stale_data", "symbol": None, "threshold": float(STALE_AFTER_DAYS),
                "observed_value": float(days),
                "severity": "critical" if stale and days >= 2 * STALE_AFTER_DAYS else "warning",
                "detail": {"stale": stale, "missing": missing, "basis": "calendar days since last close"}}

    for c in found.values():
        c.setdefault("severity", _severity(c["alert_type"], c["observed_value"], c["threshold"]))
        c.setdefault("sector", None)

    return found, evaluated, skipped


async def _fetch_sectors(symbols: list[str]) -> dict:
    """Finnhub industry ต่อสัญลักษณ์ (cache 7 วันใน risk_data) ดึงไม่ได้ = None (ไม่เดา)"""
    async def one(sym):
        try:
            return await rd.sector(sym)
        except (ProviderError, RateLimited):
            return None
    got = await asyncio.gather(*[one(x) for x in symbols])
    return dict(zip(symbols, got))


def _last_daily_return(nav_series) -> dict | None:
    if not isinstance(nav_series, list) or len(nav_series) < 2:
        return None
    a, b = nav_series[-2], nav_series[-1]
    try:
        prev, cur = float(a["nav"]), float(b["nav"])
    except (KeyError, TypeError, ValueError):
        return None
    if prev <= 0:
        return None
    return {"date": b.get("date"), "value": cur / prev - 1.0}


_MISSING_CODES = ("prices_unavailable", "benchmark_unavailable", "position_unpriced")


def _data_health(meta: dict, ctx: dict, as_of: str | None) -> dict | None:
    try:
        days_old = (datetime.now(ET).date() - date.fromisoformat(as_of)).days
    except (TypeError, ValueError):
        return None
    ws = list(meta.get("warnings") or []) + list(ctx.get("skipped") or [])
    missing = [{"code": w.get("code"), "symbol": w.get("symbol")} for w in ws
               if isinstance(w, dict) and w.get("code") in _MISSING_CODES]
    return {"freshness": meta.get("freshness"), "days_old": max(days_old, 0), "missing": missing}


def _plan(found: dict, evaluated: set, active_rows: list[dict]):
    active = {(r["alert_type"], r.get("symbol") or r.get("sector") or ""): r for r in active_rows}
    to_open = [c for k, c in found.items() if k not in active]
    to_update = [(active[k], c) for k, c in found.items() if k in active]
    to_resolve = [r for k, r in active.items() if k not in found and r["alert_type"] in evaluated]
    return to_open, to_update, to_resolve


@router.post("/alerts/evaluate")
async def evaluate(email: str = Depends(_evaluate_limit)):
    rep = await _report(email)
    ctx = rep.get("exposure_ctx")
    meta = rep.get("meta", {})
    status, as_of = meta.get("data_status"), meta.get("as_of")

    if status == "no_activity":
        # ไม่มีเทรด active เลย (เช่น หลัง Soft Reset): ไม่มีอะไรละเมิดลิมิตได้ ปิด alert ที่ค้างทั้งหมด
        found, evaluated, skipped = {}, set(ALERT_TYPES), []
    elif ctx is None or status not in ("ok", "ok_with_warnings") or not as_of:
        return {"evaluated": False, "reason": "data_not_ready", "data_status": status,
                "warnings": meta.get("warnings", [])}
    else:
        limits = _effective_limits(await _get_limits(email))
        # เรียก Finnhub เฉพาะเมื่อผู้ใช้ตั้งลิมิต sector (ประหยัดโควตา) ผลถูก cache 7 วันใน risk_data
        sector_fetched = limits.get("max_sector_weight") is not None and bool(ctx["holdings"])
        sectors = (await _fetch_sectors(list(ctx["holdings"])) if sector_fetched
                   else {s: "n/a" for s in ctx["holdings"]})
        exp = X.exposure(ctx["holdings"], ctx["cash"], sectors)
        extras = {"sector_fetched": sector_fetched,
                  "daily_return": _last_daily_return(rep.get("nav_series")),
                  "data": _data_health(meta, ctx, as_of)}
        found, evaluated, skipped = _find_conditions(exp, rep.get("analysis"), limits, extras)

    active_rows = await sb("GET", "stock_risk_alerts",
                           params={"email": f"eq.{email}", "status": "eq.active", "select": "*"}) or []
    to_open, to_update, to_resolve = _plan(found, evaluated, active_rows)

    opened = []
    for c in to_open:
        row = {"email": email, **c, "status": "active", "as_of": as_of}
        try:
            await sb("POST", "stock_risk_alerts", json=[row], prefer="return=minimal")
            opened.append({"alert_type": c["alert_type"], "symbol": c["symbol"],
                           "sector": c.get("sector"), "severity": c["severity"]})
        except HTTPException as e:
            if e.status_code != 409:  # 409 = เปิดซ้ำพร้อมกัน unique index กันไว้แล้ว
                raise
    for r, c in to_update:
        patch = {"observed_value": c["observed_value"], "threshold": c["threshold"],
                 "as_of": as_of, "detail": c["detail"], "severity": c["severity"]}
        if _SEV_RANK.get(c["severity"], 0) > _SEV_RANK.get(r.get("severity"), 0):
            patch["acknowledged_at"] = None  # รุนแรงขึ้น: ต้องให้ผู้ใช้รับทราบใหม่
        await sb("PATCH", "stock_risk_alerts",
                 params={"id": f"eq.{r['id']}", "email": f"eq.{email}", "status": "eq.active"},
                 json=patch, prefer="return=minimal")
    resolved = []
    for r in to_resolve:
        await sb("PATCH", "stock_risk_alerts",
                 params={"id": f"eq.{r['id']}", "email": f"eq.{email}", "status": "eq.active"},
                 json={"status": "resolved", "resolved_at": _now()},
                 prefer="return=minimal")
        resolved.append({"alert_type": r["alert_type"], "symbol": r.get("symbol"),
                         "sector": r.get("sector")})

    return {"evaluated": True, "as_of": as_of, "data_status": status,
            "opened": opened, "updated": len(to_update), "resolved": resolved,
            "skipped": skipped, "warnings": meta.get("warnings", [])}


@router.get("/alerts")
async def list_alerts(status: str | None = None, acknowledged: bool | None = None,
                      limit: int = Query(50, ge=1, le=200), email: str = Depends(current_email)):
    if status not in (None, "active", "resolved"):
        raise HTTPException(400, "bad_status")
    params = {"email": f"eq.{email}", "select": "*", "order": "opened_at.desc",
              "limit": str(limit)}
    if status:
        params["status"] = f"eq.{status}"
    if acknowledged is not None:
        params["acknowledged_at"] = "not.is.null" if acknowledged else "is.null"
    rows = await sb("GET", "stock_risk_alerts", params=params) or []
    return {"alerts": rows}


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int, email: str = Depends(_limits_write)):
    """รับทราบ alert ที่ยัง active ของตัวเองเท่านั้น (กรอง email จาก JWT) ไม่ปิด alert: ปิดได้เฉพาะตอนเงื่อนไขหาย"""
    rows = await sb("PATCH", "stock_risk_alerts",
                    params={"id": f"eq.{alert_id}", "email": f"eq.{email}", "status": "eq.active",
                            "acknowledged_at": "is.null"},
                    json={"acknowledged_at": _now()}, prefer="return=representation")
    if rows:
        return {"ok": True, "alert": rows[0]}
    cur = await sb("GET", "stock_risk_alerts",
                   params={"id": f"eq.{alert_id}", "email": f"eq.{email}", "select": "id,status,acknowledged_at"})
    if not cur:
        raise HTTPException(404, "alert_not_found")
    if cur[0].get("status") != "active":
        raise HTTPException(409, "alert_not_active")
    return {"ok": True, "already_acknowledged": True}
