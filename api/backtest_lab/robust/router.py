"""เพิ่มเส้นทาง Monte Carlo / Robustness / Search เข้า router หลักของ Backtest Lab (เรียกจากท้าย api/router.py)"""
from __future__ import annotations

from fastapi import Body, Header

from . import handlers as RH
from . import search_handlers as SH


def register(router, services, email_fn, out_fn) -> None:
    @router.post("/runs/{run_id}/montecarlo")
    async def montecarlo(run_id: str, body: dict = Body(default={}), authorization: str = Header(default="")):
        return out_fn(await RH.montecarlo(services(), email_fn(authorization), run_id, body))

    @router.post("/runs/{run_id}/robustness")
    async def robustness(run_id: str, body: dict = Body(default={}), authorization: str = Header(default="")):
        return out_fn(await RH.run_robustness(services(), email_fn(authorization), run_id, body))

    @router.get("/runs/{run_id}/tunables")
    async def tunables(run_id: str, authorization: str = Header(default="")):
        return out_fn(await SH.tunables(services(), email_fn(authorization), run_id))

    @router.post("/runs/{run_id}/sweep")
    async def sweep(run_id: str, body: dict = Body(default={}), authorization: str = Header(default="")):
        return out_fn(await SH.sweep(services(), email_fn(authorization), run_id, body))

    @router.post("/runs/{run_id}/walkforward")
    async def walkforward(run_id: str, body: dict = Body(default={}), authorization: str = Header(default="")):
        return out_fn(await SH.walkforward(services(), email_fn(authorization), run_id, body))

    @router.post("/runs/{run_id}/randombaseline")
    async def randombaseline(run_id: str, body: dict = Body(default={}), authorization: str = Header(default="")):
        return out_fn(await SH.random_baseline(services(), email_fn(authorization), run_id, body))
