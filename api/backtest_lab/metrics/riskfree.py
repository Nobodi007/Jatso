"""อัตราดอกเบี้ยไร้ความเสี่ยงรายวันจากอัตรา T-bill 3 เดือน (รายปี, ทศนิยม)

คัดลอกกติกาจาก Risk Center (_daily_rf ใน risk_api.py) เป็นโค้ดของแพ็กเกจนี้เอง ไม่ import:
- ผลตอบแทนของวัน t ใช้ yield ล่าสุดที่สังเกตได้ "ในหรือก่อนวันทำการก่อนหน้า" (t-1) -> ไม่มี look-ahead
- ถ้าไม่มี yield ก่อนวันแรก หรือช่องว่างเกิน max_gap วันปฏิทิน -> คืน None (Sharpe/Alpha = unavailable) ไม่เดาค่า
"""
from __future__ import annotations

from datetime import date
from typing import Mapping, Sequence

from . import core as M

MAX_GAP_DAYS = 7


def daily_rf(rates: Mapping[date, float] | None, dates: Sequence[date], max_gap: int = MAX_GAP_DAYS) -> list[float] | None:
    """dates = [base_date, d1..dN] (ยาว N+1) -> คืนรายการยาว N หรือ None"""
    if not rates:
        return None
    keys, out, j = sorted(rates), [], -1
    for i in range(1, len(dates)):
        ref = dates[i - 1]
        while j + 1 < len(keys) and keys[j + 1] <= ref:
            j += 1
        if j < 0 or (ref - keys[j]).days > max_gap:
            return None
        out.append(M.daily_rate(rates[keys[j]]))
    return out


def describe(rates: Mapping[date, float] | None, dates: Sequence[date], rf: list[float] | None) -> dict:
    """สรุปสำหรับแสดงในผลลัพธ์ (ค่าเฉลี่ยรายปีที่ใช้จริง = ค่าเฉลี่ยของ rate รายวันแปลงกลับ)"""
    if rf is None:
        return {"source": "tbill_3m", "status": "unavailable" if rates else "no_data", "avg_annual": None}
    avg_d = sum(rf) / len(rf)
    return {"source": "tbill_3m", "status": "ok", "avg_annual": (1.0 + avg_d) ** M.TRADING_DAYS - 1.0,
            "first_annual": (1.0 + rf[0]) ** M.TRADING_DAYS - 1.0, "last_annual": (1.0 + rf[-1]) ** M.TRADING_DAYS - 1.0}
