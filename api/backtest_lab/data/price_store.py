"""Cache ราคาถาวร + อัปเดตเฉพาะวันใหม่

หลักการ
- ดึงประวัติเต็ม (ตั้งแต่ FULL_HISTORY_START) ครั้งเดียวต่อ symbol แล้วเก็บ; ครั้งต่อไปดึงเฉพาะส่วนท้าย
- อัปเดตส่วนท้ายโดยดึงซ้อนทับ OVERLAP_DAYS วัน: ถ้าราคาปิดช่วงซ้อนทับต่างจากที่ cache ไว้ (เช่น เกิด split หลัง cache)
  จะทิ้ง cache แล้วดึงเต็มใหม่ — กันราคาเก่าที่ไม่ได้ปรับปะปนกับราคาใหม่
- ถ้าอัปเดตไม่สำเร็จแต่มี cache -> ใช้ cache เดิมและติดธง stale (ไม่ซ่อน)
- Backend สลับได้: Memory / File (gzip JSON) / Supabase (ผ่านตัวส่งคำขอที่ฉีดเข้ามา)
"""
from __future__ import annotations

import base64
import gzip
import json
import os
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional, Protocol

from .. import config as C
from .provider_base import PriceProvider, ProviderError


class CacheBackend(Protocol):
    def get(self, symbol: str) -> Optional[dict]: ...
    def put(self, symbol: str, entry: dict) -> None: ...


class MemoryBackend:
    def __init__(self, max_entries: int = 200):
        self._d: dict[str, dict] = {}
        self._max = max_entries

    def get(self, symbol):
        return self._d.get(symbol)

    def put(self, symbol, entry):
        if len(self._d) >= self._max and symbol not in self._d:
            self._d.pop(next(iter(self._d)))
        self._d[symbol] = entry


class FileBackend:
    """เหมาะกับเครื่อง dev/เซิร์ฟเวอร์ที่มีดิสก์ถาวร (บน host ที่ดิสก์ชั่วคราว ให้ใช้ Supabase backend)"""
    def __init__(self, directory: str):
        self.dir = directory
        os.makedirs(directory, exist_ok=True)

    def _path(self, symbol: str) -> str:
        safe = "".join(ch if ch.isalnum() else "_" for ch in symbol)
        return os.path.join(self.dir, f"{safe}.json.gz")

    def get(self, symbol):
        try:
            with gzip.open(self._path(symbol), "rt", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def put(self, symbol, entry):
        tmp = self._path(symbol) + ".tmp"
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(entry, f)
        os.replace(tmp, self._path(symbol))


class SupabaseBackend:
    """ตาราง bt_price_cache (ดู db/schema.sql) — 1 แถวต่อ symbol, payload = gzip+base64 ของ entry
    `request(method, table, params, json_body, prefer)` เป็นฟังก์ชัน sync ที่ฉีดเข้ามา (ดู db/client.py)"""
    TABLE = "bt_price_cache"

    def __init__(self, request: Callable[..., object]):
        self._req = request

    def get(self, symbol):
        rows = self._req("GET", self.TABLE, params={"symbol": f"eq.{symbol}", "select": "payload", "limit": "1"})
        if not rows:
            return None
        try:
            return json.loads(gzip.decompress(base64.b64decode(rows[0]["payload"])).decode("utf-8"))
        except (KeyError, ValueError, OSError):
            return None

    def put(self, symbol, entry):
        blob = base64.b64encode(gzip.compress(json.dumps(entry).encode("utf-8"))).decode("ascii")
        row = {"symbol": symbol, "source": entry["source"], "first_date": entry["first_date"],
               "last_date": entry["last_date"], "fetched_at": entry["fetched_at"], "payload": blob}
        self._req("POST", self.TABLE, json_body=row, prefer="resolution=merge-duplicates")


class LayeredBackend:
    """หน่วยความจำนำหน้า backend ถาวร — ลดการอ่านซ้ำ (ลด egress)"""
    def __init__(self, front: CacheBackend, back: CacheBackend):
        self.front, self.back = front, back

    def get(self, symbol):
        e = self.front.get(symbol)
        if e is None:
            e = self.back.get(symbol)
            if e is not None:
                self.front.put(symbol, e)
        return e

    def put(self, symbol, entry):
        self.back.put(symbol, entry)
        self.front.put(symbol, entry)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PriceStore:
    def __init__(self, provider: PriceProvider, backend: CacheBackend,
                 ttl_seconds: float = C.PRICE_TTL_SECONDS, now_fn: Callable[[], datetime] = _utcnow):
        self.provider, self.backend, self.ttl, self.now = provider, backend, ttl_seconds, now_fn
        self._locks: dict[str, threading.Lock] = {}
        self._glock = threading.Lock()

    def _lock(self, symbol: str) -> threading.Lock:
        with self._glock:
            return self._locks.setdefault(symbol, threading.Lock())

    def _full_fetch(self, symbol: str) -> dict:
        bars = self.provider.get_bars(symbol, date.fromisoformat(C.FULL_HISTORY_START), self.now().date())
        if not bars:
            raise ProviderError(f"{symbol}: ผู้ให้บริการไม่ส่งข้อมูล (อาจไม่มีสัญลักษณ์นี้ หรือถูก delist)")
        return self._entry(symbol, bars)

    def _entry(self, symbol: str, bars: list[dict]) -> dict:
        return {"symbol": symbol, "source": self.provider.name, "first_date": bars[0]["date"],
                "last_date": bars[-1]["date"], "fetched_at": self.now().isoformat(), "bars": bars,
                "has_adj": all("adj_close" in b for b in bars)}

    def _refresh(self, symbol: str, entry: dict) -> tuple[dict, bool]:
        """คืน (entry ใหม่, refreshed) ; ถ้าอัปเดตล้มเหลว -> raise ให้ผู้เรียกใช้ stale"""
        last = date.fromisoformat(entry["last_date"])
        frm = last - timedelta(days=C.OVERLAP_DAYS)
        fresh = self.provider.get_bars(symbol, frm, self.now().date())
        if not fresh:
            raise ProviderError(f"{symbol}: refresh returned no data")
        old = {b["date"]: b for b in entry["bars"]}
        for b in fresh:
            o = old.get(b["date"])
            if o is None:
                continue
            if abs(b["close"] / o["close"] - 1.0) > C.OVERLAP_TOL:
                return self._full_fetch(symbol), True            # ราคาเก่าถูกปรับย้อนหลัง (split) -> ดึงเต็มใหม่
            if "adj_close" in b and "adj_close" in o:            # มีปันผลใหม่ -> adj_close ของประวัติเก่าทั้งหมดเปลี่ยนสเกล -> ดึงเต็มใหม่
                if abs((b["adj_close"] / b["close"]) / (o["adj_close"] / o["close"]) - 1.0) > C.ADJ_TOL:
                    return self._full_fetch(symbol), True
        if "adj_close" in fresh[0] and any("adj_close" not in b for b in entry["bars"]):
            return self._full_fetch(symbol), True                # cache เก่าไม่มี adj_close -> ดึงเต็มใหม่ครั้งเดียว
        merged = {b["date"]: b for b in entry["bars"]}
        for b in fresh:
            merged[b["date"]] = b
        bars = [merged[k] for k in sorted(merged)]
        return self._entry(symbol, bars), True

    def get_bars(self, symbol: str, start: date, end: date, need_adj: bool = False) -> tuple[list[dict], dict]:
        with self._lock(symbol):
            entry = self.backend.get(symbol)
            stale, refreshed = False, False
            if entry is None:
                entry, refreshed = self._full_fetch(symbol), True
                self.backend.put(symbol, entry)
            else:
                age = (self.now() - datetime.fromisoformat(entry["fetched_at"])).total_seconds()
                if age > self.ttl:
                    try:
                        entry, refreshed = self._refresh(symbol, entry)
                        self.backend.put(symbol, entry)
                    except ProviderError:
                        stale = True
            if need_adj and not entry.get("has_adj", False) and not refreshed:
                entry, refreshed = self._full_fetch(symbol), True    # cache เก่าไม่มี adj_close
                self.backend.put(symbol, entry)
        s, e = start.isoformat(), end.isoformat()
        bars = [b for b in entry["bars"] if s <= b["date"] <= e]
        meta = {"symbol": symbol, "source": entry["source"], "first_date": entry["first_date"],
                "last_date": entry["last_date"], "fetched_at": entry["fetched_at"],
                "stale": stale, "refreshed": refreshed}
        return bars, meta
