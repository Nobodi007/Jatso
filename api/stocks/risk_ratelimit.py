"""Rate limit ต่อผู้ใช้ แบบนับในหน่วยความจำ (sliding window)

ข้อจำกัด: หายตอน restart และใช้ได้เฉพาะ instance เดียว (Render Free มี 1 instance)
ไม่ import อะไรจาก risk_api เพื่อกัน circular import: ส่งตัวดึงอีเมลเข้ามาเอง
"""
from __future__ import annotations

import time
from collections import deque

from fastapi import Depends, HTTPException

MAX_KEYS = 2000  # เพดานจำนวนผู้ใช้ที่จำไว้ กัน RAM โตไม่จำกัด (RAM ใกล้เพดาน)


def make_limiter(get_email, limit: int, window_s: int, name: str = "rl"):
    """คืน dependency: นับคำขอต่อ (ชื่อ, อีเมล) ถ้าเกิน limit ใน window_s วินาที ตอบ 429
    dependency นี้คืนค่าอีเมลเดิม ใช้แทน Depends(get_email) ได้เลย"""
    hits: dict[str, deque] = {}

    async def dep(email: str = Depends(get_email)) -> str:
        now = time.monotonic()
        q = hits.get(email)
        if q is None:
            if len(hits) >= MAX_KEYS:  # เต็ม: ล้างรายการที่หมดอายุทั้งหมดก่อน
                for k in [k for k, v in hits.items() if not v or now - v[-1] > window_s]:
                    del hits[k]
                if len(hits) >= MAX_KEYS:
                    raise HTTPException(429, "rate_limited", headers={"Retry-After": str(window_s)})
            q = hits[email] = deque()
        while q and now - q[0] > window_s:
            q.popleft()
        if len(q) >= limit:
            retry = max(1, int(window_s - (now - q[0])))
            raise HTTPException(429, "rate_limited", headers={"Retry-After": str(retry)})
        q.append(now)
        return email

    dep.__name__ = f"limiter_{name}"
    return dep
