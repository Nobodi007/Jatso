"""รายชื่อหุ้นที่ screener สแกน = ลิสต์พื้นฐานเดิม + S&P 500 + S&P 400 + Nasdaq-100 (+ EXTRA_TICKERS)

ดึงรายชื่อจาก Wikipedia สัปดาห์ละครั้ง เก็บแคชไว้ในไฟล์ ถ้าดึงไม่ได้จะใช้แคชเก่า/ลิสต์พื้นฐานต่อ ระบบไม่ล่ม
(Wikipedia แก้ไขได้โดยคนทั่วไป จึงกรองรูปแบบ ticker ให้เข้มและตัดทิ้งถ้ารูปแบบแปลก)
"""
import asyncio
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
RETRY_AFTER = 3600           # แหล่งที่ดึงไม่สำเร็จ ลองใหม่ได้ทุก 1 ชม. (ไม่ใช่ทุกรอบของลูป)
# Wikimedia ขอให้บอกตัวตน/ช่องทางติดต่อใน User-Agent (ตัวที่คลุมเครือโดน 403 ได้) Render ตั้ง RENDER_EXTERNAL_URL ให้อัตโนมัติ
_CONTACT = os.getenv("UNIVERSE_CONTACT") or os.getenv("RENDER_EXTERNAL_URL") or "https://example.com"
UA = {"User-Agent": f"NobodiScreener/1.0 ({_CONTACT}; stock screener) python-httpx"}
TICKER_RE = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")

PAGES = {"sp500": "List_of_S%26P_500_companies", "sp400": "List_of_S%26P_400_companies", "ndx100": "Nasdaq-100"}
MIN_COUNT = {"sp500": 400, "sp400": 300, "ndx100": 80}
SOURCES = {k: None for k in PAGES}                       # (คงชื่อเดิมไว้ให้ส่วนอื่นอ้างอิง)
WIKI_PAGE = "https://en.wikipedia.org/wiki/"
WIKI_API = "https://en.wikipedia.org/w/api.php?action=parse&format=json&formatversion=2&prop=text&redirects=1&page="
CSV_SP500 = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"

_lock = asyncio.Lock()
_fail_at: dict[str, float] = {}


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


def extra_from_file() -> list[str]:
    """สำรองกรณี Wikipedia ใช้ไม่ได้: วางรายชื่อหุ้น (คั่นด้วยเว้นวรรค/คอมมา/ขึ้นบรรทัดใหม่) ไว้ที่ DATA_DIR/universe_extra.txt"""
    try:
        with open(datadir.path("universe_extra.txt")) as fh:
            return [t for t in re.split(r"[\s,]+", fh.read().upper()) if TICKER_RE.match(t)]
    except OSError:
        return []


def merged(base: list[str]) -> list[str]:
    c = _read_cache().get("lists", {})
    seq = list(base)
    for k in SOURCES:
        seq += c.get(k, [])
    seq += extra_from_env()
    seq += extra_from_file()
    return list(dict.fromkeys(seq))


def _parse_csv(text: str) -> list[str]:
    out = []
    for line in text.splitlines()[1:]:
        t = line.split(",", 1)[0].strip().strip('"').upper().replace("-", ".")
        if TICKER_RE.match(t):
            out.append(t)
    return out


async def _fetch_one(cl, name: str) -> list[str]:
    """ลองทีละช่องทางจนได้จำนวนที่สมเหตุสมผล : หน้าเว็บ Wikipedia → API ของ Wikipedia → (sp500) CSV จาก GitHub"""
    errs = []
    attempts = [("page", WIKI_PAGE + PAGES[name]), ("api", WIKI_API + PAGES[name])]
    if name == "sp500":
        attempts.append(("csv", CSV_SP500))
    for kind, url in attempts:
        try:
            r = await cl.get(url)
            r.raise_for_status()
            if kind == "api":
                t = parse_constituents(r.json()["parse"]["text"])
            elif kind == "csv":
                t = _parse_csv(r.text)
            else:
                t = parse_constituents(r.text)
            if len(t) >= MIN_COUNT[name]:
                log.info("universe: %s via %s -> %d tickers", name, kind, len(t))
                return list(dict.fromkeys(t))
            errs.append(f"{kind}: parsed {len(t)}")
        except Exception as e:  # noqa: BLE001
            errs.append(f"{kind}: {str(e)[:60] or type(e).__name__}")
    raise RuntimeError("; ".join(errs))


async def refresh(base: list[str], force: bool = False) -> list[str]:
    """คืนรายชื่อรวมล่าสุด ดึงเฉพาะแหล่งที่แคชเก่าเกิน 7 วัน (แต่ละแหล่งนับแยกกัน) แหล่งที่เพิ่งล้มเหลวจะรอ 1 ชม.ก่อนลองใหม่"""
    async with _lock:                                   # ลูปสองตัวเรียกพร้อมกันได้ ดึงจริงครั้งเดียว
        cache = _read_cache()
        lists = dict(cache.get("lists", {}))
        at = cache.get("at", {})
        if not isinstance(at, dict):                    # รูปแบบเก่า (ตัวเลขเดียว)
            at = {k: at for k in lists}
        now = time.time()
        todo = [n for n in PAGES
                if (force or now - float(at.get(n, 0)) >= TTL or n not in lists)
                and now - _fail_at.get(n, 0) >= RETRY_AFTER]
        if todo:
            async with httpx.AsyncClient(timeout=30, headers=UA, follow_redirects=True) as cl:
                for name in todo:
                    try:
                        lists[name] = await _fetch_one(cl, name)
                        at[name] = now
                        _fail_at.pop(name, None)
                    except Exception as e:  # noqa: BLE001
                        _fail_at[name] = now
                        log.warning("universe: %s failed (%s)", name, e)
            try:
                tmp = CACHE + ".tmp"
                with open(tmp, "w") as fh:
                    json.dump({"at": at, "lists": lists}, fh)
                os.replace(tmp, CACHE)
            except OSError as e:
                log.warning("universe: cannot save cache: %s", e)
        return merged(base)
