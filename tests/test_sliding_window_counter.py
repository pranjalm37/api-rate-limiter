import asyncio

import pytest

from app.limiters.sliding_window_counter import SlidingWindowCounterLimiter


@pytest.mark.asyncio
async def test_allows_up_to_capacity(store):
    limiter = SlidingWindowCounterLimiter(store, capacity=3, window_seconds=10)
    results = [await limiter.check("user-1") for _ in range(3)]
    assert all(r.allowed for r in results)
    assert not (await limiter.check("user-1")).allowed


@pytest.mark.asyncio
async def test_smooths_across_window_boundary(store):
    """A full-capacity burst late in one window should not be immediately
    followed by another full burst at the very start of the next window."""
    limiter = SlidingWindowCounterLimiter(store, capacity=4, window_seconds=0.3)
    for _ in range(4):
        assert (await limiter.check("user-1")).allowed

    await asyncio.sleep(0.31)  # just into the next window
    # Previous window's count is still weighted in -- shouldn't allow 4 more immediately.
    allowed_count = sum([(await limiter.check("user-1")).allowed for _ in range(4)])
    assert allowed_count < 4
