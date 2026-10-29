"""สัญญา (interface) ของแหล่งราคา — สลับ Provider ได้โดยไม่แตะ engine

Bar = {"date": "YYYY-MM-DD", "open": f, "high": f, "low": f, "close": f, "volume": int}
ราคาต้องเป็น split-adjusted และ *ไม่* ปรับปันผล (Price Return)
"""
from __future__ import annotations

from datetime import date
from typing import Protocol


class ProviderError(Exception):
    """แหล่งข้อมูลภายนอกผิดพลาด (ข้อความต้องไม่มี API key/URL ที่มี key)"""


class PriceProvider(Protocol):
    name: str

    def get_bars(self, symbol: str, start: date, end: date) -> list[dict]: ...
