"""ดึงราคาสำหรับรันซ้ำตาม spec ที่เก็บไว้ (ผ่าน PriceStore/cache เดียวกับระบบ) — ไม่แก้ service.py"""
from __future__ import annotations

from datetime import date, timedelta

from ..data.price_store import PriceStore
from ..data.total_return import Market, load_market
from ..engine.rules import warmup_bars


def load_bars(spec: dict, price_store: PriceStore) -> Market:
    start, end = date.fromisoformat(spec["start"]), date.fromisoformat(spec["end"])
    warm = warmup_bars(spec["strategy"]) if spec.get("strategy") else 0
    fetch_from = start - timedelta(days=30 + int(warm * 1.5) + 7)
    return load_market(spec, price_store, fetch_from, end)
