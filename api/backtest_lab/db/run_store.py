"""ที่เก็บผลการรัน — ทุกเมธอดบังคับกรอง email (ผู้ใช้เห็น/แก้/ลบได้เฉพาะของตัวเอง)"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Optional, Protocol

from .client import SbClient

TABLE = "bt_runs"
LIST_COLS = "id,status,spec_hash,spec,error,created_at,finished_at,engine_version"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunStore(Protocol):
    def create(self, email: str, spec: dict, spec_hash: str, engine_version: str) -> dict: ...
    def get(self, email: str, run_id: str) -> Optional[dict]: ...
    def list(self, email: str, limit: int = 50) -> list[dict]: ...
    def count(self, email: str) -> int: ...
    def update(self, email: str, run_id: str, fields: dict) -> None: ...
    def delete(self, email: str, run_id: str) -> bool: ...
    def find_active(self, email: str, spec_hash: str) -> Optional[dict]: ...


class MemoryRunStore:
    def __init__(self):
        self._rows: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create(self, email, spec, spec_hash, engine_version):
        row = {"id": str(uuid.uuid4()), "email": email, "status": "queued", "spec": spec, "spec_hash": spec_hash,
               "engine_version": engine_version, "result": None, "error": None,
               "created_at": now_iso(), "finished_at": None}
        with self._lock:
            self._rows[row["id"]] = row
        return dict(row)

    def get(self, email, run_id):
        r = self._rows.get(run_id)
        return dict(r) if r and r["email"] == email else None

    def list(self, email, limit=50):
        rows = [r for r in self._rows.values() if r["email"] == email]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return [{k: v for k, v in r.items() if k not in ("result", "email")} for r in rows[:limit]]

    def count(self, email):
        return sum(1 for r in self._rows.values() if r["email"] == email)

    def update(self, email, run_id, fields):
        with self._lock:
            r = self._rows.get(run_id)
            if r and r["email"] == email:
                r.update(fields)

    def delete(self, email, run_id):
        with self._lock:
            r = self._rows.get(run_id)
            if r and r["email"] == email:
                del self._rows[run_id]
                return True
        return False

    def find_active(self, email, spec_hash):
        for r in self._rows.values():
            if r["email"] == email and r["spec_hash"] == spec_hash and r["status"] in ("queued", "running"):
                return dict(r)
        return None


class SupabaseRunStore:
    def __init__(self, client: SbClient):
        self.c = client

    def create(self, email, spec, spec_hash, engine_version):
        row = {"id": str(uuid.uuid4()), "email": email, "status": "queued", "spec": spec, "spec_hash": spec_hash,
               "engine_version": engine_version, "created_at": now_iso()}
        out = self.c.request("POST", TABLE, json_body=row, prefer="return=representation")
        return out[0] if out else row

    def get(self, email, run_id):
        rows = self.c.request("GET", TABLE, params={"email": f"eq.{email}", "id": f"eq.{run_id}",
                                                    "select": "*", "limit": "1"})
        return rows[0] if rows else None

    def list(self, email, limit=50):
        return self.c.request("GET", TABLE, params={"email": f"eq.{email}", "select": LIST_COLS,
                                                    "order": "created_at.desc", "limit": str(limit)}) or []

    def count(self, email):
        rows = self.c.request("GET", TABLE, params={"email": f"eq.{email}", "select": "id", "limit": "1000"}) or []
        return len(rows)

    def update(self, email, run_id, fields):
        self.c.request("PATCH", TABLE, params={"email": f"eq.{email}", "id": f"eq.{run_id}"}, json_body=fields)

    def delete(self, email, run_id):
        out = self.c.request("DELETE", TABLE, params={"email": f"eq.{email}", "id": f"eq.{run_id}"},
                             prefer="return=representation")
        return bool(out)

    def find_active(self, email, spec_hash):
        rows = self.c.request("GET", TABLE, params={"email": f"eq.{email}", "spec_hash": f"eq.{spec_hash}",
                                                    "status": "in.(queued,running)", "select": "id,status", "limit": "1"})
        return rows[0] if rows else None
