"""อัตรา Treasury 3 เดือน (รายปี, ทศนิยม) จาก FMP /stable/treasury-rates ช่อง month3 — แหล่งเดียวกับ Risk Center
แต่เป็นโค้ดของแพ็กเกจนี้เอง (อ่าน env FMP_KEY ไม่ import ระบบเดิม)

- ดึงเป็นช่วงละ ≤ 90 วัน (ข้อจำกัดของ endpoint) แล้ว cache ถาวรผ่าน backend เดียวกับราคา (คีย์ RF_TBILL3M)
- cache เก็บช่วงที่ "ครอบคลุมแล้ว" (covered_from..covered_to) ครั้งต่อไปดึงเฉพาะส่วนที่ยังไม่มี (หัว/ท้าย)
- ล้มเหลว = raise ProviderError (service จะรันต่อแบบไม่มี risk-free พร้อมคำเตือน ไม่สมมติค่าเอง)
"""
from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Callable

from .. import config as C
from .provider_base import ProviderError

KEY = "RF_TBILL3M"
BASE = "https://financialmodelingprep.com/stable"
CHUNK_DAYS = 89
MAX_CALLS = 60                      # เพดานคำขอต่อครั้ง (ป้องกันงานค้าง/ใช้โควตา FMP หมด)


class FmpRates:
    name = "fmp_treasury_3m"

    def __init__(self, key: str | None = None, timeout: float = 10.0):
        self.key = key if key is not None else os.environ.get("FMP_KEY", "")
        self.timeout = timeout

    def _get(self, start: date, end: date):
        q = urllib.parse.urlencode({"from": start.isoformat(), "to": end.isoformat(), "apikey": self.key})
        try:
            with urllib.request.urlopen(f"{BASE}/treasury-rates?{q}", timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, ValueError, OSError) as e:       # ห้ามส่งข้อความดิบ (มี URL/key)
            raise ProviderError(f"fmp treasury: {type(e).__name__}") from e

    def get_rates(self, start: date, end: date) -> dict[str, float]:
        """{'YYYY-MM-DD': annual decimal}"""
        if not self.key:
            raise ProviderError("FMP_KEY ไม่ได้ตั้งค่า")
        out: dict[str, float] = {}
        cur, calls = start, 0
        while cur <= end:
            calls += 1
            if calls > MAX_CALLS:
                raise ProviderError("fmp treasury: ช่วงเวลายาวเกินเพดานคำขอ")
            hi = min(cur + timedelta(days=CHUNK_DAYS), end)
            data = self._get(cur, hi)
            if isinstance(data, dict):                                   # {"Error Message": ...}
                raise ProviderError("fmp treasury: rejected (plan/permission)")
            for r in data or []:
                v = r.get("month3")
                if v is None:
                    continue
                try:
                    f = float(v)
                except (TypeError, ValueError):
                    continue
                if f == f and -5.0 < f < 100.0:                         # yield เป็น % (อาจ ~0 ได้จริง ห้ามตัดทิ้งเพราะ ≤ 0)
                    out[str(r["date"])[:10]] = f / 100.0
            cur = hi + timedelta(days=1)
        return out


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RateStore:
    def __init__(self, provider, backend, ttl_seconds: float = C.PRICE_TTL_SECONDS,
                 now_fn: Callable[[], datetime] = _now):
        self.provider, self.backend, self.ttl, self.now = provider, backend, ttl_seconds, now_fn
        self._lock = threading.Lock()

    def _put(self, rates: dict, cf: str, ct: str) -> dict:
        ds = sorted(rates)
        e = {"symbol": KEY, "source": self.provider.name, "first_date": ds[0] if ds else cf,
             "last_date": ds[-1] if ds else ct, "fetched_at": self.now().isoformat(),
             "covered_from": cf, "covered_to": ct, "rates": rates}
        self.backend.put(KEY, e)
        return e

    def get_rates(self, start: date, end: date) -> tuple[dict[date, float], dict]:
        """คืน ({date: annual}, meta) ครอบคลุม start..end เท่าที่มี; ล้มเหลวโดยไม่มี cache -> ProviderError"""
        with self._lock:
            e = self.backend.get(KEY)
            s, en = start.isoformat(), end.isoformat()
            stale = False
            try:
                if e is None:
                    e = self._put(self.provider.get_rates(start, end), s, en)
                else:
                    rates = dict(e["rates"])
                    cf, ct = e["covered_from"], e["covered_to"]
                    age = (self.now() - datetime.fromisoformat(e["fetched_at"])).total_seconds()
                    changed = False
                    if s < cf:                                           # ต้องการช่วงที่เก่ากว่าที่เคยดึง
                        rates.update(self.provider.get_rates(start, date.fromisoformat(cf) - timedelta(days=1)))
                        cf, changed = s, True
                    if en > ct or age > self.ttl:                        # ท้ายช่วง/หมดอายุ: ดึงซ้อนทับ 7 วัน
                        frm = date.fromisoformat(ct) - timedelta(days=7)
                        rates.update(self.provider.get_rates(frm, max(end, date.fromisoformat(ct))))
                        ct, changed = max(en, ct), True
                    if changed:
                        e = self._put(rates, cf, ct)
            except ProviderError:
                if e is None:
                    raise
                stale = True                                             # มี cache เดิม ใช้ต่อและติดธง
        sel = {date.fromisoformat(d): v for d, v in e["rates"].items() if s <= d <= en}
        return sel, {"source": e["source"], "fetched_at": e["fetched_at"], "stale": stale,
                     "points": len(sel), "first_date": e["first_date"], "last_date": e["last_date"]}
