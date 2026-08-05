from app.limiters.base import RateLimitResult, RateLimiter
from app.storage.base import Store


class FixedWindowLimiter(RateLimiter):
    """Counts requests in fixed-size, non-overlapping windows (e.g. per calendar
    minute). Simplest algorithm and cheap (one counter per key), but a burst
    can hit `capacity` right at the end of one window and again right at the
    start of the next -- up to 2x capacity in a short span at the boundary."""

    name = "fixed_window"

    def __init__(self, store: Store, capacity: int, window_seconds: float) -> None:
        self.store = store
        self.capacity = capacity
        self.window_seconds = window_seconds

    async def check(self, key: str) -> RateLimitResult:
        storage_key = f"fw:{key}"
        count = await self.store.incr_and_get(storage_key, self.window_seconds)
        allowed = count <= self.capacity
        remaining = max(self.capacity - count, 0)
        retry_after = 0.0 if allowed else self.window_seconds
        return RateLimitResult(
            allowed=allowed,
            limit=self.capacity,
            remaining=remaining,
            retry_after=retry_after,
        )

    async def peek(self, key: str) -> int:
        count = await self.store.get_counter(f"fw:{key}")
        return max(self.capacity - count, 0)
