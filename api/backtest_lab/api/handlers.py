"""ตรรกะของ endpoint (ไม่พึ่ง FastAPI) -> ทดสอบได้ตรง ๆ ; router.py เป็นแค่ตัวแปลงเป็น HTTP

ทุกฟังก์ชันคืน (http_status, payload dict)"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Optional

from .. import config as C
from ..data.price_store import LayeredBackend, MemoryBackend, PriceStore, SupabaseBackend
from ..data.provider_yahoo import YahooProvider
from ..db.client import SbClient
from ..db.run_store import MemoryRunStore, RunStore, SupabaseRunStore
from ..engine import rules
from ..engine.indicators import catalogue as indicator_catalogue
from ..engine.spec import SpecError, spec_hash, validate_spec
from ..jobs.limiter import RateLimiter
from ..jobs.runner_pool import RunPool
from ..service import execute_run, mark_timeout, reconcile

log = logging.getLogger("backtest_lab")


@dataclass
class Services:
    run_store: RunStore
    price_store: PriceStore
    pool: RunPool
    limiter: RateLimiter
    tasks: set = field(default_factory=set)

    @classmethod
    def from_env(cls) -> "Services":
        client = SbClient.from_env()
        if client:
            run_store = SupabaseRunStore(client)
            backend = LayeredBackend(MemoryBackend(), SupabaseBackend(client.request))
        else:
            log.warning("backtest_lab: SUPABASE_* ไม่ถูกตั้งค่า ใช้ที่เก็บในหน่วยความจำ (ข้อมูลหายเมื่อรีสตาร์ต)")
            run_store, backend = MemoryRunStore(), MemoryBackend()
        return cls(run_store, PriceStore(YahooProvider(), backend),
                   RunPool(C.MAX_CONCURRENT_RUNS, C.RUN_TIMEOUT_SECONDS),
                   RateLimiter(C.RATE_LIMIT_RUNS, C.RATE_LIMIT_WINDOW_SECONDS))


def meta() -> tuple[int, dict]:
    return 200, {
        "engine_version": C.ENGINE_VERSION, "spec_version": C.SPEC_VERSION, "benchmark": C.BENCHMARK,
        "limits": {"max_symbols": C.MAX_SYMBOLS, "max_years": C.MAX_YEARS, "min_trading_days": C.MIN_TRADING_DAYS,
                   "min_capital": C.MIN_CAPITAL, "max_capital": C.MAX_CAPITAL,
                   "max_commission_bps": C.MAX_COMMISSION_BPS, "max_slippage_bps": C.MAX_SLIPPAGE_BPS},
        "defaults": {"commission_bps": C.DEFAULT_COMMISSION_BPS, "slippage_bps": C.DEFAULT_SLIPPAGE_BPS,
                     "execution": "next_open", "return_method": "price_return"},
        "indicators": indicator_catalogue(),
        "rule_language": {"operators": list(rules.OPS), "price_fields": list(rules.PRICE_FIELDS),
                          "max_nodes": rules.MAX_NODES, "max_depth": rules.MAX_DEPTH, "max_shift": rules.MAX_SHIFT,
                          "stops": ["stop_loss_pct", "take_profit_pct", "trailing_stop_pct", "max_hold_days"]},
        "retention_days": C.RETENTION_DAYS,
        "notice": "ผล Backtest เป็นข้อมูลจำลองย้อนหลัง ไม่ใช่ผลงานจริงและไม่ใช่การพยากรณ์ ไม่ใช่คำแนะนำการลงทุน",
    }


async def prune_expired(s: Services, email: str) -> int:
    """ลบผลที่เสร็จแล้วและเก่าเกิน RETENTION_DAYS ของผู้ใช้คนนี้ (ล้มเหลวไม่ทำให้คำขอหลักล้ม)"""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=C.RETENTION_DAYS)).isoformat()
    try:
        return await asyncio.to_thread(s.run_store.delete_finished_before, email, cutoff)
    except Exception:
        log.warning("backtest_lab: prune ล้มเหลว (ข้ามไป)")
        return 0


async def create_run(s: Services, email: str, body) -> tuple[int, dict]:
    if not isinstance(body, dict) or "spec" not in body:
        return 400, {"code": "invalid_body", "message": "ต้องส่ง {\"spec\": {...}}"}
    try:
        if len(json.dumps(body["spec"])) > C.MAX_SPEC_BYTES:
            return 413, {"code": "spec_too_large", "message": "spec ใหญ่เกินกำหนด"}
        spec = validate_spec(body["spec"])
    except (SpecError, TypeError, ValueError) as e:
        return 400, {"code": "invalid_spec", "message": str(e)}
    h = spec_hash(spec)

    await prune_expired(s, email)
    active = await asyncio.to_thread(s.run_store.find_active, email, h)       # กันรันซ้ำที่ยังไม่เสร็จ
    if active:
        return 200, {"id": active["id"], "status": active["status"], "duplicate": True}
    if not s.limiter.allow(email):
        return 429, {"code": "rate_limited", "message": "รันบ่อยเกินไป กรุณารอสักครู่"}
    if await asyncio.to_thread(s.run_store.count, email) >= C.MAX_STORED_RUNS_PER_USER:
        return 409, {"code": "too_many_runs", "message": f"เก็บผลได้สูงสุด {C.MAX_STORED_RUNS_PER_USER} รายการ กรุณาลบรายการเก่าก่อน"}

    row = await asyncio.to_thread(s.run_store.create, email, spec, h, C.ENGINE_VERSION)
    run_id = row["id"]
    task = asyncio.create_task(_run(s, run_id, email, spec))
    s.tasks.add(task)
    task.add_done_callback(s.tasks.discard)
    return 202, {"id": run_id, "status": "queued"}


async def _run(s: Services, run_id: str, email: str, spec: dict) -> None:
    try:
        await s.pool.run(execute_run, run_id, email, spec, s.run_store, s.price_store,
                         on_timeout=lambda: mark_timeout(run_id, email, s.run_store))
    except Exception:                                                            # ห้ามให้ task ตายเงียบ
        log.exception("backtest_lab: task crashed run=%s", run_id)
        try:
            await asyncio.to_thread(mark_timeout, run_id, email, s.run_store)
        except Exception:
            pass


async def get_run(s: Services, email: str, run_id: str) -> tuple[int, dict]:
    row = await asyncio.to_thread(s.run_store.get, email, run_id)
    if not row:
        return 404, {"code": "not_found", "message": "ไม่พบรายการ"}
    row = await asyncio.to_thread(reconcile, row, s.run_store, email)
    row.pop("email", None)
    return 200, row


async def list_runs(s: Services, email: str) -> tuple[int, dict]:
    await prune_expired(s, email)
    rows = await asyncio.to_thread(s.run_store.list, email, C.MAX_STORED_RUNS_PER_USER)
    return 200, {"runs": rows}


async def delete_run(s: Services, email: str, run_id: str) -> tuple[int, dict]:
    ok = await asyncio.to_thread(s.run_store.delete, email, run_id)
    return (200, {"deleted": True}) if ok else (404, {"code": "not_found", "message": "ไม่พบรายการ"})
