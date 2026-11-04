"""ตรวจ spec ของโหมดทยอยสะสม (DCA / Buy-the-dip) — whitelist เท่านั้น ข้อความผิดพลาดเป็นภาษาไทย

"accumulate": {
  "contribution": {"amount": 1000, "frequency": "weekly|monthly|quarterly"} | null,   # เงินใหม่เข้าพอร์ต วันทำการแรกของงวด (ไม่รวมวันแรก) แบ่งเข้าช่องตามน้ำหนักเป้าหมาย
  "schedule":     {"amount": 1000, "frequency": "monthly"} | null,                     # DCA: ซื้อรวมต่องวด (แบ่งตามน้ำหนัก) จากเงินสดในช่อง
  "dip":          {"drop_pct": 20, "lookback_days": 252, "amount": 2000, "cooldown_days": 21} | null,   # ซื้อต่อหุ้นต่อครั้ง เมื่อปิดต่ำกว่าสูงสุด N วันทำการ ≥ drop_pct
  "when": <เงื่อนไขภาษากฎเดียวกับ entry> | null,                                        # ต้องจริงด้วย (AND) จึงจะซื้อ เช่น close < EMA200
  "max_invested_per_stock": 20000 | null,                                              # เพดานเงินซื้อสะสมต่อหุ้น (รวมค่าคอม)
  "initial_invest_pct": 0                                                              # % ของเงินช่องที่ลงทันทีที่เปิดวันแรก
}
"""
from __future__ import annotations

import math
from typing import Any

from . import rules
from .rules import RuleError, validate_strategy

FREQS = ("weekly", "monthly", "quarterly")
MAX_AMOUNT = 1e9


class AccumError(ValueError):
    """accumulate ไม่ถูกต้อง (ข้อความภาษาไทย)"""


def _num(x: Any, name: str, lo: float, hi: float, integer: bool = False) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise AccumError(f"{name} ต้องเป็นตัวเลข")
    if not (lo <= x <= hi):
        raise AccumError(f"{name} ต้องอยู่ระหว่าง {lo:g} ถึง {hi:g}")
    if integer and float(x) != int(x):
        raise AccumError(f"{name} ต้องเป็นจำนวนเต็ม")
    return int(x) if integer else float(x)


def _block(raw: Any, name: str, allowed: set[str]) -> dict:
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise AccumError(f"{name} รูปแบบไม่ถูกต้อง (ฟิลด์ที่รองรับ: {', '.join(sorted(allowed))})")
    return raw


def _freq(raw: dict, name: str) -> str:
    f = raw.get("frequency")
    if f not in FREQS:
        raise AccumError(f"{name}.frequency ต้องเป็นหนึ่งใน {', '.join(FREQS)}")
    return f


def validate_accumulate(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise AccumError("accumulate ต้องเป็น object")
    extra = set(raw) - {"contribution", "schedule", "dip", "when", "max_invested_per_stock", "initial_invest_pct"}
    if extra:
        raise AccumError(f"accumulate มีฟิลด์ที่ไม่รองรับ: {', '.join(sorted(extra))}")
    out: dict = {"contribution": None, "schedule": None, "dip": None, "when": None,
                 "max_invested_per_stock": None, "initial_invest_pct": 0.0}
    c = raw.get("contribution")
    if c is not None:
        c = _block(c, "contribution", {"amount", "frequency"})
        out["contribution"] = {"amount": _num(c.get("amount"), "contribution.amount", 1.0, MAX_AMOUNT), "frequency": _freq(c, "contribution")}
    s = raw.get("schedule")
    if s is not None:
        s = _block(s, "schedule", {"amount", "frequency"})
        out["schedule"] = {"amount": _num(s.get("amount"), "schedule.amount", 1.0, MAX_AMOUNT), "frequency": _freq(s, "schedule")}
    d = raw.get("dip")
    if d is not None:
        d = _block(d, "dip", {"drop_pct", "lookback_days", "amount", "cooldown_days"})
        out["dip"] = {"drop_pct": _num(d.get("drop_pct"), "dip.drop_pct", 1.0, 90.0),
                      "lookback_days": _num(d.get("lookback_days", 252), "dip.lookback_days", 20, 1000, True),
                      "amount": _num(d.get("amount"), "dip.amount", 1.0, MAX_AMOUNT),
                      "cooldown_days": _num(d.get("cooldown_days", 21), "dip.cooldown_days", 1, 252, True)}
    if raw.get("when") is not None:
        try:
            out["when"] = validate_strategy({"entry": raw["when"]})["entry"]
        except RuleError as e:
            raise AccumError(f"when: {str(e).replace('entry', 'when')}")
    if raw.get("max_invested_per_stock") is not None:
        out["max_invested_per_stock"] = _num(raw["max_invested_per_stock"], "max_invested_per_stock", 1.0, MAX_AMOUNT)
    out["initial_invest_pct"] = _num(raw.get("initial_invest_pct", 0), "initial_invest_pct", 0.0, 100.0)
    if out["schedule"] is None and out["dip"] is None and out["initial_invest_pct"] <= 0:
        raise AccumError("ต้องมีอย่างน้อยหนึ่งอย่าง: schedule (DCA), dip (ซื้อตอนย่อ) หรือ initial_invest_pct > 0 ไม่เช่นนั้นจะไม่ซื้ออะไรเลย")
    return out


def accumulate_warmup(acc: dict) -> int:
    w = 0
    if acc.get("dip"):
        w = acc["dip"]["lookback_days"] + 2
    if acc.get("when") is not None:
        w = max(w, rules.warmup_bars({"entry": acc["when"], "exit": None}))
    return w


def spec_warmup(spec: dict) -> int:
    """จำนวนแท่งก่อนวันเริ่มที่ต้องดึงเพิ่ม (กลยุทธ์ หรือ ทยอยสะสม)"""
    if spec.get("accumulate"):
        return accumulate_warmup(spec["accumulate"])
    if spec.get("strategy"):
        return rules.warmup_bars(spec["strategy"])
    return 0
