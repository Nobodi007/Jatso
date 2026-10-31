"""ตรวจคุณภาพแท่งราคาก่อนเข้า engine — คืนแท่งที่สะอาด + รายการปัญหา (ไม่ซ่อนปัญหา)"""
from __future__ import annotations

import math
from datetime import date

# อัตรา split ที่พบบ่อย: ถ้าราคาปิดกระโดดใกล้อัตราเหล่านี้ อาจเป็น split ที่ยังไม่ถูกปรับ
_SPLIT_RATIOS = (2, 3, 4, 5, 8, 10, 15, 20)
GAP_DAYS = 10


class DataError(Exception):
    """ข้อมูลใช้ไม่ได้ (code ใช้แมปเป็นข้อความผู้ใช้)"""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def clean_bars(symbol: str, bars: list[dict]) -> tuple[list[dict], list[dict]]:
    issues: list[dict] = []
    seen: dict[str, dict] = {}
    dropped = 0
    for b in bars:
        try:
            vals = [float(b[k]) for k in ("open", "high", "low", "close")]
            d = str(b["date"])[:10]
            date.fromisoformat(d)
        except (KeyError, TypeError, ValueError):
            dropped += 1
            continue
        if not all(math.isfinite(v) for v in vals) or min(vals) <= 0:
            dropped += 1
            continue
        row = {"date": d, "open": vals[0], "high": vals[1], "low": vals[2], "close": vals[3],
               "volume": int(b.get("volume") or 0)}
        try:                                                  # adj_close (ถ้ามี) ใช้เฉพาะโหมด Total Return
            a = float(b["adj_close"])
            if math.isfinite(a) and a > 0:
                row["adj_close"] = a
        except (KeyError, TypeError, ValueError):
            pass
        seen[d] = row
    out = [seen[k] for k in sorted(seen)]
    if dropped:
        issues.append({"symbol": symbol, "code": "dropped_rows", "count": dropped})
    if not out:
        raise DataError("no_data", f"{symbol}: ไม่มีข้อมูลราคา")

    bad_ohlc = sum(1 for b in out if b["low"] > min(b["open"], b["close"]) * 1.0001
                   or b["high"] < max(b["open"], b["close"]) * 0.9999)
    if bad_ohlc:
        issues.append({"symbol": symbol, "code": "ohlc_inconsistent", "count": bad_ohlc})

    for prev, cur in zip(out, out[1:]):
        gap = (date.fromisoformat(cur["date"]) - date.fromisoformat(prev["date"])).days
        if gap > GAP_DAYS:
            issues.append({"symbol": symbol, "code": "gap", "from": prev["date"], "to": cur["date"], "days": gap})
        jump = prev["close"] / cur["close"] if cur["close"] else 0.0
        for r in _SPLIT_RATIOS:
            if abs(jump - r) / r < 0.03 or abs(1 / jump - r) / r < 0.03 if jump else False:
                issues.append({"symbol": symbol, "code": "possible_unadjusted_split",
                               "date": cur["date"], "ratio": round(max(jump, 1 / jump), 3)})
                break
    return out, issues
