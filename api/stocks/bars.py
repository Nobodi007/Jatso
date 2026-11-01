"""แท่งเทียนรายวัน: เก็บใน SQLite + ตัวดึงข้อมูล

โหมด
  polygon : มี POLYGON_KEY (หรือ MASSIVE_KEY) → ดึง "grouped daily" ทั้งตลาดวันละ 1 call
            ถ้าแผนไม่อนุญาต endpoint นี้จะสลับเป็นดึงทีละตัว (ช้าแต่ใช้ได้)
  yahoo   : ไม่มี key → yfinance (ไม่เป็นทางการ อาจโดนจำกัด) ดึงเป็นก้อนละ ~60 ตัว

ราคาที่เก็บจาก Polygon เป็นราคาตามจริงของแต่ละวัน (ยังไม่ปรับ split) จึงเก็บตาราง splits ไว้ปรับตอนอ่าน
แต่ละแท่งมีคอลัมน์ asof = วันที่ราคานั้น "ปรับ split ไปถึง" (Polygon = วันของแท่งเอง, Yahoo = วันที่ดึง)
ตอนอ่านจะปรับเฉพาะ split ที่เกิดหลัง asof ของแท่งนั้น จึงผสมแหล่งข้อมูลได้โดยไม่ซ้ำซ้อน
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import sqlite3
import threading
import time
from contextlib import closing
from datetime import date, datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import numpy as np

from . import datadir

log = logging.getLogger("stocks.bars")

POLYGON_KEY = os.getenv("POLYGON_KEY") or os.getenv("MASSIVE_KEY") or ""
BASE = os.getenv("POLYGON_BASE", "https://api.polygon.io")  # api.massive.com ใช้แทนกันได้
DB = datadir.path("bars.sqlite")
HISTORY_DAYS = 420            # ~290 วันทำการ พอสำหรับ SMA200 + ผลตอบแทน 1 ปี
CALL_GAP = 12.5               # แผนฟรี 5 call/นาที
NY = ZoneInfo("America/New_York")
_dblock = threading.Lock()

STATUS: dict = {"mode": "polygon" if POLYGON_KEY else "yahoo", "phase": "idle", "done": 0, "total": 0,
                "lastBar": None, "error": None, "splitsOk": None}


class BarsError(Exception):
    pass


class PlanDenied(BarsError):
    pass


# ───────────────────────── SQLite ─────────────────────────

def _conn():
    c = sqlite3.connect(DB, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_db():
    with _dblock, closing(_conn()) as c, c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS bars(sym TEXT, d TEXT, o REAL, h REAL, l REAL, c REAL, v REAL, asof TEXT,
                                        PRIMARY KEY(sym, d));
        CREATE TABLE IF NOT EXISTS splits(sym TEXT, d TEXT, factor REAL, PRIMARY KEY(sym, d));
        CREATE TABLE IF NOT EXISTS days(d TEXT PRIMARY KEY, n INTEGER);
        CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
        """)


def kv_get(k: str, default=None):
    with closing(_conn()) as c:
        r = c.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return r[0] if r else default


def kv_set(k: str, v: str):
    with _dblock, closing(_conn()) as c, c:
        c.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (k, v))


def _store_rows(rows: list[tuple]):
    with _dblock, closing(_conn()) as c, c:
        c.executemany("INSERT OR REPLACE INTO bars VALUES(?,?,?,?,?,?,?,?)", rows)


def _mark_day(d: str, n: int):
    with _dblock, closing(_conn()) as c, c:
        c.execute("INSERT OR REPLACE INTO days VALUES(?,?)", (d, n))


def _done_days() -> set[str]:
    with closing(_conn()) as c:
        return {r[0] for r in c.execute("SELECT d FROM days")}


def _bar_stats() -> dict[str, tuple[int, str]]:
    with closing(_conn()) as c:
        return {s: (n, mx) for s, n, mx in c.execute("SELECT sym, COUNT(*), MAX(d) FROM bars GROUP BY sym")}


def _prune():
    cut = (date.today() - timedelta(days=HISTORY_DAYS + 60)).isoformat()
    with _dblock, closing(_conn()) as c, c:
        c.execute("DELETE FROM bars WHERE d < ?", (cut,))
        c.execute("DELETE FROM days WHERE d < ?", (cut,))


def _store_splits(rows: list[tuple]):
    with _dblock, closing(_conn()) as c, c:
        c.executemany("INSERT OR REPLACE INTO splits VALUES(?,?,?)", rows)


# ───────────────────────── อ่านแท่ง + ปรับ split ─────────────────────────

_RATIOS = (2, 3, 4, 5, 6, 7, 8, 10, 15, 20, 25, 30, 40, 50, 100)


def _guess_splits(d, o, c):
    """สำรองเมื่อดึงตาราง split ไม่ได้: จับการกระโดดของราคาที่เป็นอัตราส่วนแบบ split (ต้องตรงทั้งราคาเปิดและปิด)"""
    out = []
    for i in range(1, len(c)):
        if c[i - 1] <= 0:
            continue
        r = c[i] / c[i - 1]
        ro = o[i] / c[i - 1]
        for k in _RATIOS:
            hit = next((f for f in (1.0 / k, float(k)) if abs(r / f - 1) < 0.03 and abs(ro / f - 1) < 0.06), None)
            if hit:
                out.append((d[i], hit))
                break
    return out


def load_all(symbols: set[str] | None = None) -> dict[str, dict]:
    """{sym: {d: ndarray[str], o,h,l,c,v: ndarray}} เรียงเก่า→ใหม่ และปรับ split แล้ว"""
    with closing(_conn()) as cx:
        rows = cx.execute("SELECT sym,d,o,h,l,c,v,asof FROM bars ORDER BY sym, d").fetchall()
        sp: dict[str, list] = {}
        for s, d, f in cx.execute("SELECT sym,d,factor FROM splits"):
            sp.setdefault(s, []).append((d, f))
    use_guess = kv_get("splits_ok") == "0"

    out: dict[str, dict] = {}
    i, n = 0, len(rows)
    while i < n:
        sym = rows[i][0]
        j = i
        while j < n and rows[j][0] == sym:
            j += 1
        if symbols is None or sym in symbols:
            seg = rows[i:j]
            d = np.array([r[1] for r in seg])
            asof = np.array([r[7] or r[1] for r in seg])
            o, h, l, c, v = (np.array([r[k] for r in seg], dtype=float) for k in (2, 3, 4, 5, 6))
            splits = sp.get(sym, [])
            if use_guess and not splits:
                splits = _guess_splits(d, o, c)
            for sd, f in splits:
                if not (f > 0 and math.isfinite(f)):
                    continue
                m = (d < sd) & (asof < sd)
                if m.any():
                    for a in (o, h, l, c):
                        a[m] *= f
                    v[m] /= f
            out[sym] = {"d": d, "o": o, "h": h, "l": l, "c": c, "v": v}
        i = j
    return out


# ───────────────────────── Polygon / Massive ─────────────────────────

_last_call = 0.0


async def _pace():
    global _last_call
    wait = CALL_GAP - (time.monotonic() - _last_call)
    if wait > 0:
        await asyncio.sleep(wait)
    _last_call = time.monotonic()


async def _poly(cl: httpx.AsyncClient, url_or_path: str, params: dict | None = None):
    url = url_or_path if url_or_path.startswith("http") else BASE + url_or_path
    for attempt in range(4):
        await _pace()
        try:
            r = await cl.get(url, params=params, headers={"Authorization": f"Bearer {POLYGON_KEY}"})
        except httpx.HTTPError as e:
            raise BarsError(type(e).__name__) from e   # ไม่แสดง URL (กันหลุด key)
        if r.status_code == 429:
            log.info("polygon 429, backoff")
            await asyncio.sleep(65)
            continue
        if r.status_code in (401, 403):
            raise PlanDenied(f"HTTP {r.status_code}")
        if r.status_code != 200:
            raise BarsError(f"HTTP {r.status_code}")
        try:
            return r.json()
        except ValueError as e:
            raise BarsError("non-JSON") from e
    raise BarsError("rate limited")


def _target_end() -> date:
    """วันทำการล่าสุดที่ควรมีข้อมูลปิดตลาดแล้ว"""
    now = datetime.now(NY)
    d = now.date() if now.time() >= dtime(17, 30) else now.date() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _weekdays(a: date, b: date):
    d = a
    while d <= b:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def _bar_date(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()


def _row(sym, d, r):
    try:
        o, h, l, c, v = (float(r[k]) for k in ("o", "h", "l", "c", "v"))
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(x) for x in (o, h, l, c)) or c <= 0 or h < l:
        return None
    return (sym, d, o, h, l, c, v, d)


async def _sync_grouped(cl, uni: set[str], end: date) -> bool:
    """คืน True ถ้าใช้ grouped ได้ ; False ถ้าแผนไม่อนุญาตตั้งแต่ครั้งแรก"""
    start = date.today() - timedelta(days=HISTORY_DAYS)
    done = _done_days()
    pending = [d for d in _weekdays(start, end) if d.isoformat() not in done]
    STATUS.update(phase="grouped", done=0, total=len(pending))
    first = not done
    for k, d in enumerate(pending):
        ds = d.isoformat()
        try:
            js = await _poly(cl, f"/v2/aggs/grouped/locale/us/market/stocks/{ds}", {"adjusted": "false"})
        except PlanDenied as e:
            if first and k == 0:
                log.warning("polygon: grouped daily not allowed on this plan (%s); switching to per-symbol", e)
                return False
            log.info("polygon: %s not available yet (%s)", ds, e)
            break
        res = js.get("results") or []
        rows = [x for x in (_row(r.get("T"), ds, r) for r in res if r.get("T") in uni) if x]
        if rows:
            await asyncio.to_thread(_store_rows, rows)
        if res or (end - d).days > 3:       # วันหยุดจริง = ว่าง ; ว่างในช่วง 3 วันล่าสุด อาจยังไม่ออก ให้ลองใหม่
            await asyncio.to_thread(_mark_day, ds, len(res))
        STATUS["done"] = k + 1
    return True


async def _sync_per_symbol(cl, uni: list[str], end: date, cap: int | None, incremental: bool):
    """ดึงทีละตัว
    - ตัวที่มีแท่งน้อยกว่า 200 (หุ้นใหม่/เพิ่งเข้าชุด/ไอพีโอ) → ดึงย้อนหลังทั้งช่วง (ลองซ้ำได้สัปดาห์ละครั้ง)
    - incremental=True (โหมดไม่มี grouped) → ตัวที่แท่งล่าสุดเก่ากว่าวันเป้าหมายก็ดึงต่อ
    cap = จำนวน call สูงสุดต่อรอบ"""
    stats = await asyncio.to_thread(_bar_stats)
    horizon = (date.today() - timedelta(days=HISTORY_DAYS)).isoformat()
    todo = []
    for s in uni:
        n, mx = stats.get(s, (0, ""))
        if n < 200:  # ยังไม่เคยดึง/ข้อมูลน้อย → ดึงทั้งช่วง (ยกเว้นเพิ่งลองไปไม่เกิน 7 วัน)
            t = float(kv_get(f"bf:{s}", "0") or 0)
            if time.time() - t > 7 * 86400:
                todo.append((horizon, s, True))
        elif incremental and mx < end.isoformat():
            todo.append((mx, s, False))
    todo.sort()
    if cap:
        todo = todo[:cap]
    STATUS.update(phase="per-symbol", done=0, total=len(todo))
    for k, (frm, s, full) in enumerate(todo):
        try:
            js = await _poly(cl, f"/v2/aggs/ticker/{s}/range/1/day/{frm}/{end.isoformat()}",
                             {"adjusted": "false", "sort": "asc", "limit": 50000})
        except PlanDenied as e:
            log.warning("polygon: %s denied (%s)", s, e)
            continue
        except BarsError as e:
            log.info("polygon: %s failed (%s)", s, e)
            continue
        rows = [x for x in (_row(s, _bar_date(r["t"]), r) for r in (js.get("results") or []) if "t" in r) if x]
        if rows:
            await asyncio.to_thread(_store_rows, rows)
        if full:
            await asyncio.to_thread(kv_set, f"bf:{s}", str(time.time()))
        STATUS["done"] = k + 1


async def _sync_splits(cl, uni: set[str]):
    if time.time() - float(kv_get("splits_at", "0") or 0) < 86400 and kv_get("splits_ok") == "1":
        return
    start = (date.today() - timedelta(days=HISTORY_DAYS + 10)).isoformat()
    url, params, rows = "/v3/reference/splits", {"execution_date.gte": start, "limit": 1000,
                                                  "order": "asc", "sort": "execution_date"}, []
    try:
        for _ in range(20):
            js = await _poly(cl, url, params)
            for r in js.get("results") or []:
                try:
                    if r["ticker"] in uni and float(r["split_from"]) > 0 and float(r["split_to"]) > 0:
                        rows.append((r["ticker"], r["execution_date"], float(r["split_from"]) / float(r["split_to"])))
                except (KeyError, TypeError, ValueError):
                    continue
            nxt = js.get("next_url")
            if not nxt:
                break
            url, params = nxt, None
    except BarsError as e:
        log.warning("splits fetch failed (%s); using price-jump heuristic until it works", e)
        await asyncio.to_thread(kv_set, "splits_ok", "0")
        STATUS["splitsOk"] = False
        return
    await asyncio.to_thread(_store_splits, rows)
    await asyncio.to_thread(kv_set, "splits_ok", "1")
    await asyncio.to_thread(kv_set, "splits_at", str(time.time()))
    STATUS["splitsOk"] = True


# ───────────────────────── Yahoo (สำรอง/ไม่มี key) ─────────────────────────

def _yf(sym: str) -> str:
    return sym.replace(".", "-")


def _yahoo_batch_sync(batch: list[str], start: date) -> list[tuple]:
    import yfinance as yf
    df = yf.download([_yf(s) for s in batch], start=start.isoformat(), auto_adjust=False,
                     group_by="ticker", progress=False, threads=True)
    now = datetime.now(NY)
    today = date.today().isoformat()
    rows = []
    for s in batch:
        try:
            sub = df[_yf(s)] if len(batch) > 1 else df
            sub = sub.dropna(subset=["Close"])
        except (KeyError, TypeError):
            continue
        for ts, r in sub.iterrows():
            d = ts.date()
            if d == now.date() and now.time() < dtime(16, 15):
                continue
            try:
                o, h, l, c, v = (float(r[k]) for k in ("Open", "High", "Low", "Close", "Volume"))
            except (KeyError, TypeError, ValueError):
                continue
            if all(math.isfinite(x) for x in (o, h, l, c)) and c > 0 and h >= l:
                rows.append((s, d.isoformat(), o, h, l, c, v if math.isfinite(v) else 0.0, today))
    return rows


def _replace_symbols(syms: list[str], rows: list[tuple]):
    with _dblock, closing(_conn()) as c, c:
        c.executemany("DELETE FROM bars WHERE sym=?", [(s,) for s in {r[0] for r in rows}])
        c.executemany("INSERT OR REPLACE INTO bars VALUES(?,?,?,?,?,?,?,?)", rows)


async def _sync_yahoo(uni: list[str]):
    start = date.today() - timedelta(days=HISTORY_DAYS)
    B = 60
    STATUS.update(phase="yahoo", done=0, total=len(uni))
    for i in range(0, len(uni), B):
        batch = uni[i:i + B]
        try:
            rows = await asyncio.wait_for(asyncio.to_thread(_yahoo_batch_sync, batch, start), timeout=180)
        except Exception as e:  # noqa: BLE001
            log.warning("yahoo batch %d failed: %s", i // B, type(e).__name__)
            rows = []
        if rows:
            await asyncio.to_thread(_replace_symbols, batch, rows)
        STATUS["done"] = min(i + B, len(uni))
        await asyncio.sleep(3)


# ───────────────────────── entry ─────────────────────────

async def run_once(universe: list[str]) -> bool:
    """อัปเดตแท่งเทียนหนึ่งรอบ คืน True ถ้ามีข้อมูลใหม่"""
    init_db()
    before = max((mx for _, mx in (await asyncio.to_thread(_bar_stats)).values()), default="")
    uni = set(universe)
    end = _target_end()
    STATUS["error"] = None
    try:
        if POLYGON_KEY:
            async with httpx.AsyncClient(timeout=40) as cl:
                mode = kv_get("mode", "grouped")
                if mode == "grouped" and not await _sync_grouped(cl, uni, end):
                    kv_set("mode", "per_symbol")
                    mode = "per_symbol"
                if mode == "grouped":
                    # หุ้นที่เพิ่งเข้าชุด/ไอพีโอใหม่: ดึงย้อนหลังทีละตัว รอบละไม่เกิน 40 call
                    await _sync_per_symbol(cl, universe, end, cap=40, incremental=False)
                else:
                    await _sync_per_symbol(cl, universe, end, cap=None, incremental=True)
                await _sync_splits(cl, uni)
        else:
            stale = time.time() - float(kv_get("yahoo_at", "0") or 0) > 6 * 3600
            if stale and (not before or before < end.isoformat()):
                await _sync_yahoo(universe)
                kv_set("yahoo_at", str(time.time()))
    except BarsError as e:
        STATUS["error"] = str(e)
        log.warning("bars sync stopped: %s", e)
    await asyncio.to_thread(_prune)
    after = max((mx for _, mx in (await asyncio.to_thread(_bar_stats)).values()), default="")
    STATUS.update(phase="idle", lastBar=after or None)
    return after != before
