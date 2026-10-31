"""ตรวจและ normalize Strategy/Portfolio Spec (v1) — whitelist เท่านั้น ข้อความผิดพลาดเป็นภาษาไทยแสดงผู้ใช้ได้เลย

Spec v1 (พอร์ตสัดส่วนคงที่ + rebalance + ต้นทุน)
{
  "version": 1, "start": "2016-01-04", "end": "2026-10-27", "initial_capital": 100000,
  "positions": [{"symbol": "AAPL", "weight": 0.4}, ...],          # weight เป็นสัดส่วน 0-1, ผลรวม ≤ 1 ส่วนที่เหลือคือเงินสด
  "rebalance": {"mode": "none|calendar|threshold|hybrid", "frequency": "monthly|quarterly|annual", "threshold_pct": 5},
  "costs": {"commission_bps": 0, "slippage_bps": 5},
  "risk_free_annual": null                                         # null = ไม่คำนวณ Sharpe/Alpha มาตรฐาน (ไม่สมมติเอง)
}
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date
from typing import Any

from .. import config as C
from .rules import RuleError, validate_strategy

SYMBOL_RE = re.compile(r"^[A-Z][A-Z.\-]{0,9}$")
MODES = ("none", "calendar", "threshold", "hybrid")
FREQS = ("monthly", "quarterly", "annual")


class SpecError(ValueError):
    """Spec ไม่ถูกต้อง (ข้อความภาษาไทย)"""


def _num(x: Any, name: str, lo: float, hi: float) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise SpecError(f"{name} ต้องเป็นตัวเลข")
    v = float(x)
    if not math.isfinite(v) or v < lo or v > hi:
        raise SpecError(f"{name} ต้องอยู่ระหว่าง {lo:g} ถึง {hi:g}")
    return v


def _date(x: Any, name: str) -> date:
    try:
        return date.fromisoformat(str(x))
    except ValueError:
        raise SpecError(f"{name} ต้องเป็นวันที่รูปแบบ YYYY-MM-DD")


def validate_spec(raw: Any, today: date | None = None) -> dict:
    today = today or date.today()
    if not isinstance(raw, dict):
        raise SpecError("spec ต้องเป็น object")
    unknown = set(raw) - {"version", "start", "end", "initial_capital", "positions", "rebalance", "costs", "risk_free_annual", "strategy", "return_mode"}
    if unknown:
        raise SpecError(f"พบฟิลด์ที่ไม่รองรับ: {', '.join(sorted(map(str, unknown)))}")
    if raw.get("version", C.SPEC_VERSION) != C.SPEC_VERSION:
        raise SpecError(f"รองรับ spec version {C.SPEC_VERSION} เท่านั้น")

    start, end = _date(raw.get("start"), "start"), _date(raw.get("end"), "end")
    if start >= end:
        raise SpecError("start ต้องอยู่ก่อน end")
    if end > today:
        raise SpecError("end ต้องไม่เกินวันนี้")
    if (end - start).days > C.MAX_YEARS * 366:
        raise SpecError(f"ช่วงเวลายาวเกิน {C.MAX_YEARS} ปี")

    capital = _num(raw.get("initial_capital"), "initial_capital", C.MIN_CAPITAL, C.MAX_CAPITAL)

    pos_raw = raw.get("positions")
    if not isinstance(pos_raw, list) or not pos_raw:
        raise SpecError("ต้องระบุ positions อย่างน้อย 1 ตัว")
    if len(pos_raw) > C.MAX_SYMBOLS:
        raise SpecError(f"เลือกหุ้นได้สูงสุด {C.MAX_SYMBOLS} ตัวต่อการรัน")
    positions, seen = [], set()
    for i, p in enumerate(pos_raw):
        if not isinstance(p, dict) or set(p) - {"symbol", "weight"}:
            raise SpecError(f"positions[{i}] รูปแบบไม่ถูกต้อง")
        sym = str(p.get("symbol", "")).strip().upper()
        if not SYMBOL_RE.match(sym):
            raise SpecError(f"positions[{i}] สัญลักษณ์ไม่ถูกต้อง")
        if sym in seen:
            raise SpecError(f"สัญลักษณ์ซ้ำ: {sym}")
        seen.add(sym)
        w = _num(p.get("weight"), f"น้ำหนักของ {sym}", 1e-6, 1.0)
        positions.append({"symbol": sym, "weight": w})
    total = math.fsum(p["weight"] for p in positions)
    if total > 1.0 + 1e-9:
        raise SpecError(f"น้ำหนักรวม {total:.4f} เกิน 100%")

    rb = raw.get("rebalance") or {"mode": "none"}
    if not isinstance(rb, dict) or set(rb) - {"mode", "frequency", "threshold_pct"}:
        raise SpecError("rebalance รูปแบบไม่ถูกต้อง")
    mode = rb.get("mode", "none")
    if mode not in MODES:
        raise SpecError(f"rebalance.mode ต้องเป็นหนึ่งใน {', '.join(MODES)}")
    freq = rb.get("frequency")
    thr = rb.get("threshold_pct")
    if mode in ("calendar", "hybrid"):
        if freq not in FREQS:
            raise SpecError(f"rebalance.frequency ต้องเป็นหนึ่งใน {', '.join(FREQS)}")
    else:
        freq = None
    if mode in ("threshold", "hybrid"):
        thr = _num(thr, "rebalance.threshold_pct", 0.1, 50.0)
    else:
        thr = None

    costs = raw.get("costs") or {}
    if not isinstance(costs, dict) or set(costs) - {"commission_bps", "slippage_bps"}:
        raise SpecError("costs รูปแบบไม่ถูกต้อง")
    comm = _num(costs.get("commission_bps", C.DEFAULT_COMMISSION_BPS), "commission_bps", 0.0, C.MAX_COMMISSION_BPS)
    slip = _num(costs.get("slippage_bps", C.DEFAULT_SLIPPAGE_BPS), "slippage_bps", 0.0, C.MAX_SLIPPAGE_BPS)

    rf = raw.get("risk_free_annual")
    rf = None if rf is None else _num(rf, "risk_free_annual", 0.0, 0.5)

    out = {"version": C.SPEC_VERSION, "start": start.isoformat(), "end": end.isoformat(),
           "initial_capital": capital, "positions": positions,
           "rebalance": {"mode": mode, "frequency": freq, "threshold_pct": thr},
           "costs": {"commission_bps": comm, "slippage_bps": slip}, "risk_free_annual": rf}
    rm = raw.get("return_mode", "price")
    if rm not in ("price", "total"):
        raise SpecError("return_mode ต้องเป็น price (ไม่รวมปันผล) หรือ total (รวมปันผล)")
    if rm == "total":                                         # โหมด price ไม่ใส่ฟิลด์ -> spec/hash เหมือนเดิมทุกประการ
        out["return_mode"] = "total"
    if raw.get("strategy") is not None:                      # ไม่มี strategy -> spec/hash เหมือน B1 ทุกประการ
        try:
            out["strategy"] = validate_strategy(raw["strategy"])
        except RuleError as e:
            raise SpecError(f"strategy: {e}")
    return out


def spec_hash(spec: dict) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
