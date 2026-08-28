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

        # Reads both counters and conditionally increments current_key as
        # one atomic operation -- the old get_counter + get_counter +
        # incr_and_get sequence (three separate calls) let concurrent
        # requests all read the same under-capacity weighted count before
        # any of them wrote back, overselling the window (confirmed
        # empirically: 50 concurrent requests at capacity=5 let 12 through).
        allowed, weighted_count = await self.store.incr_weighted_if_under_capacity(
            current_key, previous_key, 1 - elapsed_fraction, self.capacity, self.window_seconds * 2
        )

        remaining = max(int(self.capacity - weighted_count), 0)
        reset_after = self.window_seconds * (1 - elapsed_fraction)
        retry_after = 0.0 if allowed else reset_after
        return RateLimitResult(
            allowed=allowed,
            limit=self.capacity,
            remaining=remaining,
            retry_after=retry_after,
            reset_after=reset_after,
        )

    async def peek(self, key: str) -> int:
        now = time.time()
        window_index = int(now // self.window_seconds)
        elapsed_fraction = (now % self.window_seconds) / self.window_seconds

        current = await self.store.get_counter(f"swc:{key}:{window_index}")
        previous = await self.store.get_counter(f"swc:{key}:{window_index - 1}")
        weighted = previous * (1 - elapsed_fraction) + current
        return max(int(self.capacity - weighted), 0)
