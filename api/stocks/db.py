import logging
import os
import time

import httpx
from fastapi import HTTPException

log = logging.getLogger("stocks.db")

SB_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SB_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
_client = httpx.AsyncClient(timeout=10)

# --- ตัวนับ byte ที่รับจาก Supabase ต่อตาราง (ใช้หาว่าอะไรกิน Egress) ---
# นับเฉพาะ query ที่เรียกผ่าน sb() นี้ ไม่รวมโค้ดส่วนอื่นที่ต่อ Supabase เอง
# เขียน log 1 บรรทัดทุก _WINDOW_S วินาที (เมื่อมีการเรียก) แล้วเริ่มนับใหม่
_WINDOW_S = 600
_bytes: dict[str, int] = {}
_calls: dict[str, int] = {}
_win_start = time.monotonic()


def _track(table: str, n: int) -> None:
    global _win_start
    try:
        _bytes[table] = _bytes.get(table, 0) + n
        _calls[table] = _calls.get(table, 0) + 1
        now = time.monotonic()
        if now - _win_start >= _WINDOW_S:
            top = sorted(_bytes.items(), key=lambda kv: -kv[1])[:8]
            log.warning("sb_bytes window=%ds total_bytes=%d total_calls=%d top=%s",
                        int(now - _win_start), sum(_bytes.values()), sum(_calls.values()),
                        [(t, b, _calls[t]) for t, b in top])
            _bytes.clear()
            _calls.clear()
            _win_start = now
    except Exception:  # ตัวนับต้องไม่ทำให้ query พัง
        pass


class SbError(Exception):
    """Raw PostgREST error (opt-in via raw_error=True) so callers can read RPC error text."""
    def __init__(self, status: int, body: str):
        super().__init__(f"{status}: {body[:300]}")
        self.status, self.body = status, body


async def sb(method: str, table: str, *, params: dict | None = None,
             json=None, prefer: str | None = None, raw_error: bool = False):
    """เรียก Supabase ทุก query ต้องกรอง user_email เอง เพราะ service role ข้าม RLS"""
    if not SB_URL or not SB_KEY:
        raise HTTPException(503, "db_not_configured")

    headers = {
        "apikey": SB_KEY,
        "Authorization": f"Bearer {SB_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer

    try:
        resp = await _client.request(
            method, f"{SB_URL}/rest/v1/{table}", params=params, json=json, headers=headers
        )
    except httpx.HTTPError as e:
        log.warning("supabase network error: %s", e)
        raise HTTPException(502, "db_error")

    _track(table, len(resp.content or b""))

    if raw_error and resp.status_code >= 400:
        raise SbError(resp.status_code, resp.text)
    if resp.status_code == 409:
        raise HTTPException(409, "already_exists")
    if resp.status_code >= 400:
        log.warning("supabase %s %s -> %s %s", method, table, resp.status_code, resp.text[:300])
        raise HTTPException(502, "db_error")
    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()
