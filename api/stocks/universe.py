"""รายชื่อหุ้นที่ screener สแกน = ลิสต์พื้นฐานเดิม + S&P 500 + S&P 400 + Nasdaq-100 (+ EXTRA_TICKERS)

ดึงรายชื่อจาก Wikipedia สัปดาห์ละครั้ง เก็บแคชไว้ในไฟล์ ถ้าดึงไม่ได้จะใช้แคชเก่า/ลิสต์พื้นฐานต่อ ระบบไม่ล่ม
(Wikipedia แก้ไขได้โดยคนทั่วไป จึงกรองรูปแบบ ticker ให้เข้มและตัดทิ้งถ้ารูปแบบแปลก)
"""
import json
import logging
import os
import re
import time

import httpx

from . import datadir

log = logging.getLogger("stocks.universe")

CACHE = datadir.path("universe.json")
TTL = 7 * 86400
UA = {"User-Agent": "NobodiScreener/1.0 (stock screener; contact: admin@localhost)"}
TICKER_RE = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")

SOURCES = {
    "sp500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "sp400": "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
    "ndx100": "https://en.wikipedia.org/wiki/Nasdaq-100",
}


def _strip(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).replace("&amp;", "&").strip()


def parse_constituents(html: str) -> list[str]:
    """หาตารางที่มีหัวคอลัมน์ Symbol/Ticker แล้วดึงคอลัมน์นั้น (ตารางแรกที่เข้าเงื่อนไข)"""
    for tbl in re.findall(r"<table[^>]*>.*?</table>", html, flags=re.S | re.I):
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, flags=re.S | re.I)
        if len(rows) < 20:
            continue
        head = [_strip(x).lower() for x in re.findall(r"<th[^>]*>(.*?)</th>", rows[0], flags=re.S | re.I)]
        idx = next((i for i, h in enumerate(head) if h in ("symbol", "ticker", "ticker symbol")), None)
        if idx is None:
            continue
        out = []
        for r in rows[1:]:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, flags=re.S | re.I)
            if len(cells) <= idx:
                continue
            t = _strip(cells[idx]).upper().replace("-", ".")
            if TICKER_RE.match(t):
                out.append(t)
        if len(out) >= 20:
            return out
    return []


def _read_cache() -> dict:
    try:
        with open(CACHE) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def extra_from_env() -> list[str]:
    raw = os.getenv("EXTRA_TICKERS", "")
    return [t for t in re.split(r"[\s,]+", raw.upper()) if TICKER_RE.match(t)]


def merged(base: list[str]) -> list[str]:
    c = _read_cache().get("lists", {})
    seq = list(base)
    for k in SOURCES:
        seq += c.get(k, [])
    seq += extra_from_env()
    return list(dict.fromkeys(seq))


async def refresh(base: list[str], force: bool = False) -> list[str]:
    """คืนรายชื่อรวมล่าสุด (ดึงใหม่ถ้าแคชเก่าเกิน 7 วัน)"""
    cache = _read_cache()
    if not force and time.time() - float(cache.get("at", 0)) < TTL and cache.get("lists"):
        return merged(base)

    lists = dict(cache.get("lists", {}))
    async with httpx.AsyncClient(timeout=30, headers=UA, follow_redirects=True) as cl:
        for name, url in SOURCES.items():
            try:
                r = await cl.get(url)
                r.raise_for_status()
                t = parse_constituents(r.text)
                if len(t) >= {"sp500": 400, "sp400": 300, "ndx100": 80}[name]:
                    lists[name] = list(dict.fromkeys(t))
                else:
                    log.warning("universe: %s parsed only %d tickers; keeping previous", name, len(t))
            except Exception as e:  # noqa: BLE001
                log.warning("universe: fetch %s failed: %s", name, type(e).__name__)
    try:
        tmp = CACHE + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({"at": time.time(), "lists": lists}, fh)
        os.replace(tmp, CACHE)
    except OSError as e:
        log.warning("universe: cannot save cache: %s", e)
    return merged(base)
