"""ตัวจำกัดอัตราต่อผู้ใช้ (sliding window ในหน่วยความจำ) — ของ Backtest Lab เอง ไม่ใช้ตัวนับร่วมกับระบบเดิม"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Callable


class RateLimiter:
    def __init__(self, limit: int, window_s: float, now_fn: Callable[[], float] = time.monotonic):
        self.limit, self.window, self.now = limit, window_s, now_fn
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        t = self.now()
        with self._lock:
            q = self._hits[key]
            while q and t - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(t)
            return True
