"""เพิ่มเส้นทาง Monte Carlo / Robustness เข้า router หลักของ Backtest Lab (เรียกจากท้าย api/router.py)"""
from __future__ import annotations

from fastapi import Body, Header

from . import handlers as RH


def register(router, services, email_fn, out_fn) -> None:
    @router.post("/runs/{run_id}/montecarlo")
    async def montecarlo(run_id: str, body: dict = Body(default={}), authorization: str = Header(default="")):
        return out_fn(await RH.montecarlo(services(), email_fn(authorization), run_id, body))

    @router.post("/runs/{run_id}/robustness")
    async def robustness(run_id: str, body: dict = Body(default={}), authorization: str = Header(default="")):
        return out_fn(await RH.run_robustness(services(), email_fn(authorization), run_id, body))
