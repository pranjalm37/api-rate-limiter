import time
import uuid

from app.limiters.base import RateLimitResult, RateLimiter
from app.storage.base import Store


class SlidingWindowLogLimiter(RateLimiter):
    """Keeps a timestamped log of every request in the trailing `window_seconds`.
    Exact (no boundary burst like fixed window) because the window truly slides,
    but memory cost grows with request volume since every timestamp is stored."""

    name = "sliding_window_log"

    def __init__(self, store: Store, capacity: int, window_seconds: float) -> None:
        self.store = store
        self.capacity = capacity
        self.window_seconds = window_seconds

    async def check(self, key: str) -> RateLimitResult:
        storage_key = f"swl:{key}"
        now = time.time()
        window_start = now - self.window_seconds

        await self.store.zremrangebyscore(storage_key, 0, window_start)
        current = await self.store.zcard(storage_key)

        allowed = current < self.capacity
        if allowed:
            await self.store.zadd(storage_key, now, f"{now}:{uuid.uuid4().hex}")
            await self.store.expire(storage_key, self.window_seconds)
            current += 1

        remaining = max(self.capacity - current, 0)
        retry_after = 0.0 if allowed else self.window_seconds
        return RateLimitResult(
            allowed=allowed,
            limit=self.capacity,
            remaining=remaining,
            retry_after=retry_after,
        )

    async def peek(self, key: str) -> int:
        storage_key = f"swl:{key}"
        await self.store.zremrangebyscore(storage_key, 0, time.time() - self.window_seconds)
        return max(self.capacity - await self.store.zcard(storage_key), 0)
