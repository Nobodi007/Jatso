"""endpoint ของ Monte Carlo / Robustness — ผลคำนวณตามสั่ง ไม่เก็บลงฐานข้อมูล (ทำซ้ำได้ด้วย seed)

ใช้ run_store/price_store/pool ชุดเดียวกับ handlers หลัก; ทุกการอ่านกรองตาม email"""
from __future__ import annotations

import asyncio
import hashlib

from .. import config as C
from ..api.handlers import Services
from ..data.provider_base import ProviderError
from ..data.validate import DataError
from ..jobs.limiter import RateLimiter
from . import montecarlo as MC
from .data import load_bars
from .stability import robustness

_limiter = RateLimiter(20, 600)


def _int(body: dict, key: str, default: int, lo: int, hi: int) -> int:
    v = body.get(key, default)
    if isinstance(v, bool) or not isinstance(v, int) or not (lo <= v <= hi):
        raise ValueError(f"{key} ต้องเป็นจำนวนเต็ม {lo}–{hi}")
    return v


async def _load_done_run(s: Services, email: str, run_id: str):
    row = await asyncio.to_thread(s.run_store.get, email, run_id)
    if not row:
        return None, (404, {"code": "not_found", "message": "ไม่พบรายการ"})
    if row.get("status") != "done" or not row.get("result"):
        return None, (409, {"code": "run_not_done", "message": "รันนี้ยังไม่เสร็จหรือไม่สำเร็จ"})
    return row, None


async def _compute(s: Services, fn):
    box: dict = {}

    def job(cancel):
        try:
            box["out"] = fn()
        except Exception as e:                     # ส่งต่อไปแปลงเป็น HTTP ด้านนอก
            box["err"] = e

    done = await s.pool.run(job)
    return done, box


def _err(e: Exception) -> tuple[int, dict]:
    if isinstance(e, (MC.MCError, ValueError)):
        return 400, {"code": "invalid_params", "message": str(e)}
    if isinstance(e, DataError):
        return 422, {"code": getattr(e, "code", "data_error"), "message": str(e)}
    if isinstance(e, ProviderError):
        return 502, {"code": "provider_error", "message": f"ดึงข้อมูลราคาไม่สำเร็จ: {e}"}
    return 500, {"code": "internal_error", "message": "เกิดข้อผิดพลาดภายในระบบ"}


async def montecarlo(s: Services, email: str, run_id: str, body) -> tuple[int, dict]:
    body = body if isinstance(body, dict) else {}
    row, bad = await _load_done_run(s, email, run_id)
    if bad:
        return bad
    try:
        sims = _int(body, "sims", 2000, 100, MC.MAX_SIMS)
        block = _int(body, "block_days", 21, 1, 252)
        years = body.get("years")
        horizon = None if years is None else _int(body, "years", 1, 1, 30) * MC.TRADING_DAYS
        default_seed = int(hashlib.sha256(run_id.encode()).hexdigest()[:8], 16) & 0x7FFFFFFF
        seed = _int(body, "seed", default_seed, 0, 2**31 - 1)
    except ValueError as e:
        return 400, {"code": "invalid_params", "message": str(e)}
    if not _limiter.allow(email):
        return 429, {"code": "rate_limited", "message": "ใช้งานบ่อยเกินไป กรุณารอสักครู่"}
    series = row["result"]["series"]

    def fn():
        rp = MC.returns_from_series(series, "portfolio")
        rb = MC.returns_from_series(series, "benchmark")
        return MC.simulate(rp, rb, sims=sims, horizon=horizon, block=block, seed=seed, actual_final=series[-1]["portfolio"])

    done, box = await _compute(s, fn)
    if not done:
        return 504, {"code": "timeout", "message": f"คำนวณนานเกิน {C.RUN_TIMEOUT_SECONDS} วินาที ลองลดจำนวนรอบ"}
    if "err" in box:
        return _err(box["err"])
    return 200, box["out"]


async def run_robustness(s: Services, email: str, run_id: str, body) -> tuple[int, dict]:
    body = body if isinstance(body, dict) else {}
    row, bad = await _load_done_run(s, email, run_id)
    if bad:
        return bad
    try:
        k = _int(body, "windows", 4, 2, 8)
    except ValueError as e:
        return 400, {"code": "invalid_params", "message": str(e)}
    do_sens = bool(body.get("sensitivity", True))
    if not _limiter.allow(email):
        return 429, {"code": "rate_limited", "message": "ใช้งานบ่อยเกินไป กรุณารอสักครู่"}
    spec, dates = row["spec"], [x["date"] for x in row["result"]["series"]]

    def fn():
        return robustness(spec, load_bars(spec, s.price_store), dates, k, do_sens)

    done, box = await _compute(s, fn)
    if not done:
        return 504, {"code": "timeout", "message": f"คำนวณนานเกิน {C.RUN_TIMEOUT_SECONDS} วินาที ลองลดจำนวนช่วง"}
    if "err" in box:
        return _err(box["err"])
    return 200, box["out"]
