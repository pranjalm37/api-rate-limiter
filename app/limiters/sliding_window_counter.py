import time

from app.limiters.base import RateLimitResult, RateLimiter
from app.storage.base import Store


class SlidingWindowCounterLimiter(RateLimiter):
    """Approximates a sliding window using just two fixed-window counters
    (current + previous), weighted by how far the clock has moved into the
    current window. Cheap like fixed window, but smooths out the boundary
    burst problem instead of eliminating it outright like the log variant."""

    name = "sliding_window_counter"

    def __init__(self, store: Store, capacity: int, window_seconds: float) -> None:
        self.store = store
        self.capacity = capacity
        self.window_seconds = window_seconds

    async def check(self, key: str) -> RateLimitResult:
        now = time.time()
        window_index = int(now // self.window_seconds)
        elapsed_fraction = (now % self.window_seconds) / self.window_seconds

        current_key = f"swc:{key}:{window_index}"
        previous_key = f"swc:{key}:{window_index - 1}"

        current_count = await self.store.get_counter(current_key)
        previous_count = await self.store.get_counter(previous_key)

        weighted_count = previous_count * (1 - elapsed_fraction) + current_count
        allowed = weighted_count < self.capacity

        if allowed:
            current_count = await self.store.incr_and_get(current_key, self.window_seconds * 2)
            weighted_count = previous_count * (1 - elapsed_fraction) + current_count

        remaining = max(int(self.capacity - weighted_count), 0)
        retry_after = 0.0 if allowed else self.window_seconds * (1 - elapsed_fraction)
        return RateLimitResult(
            allowed=allowed,
            limit=self.capacity,
            remaining=remaining,
            retry_after=retry_after,
        )

    async def peek(self, key: str) -> int:
        now = time.time()
        window_index = int(now // self.window_seconds)
        elapsed_fraction = (now % self.window_seconds) / self.window_seconds

        current = await self.store.get_counter(f"swc:{key}:{window_index}")
        previous = await self.store.get_counter(f"swc:{key}:{window_index - 1}")
        weighted = previous * (1 - elapsed_fraction) + current
        return max(int(self.capacity - weighted), 0)
