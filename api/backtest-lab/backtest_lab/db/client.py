"""Supabase (PostgREST) client ของ Backtest Lab — เขียนเอง ไม่ใช้ api/stocks/db.py ของเดิม

- sync + stdlib urllib (เรียกจาก thread) ; ส่งตัวส่งคำขอ (transport) เข้ามาเพื่อทดสอบได้
- service role ข้าม RLS => ผู้เรียกต้องกรอง email เองทุก query (RunStore ทำให้ทุกเมธอด)
- ข้อความ error ไม่มี URL/คีย์
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional


class DbError(Exception):
    def __init__(self, status: int, message: str = "db_error"):
        super().__init__(f"{status}: {message}")
        self.status = status


Transport = Callable[[str, str, dict, Optional[bytes]], tuple[int, bytes]]


def _urllib_transport(method: str, url: str, headers: dict, body: Optional[bytes]) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        raise DbError(0, type(e).__name__) from e


class SbClient:
    def __init__(self, url: str, key: str, transport: Transport = _urllib_transport):
        self.url, self.key, self.transport = url.rstrip("/"), key, transport

    @classmethod
    def from_env(cls) -> "SbClient | None":
        url, key = os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        return cls(url, key) if url and key else None

    def request(self, method: str, table: str, *, params: dict | None = None, json_body=None, prefer: str | None = None):
        q = ("?" + urllib.parse.urlencode(params)) if params else ""
        headers = {"apikey": self.key, "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        if prefer:
            headers["Prefer"] = prefer
        body = json.dumps(json_body).encode("utf-8") if json_body is not None else None
        status, raw = self.transport(method, f"{self.url}/rest/v1/{table}{q}", headers, body)
        if status >= 400:
            raise DbError(status)                       # ไม่แนบ body/URL
        if status == 204 or not raw:
            return None
        return json.loads(raw)
