"""Phase 4: risk limits + alert history (stock-risk).

ไฟล์ใหม่ ไม่แก้ไฟล์เดิม ใช้ตาราง stock_risk_limits / stock_risk_alerts / audit_log
- GET  /api/stocks/risk/limits            อ่านลิมิตของผู้ใช้
- PUT  /api/stocks/risk/limits            แก้ลิมิต (เขียน audit_log ทุกฟิลด์ที่เปลี่ยน)
- POST /api/stocks/risk/alerts/evaluate   ประเมินลิมิตกับสถานะ ณ ราคาปิดล่าสุด เปิด/ปิด alert
- GET  /api/stocks/risk/alerts            ดูประวัติ alert

alert ทั้งหมดอิงสถานะ ณ ราคาปิดล่าสุด (as_of) ไม่ใช่ราคาสด
ถ้าข้อมูลยังไม่พร้อม จะไม่เปิดและไม่ปิด alert ใด ๆ (กันปิดผิดจากข้อมูลขาด)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from . import risk_exposure as X
from .db import sb
from .risk_api import _ctx, current_email
from .risk_ratelimit import make_limiter

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stocks/risk", tags=["stock-risk-alerts"])

# evaluate เรียก FMP/Yahoo ทุกครั้ง: จำกัด 5 ครั้ง/นาที/ผู้ใช้
_evaluate_limit = make_limiter(current_email, 5, 60, "evaluate")

LIMIT_FIELDS = ("max_drawdown", "max_single_weight", "max_hhi", "min_cash_weight")
MIN_DD_OBS = 20  # drawdown alert ต้องมีข้อมูลอย่างน้อยเท่านี้ ไม่งั้นข้าม


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num(x):
    return None if x is None else float(x)


# ------------------------------------------------------------------ limits
class LimitsIn(BaseModel):
    """ส่งเฉพาะฟิลด์ที่จะแก้ ส่ง null = ลบลิมิตข้อนั้น (ไม่เตือน)"""
    max_drawdown: float | None = Field(default=None, gt=0, le=1)
    max_single_weight: float | None = Field(default=None, gt=0, le=1)
    max_hhi: float | None = Field(default=None, gt=0, le=1)
    min_cash_weight: float | None = Field(default=None, ge=0, lt=1)


async def _get_limits(email: str) -> dict:
    rows = await sb("GET", "stock_risk_limits",
                    params={"email": f"eq.{email}", "select": "*"})
    return rows[0] if rows else {}


def _public_limits(row: dict) -> dict:
    return {k: _num(row.get(k)) for k in LIMIT_FIELDS}


@router.get("/limits")
async def get_limits(email: str = Depends(current_email)):
    row = await _get_limits(email)
    return {"limits": _public_limits(row), "updated_at": row.get("updated_at")}


@router.put("/limits")
async def put_limits(body: LimitsIn, email: str = Depends(current_email)):
    changes = {k: getattr(body, k) for k in body.model_fields_set if k in LIMIT_FIELDS}
    if not changes:
        raise HTTPException(400, "no_fields")
    old = await _get_limits(email)
    diff = {k: v for k, v in changes.items() if _num(old.get(k)) != v}
    if not diff:
        return {"ok": True, "changed": [], "limits": _public_limits(old), "audit_written": True}

    saved = await sb("POST", "stock_risk_limits",
                     params={"on_conflict": "email"},
                     json=[{"email": email, "updated_at": _now(), **diff}],
                     prefer="resolution=merge-duplicates,return=representation")
    new_row = saved[0] if saved else {**old, **diff}

    ts = _now()
    audit = [{"ts": ts, "actor": email, "event": "risk_limit_changed", "param": k,
              "old_value": _num(old.get(k)), "new_value": v} for k, v in diff.items()]
    audit_ok = True
    try:
        await sb("POST", "audit_log", json=audit, prefer="return=minimal")
    except HTTPException as e:  # ลิมิตบันทึกแล้ว แต่ audit พลาด ให้รู้ ไม่ปิดเงียบ
        audit_ok = False
        log.error("audit_log write failed for risk limits: %s", e.detail)
    return {"ok": True, "changed": sorted(diff), "limits": _public_limits(new_row),
            "audit_written": audit_ok}


# ------------------------------------------------------------------ evaluation
def _drawdown_metric(analysis: dict | None):
    """ดึง max_drawdown จาก analysis["tail"]["max_drawdown"] (โครงสร้างจริงของ /overview)
    คืน dict ของ metric หรือ None ถ้าไม่มีโครงสร้างนี้"""
    tail = (analysis or {}).get("tail")
    if not isinstance(tail, dict):
        return None
    md = tail.get("max_drawdown")
    return md if isinstance(md, dict) else None


def _find_conditions(exp: dict, analysis: dict | None, limits: dict):
    """คืน (found, evaluated, skipped)
    found: {(alert_type, symbol|""): cond}   เงื่อนไขที่ละเมิดลิมิตตอนนี้
    evaluated: ชนิดที่ประเมินได้จริง (ใช้ตัดสินว่า alert เก่าชนิดนั้นปิดได้)
    skipped: ชนิดที่ตั้งลิมิตแต่ข้อมูลไม่พอ (ไม่เปิดไม่ปิด)
    """
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

    # drawdown = max drawdown ของช่วงรายงาน (peak-to-trough) ไม่ใช่ drawdown ปัจจุบัน
    # อ่านจาก analysis["tail"]["max_drawdown"]
    # TODO: tail.current_drawdown ตรงกับความหมายของลิมิตมากกว่า ค่อยเปลี่ยนเมื่อเห็นรูปแบบค่าจริงจาก /metrics
    md = _drawdown_metric(analysis)
    if lim["max_drawdown"] is None:
        evaluated.add("drawdown")
    elif md is None:
        skipped.append({"alert_type": "drawdown", "reason": "analysis_unavailable"})
    elif md.get("status") != "ok" or md.get("value") is None:
        skipped.append({"alert_type": "drawdown",
                        "reason": md.get("reason") or md.get("status") or "drawdown_unavailable"})
    elif (md.get("n_obs") or 0) < MIN_DD_OBS:
        skipped.append({"alert_type": "drawdown",
                        "reason": f"insufficient_data: n_obs={md.get('n_obs') or 0} < {MIN_DD_OBS}"})
    else:
        evaluated.add("drawdown")
        dd = abs(float(md["value"]))
        if dd > lim["max_drawdown"]:
            found[("drawdown", "")] = {
                "alert_type": "drawdown", "symbol": None, "threshold": lim["max_drawdown"],
                "observed_value": dd,
                "detail": {"n_obs": md.get("n_obs"), "basis": "max drawdown over report period"}}

    return found, evaluated, skipped


def _plan(found: dict, evaluated: set, active_rows: list[dict]):
    active = {(r["alert_type"], r.get("symbol") or ""): r for r in active_rows}
    to_open = [c for k, c in found.items() if k not in active]
    to_update = [(active[k], c) for k, c in found.items() if k in active]
    to_resolve = [r for k, r in active.items() if k not in found and r["alert_type"] in evaluated]
    return to_open, to_update, to_resolve


@router.post("/alerts/evaluate")
async def evaluate(email: str = Depends(_evaluate_limit)):
    rep, ctx = await _ctx(email)
    meta = (rep or {}).get("meta", {}) if isinstance(rep, dict) else {}
    status, as_of = meta.get("data_status"), meta.get("as_of")
    if ctx is None or status not in ("ok", "ok_with_warnings") or not as_of:
        return {"evaluated": False, "reason": "data_not_ready", "data_status": status,
                "warnings": meta.get("warnings", [])}

    limits = await _get_limits(email)
    sectors = {s: "n/a" for s in ctx["holdings"]}  # ไม่ใช้ sector ที่นี่ ไม่เรียก Finnhub
    exp = X.exposure(ctx["holdings"], ctx["cash"], sectors)
    found, evaluated, skipped = _find_conditions(exp, rep.get("analysis"), limits)

    active_rows = await sb("GET", "stock_risk_alerts",
                           params={"email": f"eq.{email}", "status": "eq.active", "select": "*"}) or []
    to_open, to_update, to_resolve = _plan(found, evaluated, active_rows)

    opened = []
    for c in to_open:
        row = {"email": email, **c, "status": "active", "as_of": as_of}
        try:
            await sb("POST", "stock_risk_alerts", json=[row], prefer="return=minimal")
            opened.append({"alert_type": c["alert_type"], "symbol": c["symbol"]})
        except HTTPException as e:
            if e.status_code != 409:  # 409 = เปิดซ้ำพร้อมกัน unique index กันไว้แล้ว
                raise
    for r, c in to_update:
        await sb("PATCH", "stock_risk_alerts",
                 params={"id": f"eq.{r['id']}", "email": f"eq.{email}", "status": "eq.active"},
                 json={"observed_value": c["observed_value"], "threshold": c["threshold"],
                       "as_of": as_of, "detail": c["detail"]},
                 prefer="return=minimal")
    resolved = []
    for r in to_resolve:
        await sb("PATCH", "stock_risk_alerts",
                 params={"id": f"eq.{r['id']}", "email": f"eq.{email}", "status": "eq.active"},
                 json={"status": "resolved", "resolved_at": _now()},
                 prefer="return=minimal")
        resolved.append({"alert_type": r["alert_type"], "symbol": r.get("symbol")})

    return {"evaluated": True, "as_of": as_of, "data_status": status,
            "opened": opened, "updated": len(to_update), "resolved": resolved,
            "skipped": skipped, "warnings": meta.get("warnings", [])}


@router.get("/alerts")
async def list_alerts(status: str | None = None, limit: int = Query(50, ge=1, le=200),
                      email: str = Depends(current_email)):
    if status not in (None, "active", "resolved"):
        raise HTTPException(400, "bad_status")
    params = {"email": f"eq.{email}", "select": "*", "order": "opened_at.desc",
              "limit": str(limit)}
    if status:
        params["status"] = f"eq.{status}"
    rows = await sb("GET", "stock_risk_alerts", params=params) or []
    return {"alerts": rows}
