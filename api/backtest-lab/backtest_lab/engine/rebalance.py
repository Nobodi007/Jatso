"""ตรรกะวัน Rebalance (ตัดสินใจจากราคาปิดวัน t แล้วส่งคำสั่งที่ราคาเปิดวัน t+1 เท่านั้น -> ไม่มี look-ahead)

mode
  none       ไม่ปรับ น้ำหนักลอยตามราคา
  calendar   ปรับในวันทำการแรกหลังสิ้นงวด (เดือน/ไตรมาส/ปี)
  threshold  ปรับเมื่อน้ำหนักของหุ้นตัวใดเบี่ยงจากเป้าเกิน x เปอร์เซ็นต์พอยต์ (สัมบูรณ์)
  hybrid     ตรวจเฉพาะสิ้นงวด และปรับเมื่อมีตัวเกินเกณฑ์
เงินสดไม่นับเป็นตัวกระตุ้น (ดูเฉพาะหุ้น) และเงินสดไม่ได้ดอกเบี้ย
"""
from __future__ import annotations

from datetime import date


def _period_key(d: date, freq: str):
    if freq == "monthly":
        return (d.year, d.month)
    if freq == "quarterly":
        return (d.year, (d.month - 1) // 3)
    return (d.year,)


def is_period_end(today: date, next_trading_day: date | None, freq: str) -> bool:
    """วันนี้เป็นวันทำการสุดท้ายของงวดหรือไม่ (ดูจากวันทำการถัดไปในปฏิทินจริงของข้อมูล)"""
    if next_trading_day is None:
        return False
    return _period_key(today, freq) != _period_key(next_trading_day, freq)


def max_drift(weights: dict[str, float], targets: dict[str, float]) -> float:
    return max((abs(weights.get(s, 0.0) - t) for s, t in targets.items()), default=0.0)


def should_rebalance(mode: str, freq: str | None, thr_pct: float | None, today: date,
                     next_trading_day: date | None, weights: dict[str, float],
                     targets: dict[str, float]) -> str | None:
    """คืนเหตุผล ('calendar' | 'threshold' | 'hybrid') ถ้าต้องปรับ ไม่ใช่ None"""
    if mode == "none":
        return None
    if mode == "calendar":
        return "calendar" if is_period_end(today, next_trading_day, freq) else None
    if mode == "threshold":
        return "threshold" if max_drift(weights, targets) > thr_pct / 100.0 else None
    if mode == "hybrid":
        if is_period_end(today, next_trading_day, freq) and max_drift(weights, targets) > thr_pct / 100.0:
            return "hybrid"
        return None
    raise ValueError(mode)
