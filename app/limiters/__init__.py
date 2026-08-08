from enum import Enum

from app.limiters.base import RateLimiter, RateLimitResult
from app.limiters.fixed_window import FixedWindowLimiter
from app.limiters.gcra import GCRALimiter
from app.limiters.sliding_window_counter import SlidingWindowCounterLimiter
from app.limiters.sliding_window_log import SlidingWindowLogLimiter
from app.limiters.token_bucket import TokenBucketLimiter
from app.storage.base import Store
from app.storage.gcra_store import GCRAStore


class Algorithm(str, Enum):
    FIXED_WINDOW = "fixed_window"
    SLIDING_WINDOW_LOG = "sliding_window_log"
    SLIDING_WINDOW_COUNTER = "sliding_window_counter"
    TOKEN_BUCKET = "token_bucket"
    GCRA = "gcra"


def build_limiter(
    algorithm: Algorithm,
    store: Store | GCRAStore,
    capacity: int,
    window_seconds: float,
    refill_rate: float,
) -> RateLimiter:
    if algorithm == Algorithm.FIXED_WINDOW:
        assert isinstance(store, Store)
        return FixedWindowLimiter(store, capacity, window_seconds)
    if algorithm == Algorithm.SLIDING_WINDOW_LOG:
        assert isinstance(store, Store)
        return SlidingWindowLogLimiter(store, capacity, window_seconds)
    if algorithm == Algorithm.SLIDING_WINDOW_COUNTER:
        assert isinstance(store, Store)
        return SlidingWindowCounterLimiter(store, capacity, window_seconds)
    if algorithm == Algorithm.TOKEN_BUCKET:
        assert isinstance(store, Store)
        return TokenBucketLimiter(store, capacity, refill_rate)
    if algorithm == Algorithm.GCRA:
        assert isinstance(store, GCRAStore)
        return GCRALimiter(store, capacity, refill_rate)
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
    "GCRALimiter",
]
