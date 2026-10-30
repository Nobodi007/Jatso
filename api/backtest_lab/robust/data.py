"""ดึงราคาสำหรับรันซ้ำตาม spec ที่เก็บไว้ (ผ่าน PriceStore/cache เดียวกับระบบ) — ไม่แก้ service.py"""
from __future__ import annotations

from datetime import date, timedelta

from .. import config as C
from ..data.price_store import PriceStore
from ..data.validate import clean_bars
from ..engine.rules import warmup_bars


def load_bars(spec: dict, price_store: PriceStore) -> tuple[dict, list]:
    start, end = date.fromisoformat(spec["start"]), date.fromisoformat(spec["end"])
    warm = warmup_bars(spec["strategy"]) if spec.get("strategy") else 0
    fetch_from = start - timedelta(days=30 + int(warm * 1.5) + 7)
    bars = {}
    for sym in [p["symbol"] for p in spec["positions"]] + [C.BENCHMARK]:
        raw, _meta = price_store.get_bars(sym, fetch_from, end)
        bars[sym], _issues = clean_bars(sym, raw)
    bench = bars.pop(C.BENCHMARK)
    return bars, bench
