"""ซ่อนรายละเอียดของ 401 จากฟังก์ชัน auth เดิม โดยไม่ต้องแก้ตัวฟังก์ชัน

ใช้เป็น decorator เหนือ get_current_email: ถ้าฟังก์ชันเดิมโยน HTTPException 401
จะ log เหตุผลจริงฝั่ง server แล้วตอบผู้เรียกแค่ {"detail": "unauthorized"}
ไม่ log token หรือ header ใด ๆ มีเฉพาะข้อความที่ฟังก์ชันเดิมสร้างเอง (ตัดที่ 200 ตัวอักษร)
สถานะอื่นนอกจาก 401 และ exception ชนิดอื่นผ่านไปตามเดิม ไม่แตะ
"""
from __future__ import annotations

import functools
import inspect
import logging

from fastapi import HTTPException

log = logging.getLogger("stocks.auth")


def _deny(e: HTTPException) -> HTTPException:
    log.warning("auth rejected: %s", str(e.detail)[:200])
    return HTTPException(status_code=401, detail="unauthorized",
                         headers={"WWW-Authenticate": "Bearer"})


def sanitize_401(fn):
    if inspect.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except HTTPException as e:
                if e.status_code != 401:
                    raise
                raise _deny(e) from None
    else:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except HTTPException as e:
                if e.status_code != 401:
                    raise
                raise _deny(e) from None
    return wrapper
