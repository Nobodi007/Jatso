"""Yahoo Finance (yfinance) — แหล่งไม่เป็นทางการ ใช้เป็นแหล่งหลักของ Backtest ตามที่ตัดสินใจใน B0

- auto_adjust=False  -> Close เป็น split-adjusted ไม่ปรับปันผล (ตรงนิยาม Price Return)
- ตัดแท่งของวันนี้ที่ตลาดยังไม่ปิดทิ้ง
- ฟังก์ชันเป็น sync (เรียกผ่าน thread จากชั้น service)
ผลทดสอบจริงของ probe: AAPL/NVDA/TSLA/CRDO/^GSPC/SPY ได้ครบ มี volume; SIVB (delist) ว่างเปล่า
"""
from __future__ import annotations

import math
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

from .provider_base import ProviderError

_NY = ZoneInfo("America/New_York")


def _yf_symbol(symbol: str) -> str:
    return symbol if symbol.startswith("^") else symbol.replace(".", "-")


class YahooProvider:
    name = "yahoo"

    def get_bars(self, symbol: str, start: date, end: date) -> list[dict]:
        try:
            import yfinance as yf
        except ImportError as e:                                  # pragma: no cover
            raise ProviderError("yfinance not installed") from e
        try:
            df = yf.Ticker(_yf_symbol(symbol)).history(
                start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
                auto_adjust=False, actions=False)
        except Exception as e:                                    # network/format; ห้ามส่งข้อความดิบที่อาจมี URL
            raise ProviderError(f"yahoo: {type(e).__name__}") from e
        if df is None or df.empty:
            return []
        now = datetime.now(_NY)
        out = []
        for ts, r in df.iterrows():
            try:
                o, h, l, c = (float(r[k]) for k in ("Open", "High", "Low", "Close"))
                v = int(r.get("Volume") or 0)
            except (KeyError, TypeError, ValueError):
                continue
            if not all(math.isfinite(x) for x in (o, h, l, c)) or min(o, h, l, c) <= 0:
                continue
            d = ts.date()
            if d == now.date() and now.time() < dtime(16, 15):
                continue
            out.append({"date": d.isoformat(), "open": o, "high": h, "low": l, "close": c, "volume": v})
        out.sort(key=lambda b: b["date"])
        return out
