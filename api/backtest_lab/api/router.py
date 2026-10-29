"""FastAPI router ของ Backtest Lab (ชั้นบางมาก — ตรรกะอยู่ใน handlers.py)

Prefix: /api/backtest-lab   (เลี่ยงชนกับเส้นทาง /api/stocks/{symbol}/... ของระบบเดิม)
หมายเหตุ: ไฟล์นี้ import fastapi และยังไม่ได้ถูกรันจริงในสภาพแวดล้อมที่เขียน (ไม่มี fastapi) ต้องทดสอบหลังวางเข้า repo
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Header, HTTPException
from fastapi.responses import JSONResponse

from . import handlers as H
from .auth import AuthError, decode_email

router = APIRouter(prefix="/api/backtest-lab", tags=["backtest-lab"])
_services: H.Services | None = None


def services() -> H.Services:
    global _services
    if _services is None:
        _services = H.Services.from_env()
    return _services


def _email(authorization: str) -> str:
    try:
        return decode_email(authorization)
    except AuthError as e:
        raise HTTPException(e.status, e.code)


def _out(res: tuple[int, dict]) -> JSONResponse:
    return JSONResponse(res[1], status_code=res[0], headers={"Cache-Control": "no-store"})


@router.get("/meta")
async def meta(authorization: str = Header(default="")):
    _email(authorization)
    return _out(H.meta())


@router.post("/runs")
async def create_run(body: dict = Body(...), authorization: str = Header(default="")):
    return _out(await H.create_run(services(), _email(authorization), body))


@router.get("/runs")
async def list_runs(authorization: str = Header(default="")):
    return _out(await H.list_runs(services(), _email(authorization)))


@router.get("/runs/{run_id}")
async def get_run(run_id: str, authorization: str = Header(default="")):
    return _out(await H.get_run(services(), _email(authorization), run_id))


@router.delete("/runs/{run_id}")
async def delete_run(run_id: str, authorization: str = Header(default="")):
    return _out(await H.delete_run(services(), _email(authorization), run_id))
