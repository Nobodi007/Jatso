import asyncio
import time
from typing import Any, Awaitable, Callable


class ProviderError(Exception):
    """แหล่งข้อมูลภายนอกตอบผิดพลาด"""


class RateLimited(ProviderError):
    """โควต้าหมด"""


_store: dict[str, tuple[float, Any]] = {}
_stale: dict[str, Any] = {}
_locks: dict[str, asyncio.Lock] = {}
_quota: dict[str, tuple[float, int]] = {}
MAX_KEYS = 5000


async def cached(key: str, ttl: int, fetcher: Callable[[], Awaitable[Any]]) -> Any:
    hit = _store.get(key)
    if hit and hit[0] > time.time():
        return hit[1]

    # กันกรณีคนเปิดหุ้นตัวเดียวกันพร้อมกัน แล้วทุกคนยิง API ซ้ำ
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        hit = _store.get(key)
        if hit and hit[0] > time.time():
            return hit[1]
        try:
            data = await fetcher()
        except ProviderError:
            if key in _stale:
                return _stale[key]
            raise
        if len(_store) > MAX_KEYS:  # กันหน่วยความจำบวม
            _store.clear()
            _locks.clear()
        _store[key] = (time.time() + ttl, data)
        _stale[key] = data
        return data


def take_quota(name: str, limit: int, window_sec: int) -> bool:
    now = time.time()
    start, n = _quota.get(name, (now, 0))
    if now - start >= window_sec:
        start, n = now, 0
    n += 1
    _quota[name] = (start, n)
    return n <= limit
