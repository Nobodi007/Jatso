"""จำกัดงานพร้อมกันและเวลารัน — semaphore/timeout ของ Backtest Lab เอง

หมายเหตุ: timeout ยกเลิก "การรอ" ได้ แต่ thread ที่กำลังคำนวณหยุดกลางคันไม่ได้
จึงส่ง threading.Event (cancel) ให้ฟังก์ชันงานตรวจก่อนบันทึกผล เพื่อไม่ให้ผลเก่ามาทับสถานะ timeout
"""
from __future__ import annotations

import asyncio
import threading
from typing import Callable


class RunPool:
    def __init__(self, max_concurrent: int, timeout_s: float):
        self._sem = asyncio.Semaphore(max_concurrent)
        self.timeout_s = timeout_s

    async def run(self, fn: Callable[..., None], *args, on_timeout: Callable[[], None] | None = None) -> bool:
        """คืน True ถ้าเสร็จทันเวลา, False ถ้า timeout"""
        async with self._sem:                          # เวลารอคิวไม่นับรวมใน timeout
            cancel = threading.Event()
            try:
                await asyncio.wait_for(asyncio.to_thread(fn, *args, cancel), timeout=self.timeout_s)
                return True
            except asyncio.TimeoutError:
                cancel.set()
                if on_timeout:
                    on_timeout()
                return False
