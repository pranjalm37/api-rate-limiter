from enum import Enum

from app.limiters.base import RateLimiter, RateLimitResult
from app.limiters.fixed_window import FixedWindowLimiter
from app.limiters.sliding_window_counter import SlidingWindowCounterLimiter
from app.limiters.sliding_window_log import SlidingWindowLogLimiter
from app.limiters.token_bucket import TokenBucketLimiter
from app.storage.base import Store


class Algorithm(str, Enum):
    FIXED_WINDOW = "fixed_window"
    SLIDING_WINDOW_LOG = "sliding_window_log"
    SLIDING_WINDOW_COUNTER = "sliding_window_counter"
    TOKEN_BUCKET = "token_bucket"


def build_limiter(
    algorithm: Algorithm,
    store: Store,
    capacity: int,
    window_seconds: float,
    refill_rate: float,
) -> RateLimiter:
    if algorithm == Algorithm.FIXED_WINDOW:
        return FixedWindowLimiter(store, capacity, window_seconds)
    if algorithm == Algorithm.SLIDING_WINDOW_LOG:
        return SlidingWindowLogLimiter(store, capacity, window_seconds)
    if algorithm == Algorithm.SLIDING_WINDOW_COUNTER:
        return SlidingWindowCounterLimiter(store, capacity, window_seconds)
    if algorithm == Algorithm.TOKEN_BUCKET:
        return TokenBucketLimiter(store, capacity, refill_rate)
    raise ValueError(f"Unknown algorithm: {algorithm}")


__all__ = [
    "Algorithm",
    "RateLimiter",
    "RateLimitResult",
    "build_limiter",
    "FixedWindowLimiter",
    "SlidingWindowLogLimiter",
    "SlidingWindowCounterLimiter",
    "TokenBucketLimiter",
]
