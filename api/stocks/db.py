import logging
import os

import httpx
from fastapi import HTTPException

log = logging.getLogger("stocks.db")

SB_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SB_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
_client = httpx.AsyncClient(timeout=10)


async def sb(method: str, table: str, *, params: dict | None = None,
             json=None, prefer: str | None = None):
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

    if resp.status_code == 409:
        raise HTTPException(409, "already_exists")
    if resp.status_code >= 400:
        log.warning("supabase %s %s -> %s %s", method, table, resp.status_code, resp.text[:300])
        raise HTTPException(502, "db_error")
    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()
