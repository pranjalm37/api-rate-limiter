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
        member = f"{now}:{uuid.uuid4().hex}"

        # Trim, count, and conditionally add as one atomic operation -- the
        # old zremrangebyscore + zcard + zadd sequence (three separate calls)
        # let concurrent requests all read the same under-capacity count
        # before any of them wrote back, overselling the window (confirmed
        # empirically: 50 concurrent requests at capacity=5 let 16 through).
        allowed, current = await self.store.zadd_if_under_capacity(
            storage_key, window_start, self.capacity, now, member, self.window_seconds
        )

        remaining = max(self.capacity - current, 0)

        oldest = await self.store.oldest_score(storage_key)
        reset_after = max(oldest + self.window_seconds - now, 0.0) if oldest is not None else 0.0
        retry_after = 0.0 if allowed else reset_after

        return RateLimitResult(
            allowed=allowed,
            limit=self.capacity,
            remaining=remaining,
            retry_after=retry_after,
            reset_after=reset_after,
        )

    async def peek(self, key: str) -> int:
        storage_key = f"swl:{key}"
        await self.store.zremrangebyscore(storage_key, 0, time.time() - self.window_seconds)
        return max(self.capacity - await self.store.zcard(storage_key), 0)
