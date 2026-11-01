"""endpoint ของ Sweep / Walk-forward / เทียบกลยุทธ์สุ่ม — คำนวณตามสั่ง ไม่เก็บลงฐานข้อมูล (ทำซ้ำได้)

ใช้ run_store/price_store/pool ชุดเดียวกับระบบหลัก; ทุกการอ่านกรองตาม email; งานหนักจำกัด 8 ครั้ง/10 นาที/ผู้ใช้
งานที่หมดเวลาจะถูกสั่งหยุด (cancel) ไม่ปล่อยให้กิน CPU ต่อ"""
from __future__ import annotations

import asyncio
import hashlib
import itertools
from datetime import date, timedelta

from .. import config as C
from ..api.handlers import Services
from ..data.total_return import load_market
from ..engine.rules import warmup_bars
from ..jobs.limiter import RateLimiter
from . import baseline as BL
from . import search as SR
from .handlers import _err, _int, _load_done_run

_limiter = RateLimiter(8, 600)


async def _compute(s: Services, fn):
    box: dict = {}

    def job(cancel):
        try:
            box["out"] = fn(cancel)
        except SR.Aborted:
            box["aborted"] = True
        except Exception as e:
            box["err"] = e

    done = await s.pool.run(job)
    return done, box


def _timeout():
    return 504, {"code": "timeout", "message": f"คำนวณนานเกิน {C.RUN_TIMEOUT_SECONDS} วินาที ลองลดจำนวนค่าที่ทดลองหรือจำนวน fold"}


def _load_for_variants(spec: dict, chosen: list, grids: list, price_store):
    """โหลดราคาโดยเผื่อประวัติก่อนวันเริ่มให้พอสำหรับ 'ทุกชุดค่า' (ค่าช่วงยาวต้องใช้ประวัติมากกว่าค่าเดิม)"""
    warm = warmup_bars(spec["strategy"])
    for vals in itertools.product(*grids):
        var = SR.make_variant(spec, chosen, vals)
        if var is not None:
            warm = max(warm, warmup_bars(var["strategy"]))
    start, end = date.fromisoformat(spec["start"]), date.fromisoformat(spec["end"])
    return load_market(spec, price_store, start - timedelta(days=30 + int(warm * 1.5) + 7), end)


async def tunables(s: Services, email: str, run_id: str) -> tuple[int, dict]:
    row = await asyncio.to_thread(s.run_store.get, email, run_id)
    if not row:
        return 404, {"code": "not_found", "message": "ไม่พบรายการ"}
    t = SR.public_tunables(row["spec"])
    return 200, {"tunables": t, "metrics": [{"key": k, "label": SR.METRIC_LABEL[k]} for k in SR.METRICS],
                 "limits": {"max_params": SR.MAX_PARAMS, "max_values": SR.MAX_VALUES, "max_cells": SR.MAX_CELLS,
                            "max_wf_runs": SR.MAX_WF_RUNS}}


def _metric(body: dict, default: str = "calmar") -> str:
    m = body.get("metric", default)
    if m not in SR.METRICS:
        raise ValueError(f"metric ต้องเป็นหนึ่งใน {', '.join(SR.METRICS)}")
    return m


async def _prepare(s, email, run_id, body):
    body = body if isinstance(body, dict) else {}
    row, bad = await _load_done_run(s, email, run_id)
    if bad:
        return None, None, bad
    if not row["spec"].get("strategy"):
        return None, None, (400, {"code": "no_strategy", "message": "รันนี้ไม่มีกลยุทธ์ (ไม่มีพารามิเตอร์ให้ค้นหา)"})
    if not _limiter.allow(email):
        return None, None, (429, {"code": "rate_limited", "message": "ใช้งานบ่อยเกินไป กรุณารอสักครู่ (งานค้นหาจำกัด 8 ครั้งต่อ 10 นาที)"})
    return row, body, None


async def sweep(s: Services, email: str, run_id: str, body) -> tuple[int, dict]:
    row, body, bad = await _prepare(s, email, run_id, body)
    if bad:
        return bad
    spec = row["spec"]
    try:
        metric = _metric(body)
        chosen, grids = SR.parse_selection(spec, body.get("params"))
    except ValueError as e:
        return 400, {"code": "invalid_params", "message": str(e)}

    def fn(cancel):
        mk = _load_for_variants(spec, chosen, grids, s.price_store)
        return SR.sweep(spec, mk, chosen, grids, metric, cancel)

    done, box = await _compute(s, fn)
    if not done or box.get("aborted"):
        return _timeout()
    if "err" in box:
        return _err(box["err"])
    return 200, box["out"]


async def walkforward(s: Services, email: str, run_id: str, body) -> tuple[int, dict]:
    row, body, bad = await _prepare(s, email, run_id, body)
    if bad:
        return bad
    spec = row["spec"]
    try:
        metric = _metric(body)
        folds = _int(body, "folds", 4, 2, 6)
        anchored = body.get("anchored", True)
        if not isinstance(anchored, bool):
            raise ValueError("anchored ต้องเป็น true/false")
        chosen, grids = SR.parse_selection(spec, body.get("params"))
    except ValueError as e:
        return 400, {"code": "invalid_params", "message": str(e)}
    dates = [x["date"] for x in row["result"]["series"]]

    def fn(cancel):
        mk = _load_for_variants(spec, chosen, grids, s.price_store)
        return SR.walk_forward(spec, mk, dates, chosen, grids, metric, folds, anchored, cancel)

    done, box = await _compute(s, fn)
    if not done or box.get("aborted"):
        return _timeout()
    if "err" in box:
        return _err(box["err"])
    return 200, box["out"]


async def random_baseline(s: Services, email: str, run_id: str, body) -> tuple[int, dict]:
    row, body, bad = await _prepare(s, email, run_id, body)
    if bad:
        return bad
    spec = row["spec"]
    try:
        m = body.get("metric", "calmar")
        if m not in BL.BASELINE_METRICS:
            raise ValueError(f"metric ต้องเป็นหนึ่งใน {', '.join(BL.BASELINE_METRICS)}")
        sims = _int(body, "sims", 1000, BL.MIN_SIMS, BL.MAX_SIMS)
        trials = _int(body, "trials", 1, 1, 1_000_000)
        default_seed = int(hashlib.sha256(run_id.encode()).hexdigest()[:8], 16) & 0x7FFFFFFF
        seed = _int(body, "seed", default_seed, 0, 2**31 - 1)
    except ValueError as e:
        return 400, {"code": "invalid_params", "message": str(e)}
    result = row["result"]

    def fn(cancel):
        from .data import load_bars
        return BL.random_baseline(spec, load_bars(spec, s.price_store), result, m, sims, seed, trials, cancel)

    done, box = await _compute(s, fn)
    if not done or box.get("aborted"):
        return _timeout()
    if "err" in box:
        return _err(box["err"])
    return 200, box["out"]
