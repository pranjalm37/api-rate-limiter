import asyncio

import pytest

from app.limiters.sliding_window_log import SlidingWindowLogLimiter


@pytest.mark.asyncio
async def test_allows_up_to_capacity(store):
    limiter = SlidingWindowLogLimiter(store, capacity=3, window_seconds=10)
    results = [await limiter.check("user-1") for _ in range(3)]
    assert all(r.allowed for r in results)
    assert not (await limiter.check("user-1")).allowed


@pytest.mark.asyncio
async def test_old_entries_expire_out_of_window(store):
    limiter = SlidingWindowLogLimiter(store, capacity=1, window_seconds=0.2)
    assert (await limiter.check("user-1")).allowed
    assert not (await limiter.check("user-1")).allowed

    await asyncio.sleep(0.25)
    assert (await limiter.check("user-1")).allowed


@pytest.mark.asyncio
async def test_no_boundary_double_burst(store):
    """Unlike fixed window, capacity should never be exceeded across a
    window boundary -- exactly `capacity` requests are allowed in ANY
    window_seconds-long slice of time."""
    limiter = SlidingWindowLogLimiter(store, capacity=2, window_seconds=0.3)
    assert (await limiter.check("user-1")).allowed
    assert (await limiter.check("user-1")).allowed
    await asyncio.sleep(0.15)
    # Still within the sliding window of the first two requests.
    assert not (await limiter.check("user-1")).allowed


@pytest.mark.asyncio
async def test_reset_after_reflects_oldest_entry(store):
    limiter = SlidingWindowLogLimiter(store, capacity=3, window_seconds=0.3)
    result = await limiter.check("user-1")
    assert 0 < result.reset_after <= 0.3


@pytest.mark.asyncio
async def test_reset_after_advances_as_the_oldest_entry_ages(store):
    limiter = SlidingWindowLogLimiter(store, capacity=5, window_seconds=0.3)
    first = await limiter.check("user-1")
    await asyncio.sleep(0.1)
    # The oldest entry (from `first`) hasn't aged out yet -- it's still the
    # one reset_after tracks, and it's 0.1s closer to expiring now.
    second = await limiter.check("user-1")
    assert second.reset_after < first.reset_after


@pytest.mark.asyncio
async def test_concurrent_requests_never_exceed_capacity(store):
    """Fires more concurrent requests than the window has room for and
    asserts the total allowed count never exceeds capacity -- this is the
    race condition zadd_if_under_capacity() exists to prevent. Against
    real Redis this used to let 16 through at capacity 5; MemoryStore's old
    per-call-locked approach happened not to show it (an accident of
    asyncio's scheduler, not a real guarantee) -- either way, this now
    locks in the atomic guarantee explicitly rather than incidentally."""
    limiter = SlidingWindowLogLimiter(store, capacity=5, window_seconds=10)
    results = await asyncio.gather(*[limiter.check("user-1") for _ in range(50)])
    allowed_count = sum(r.allowed for r in results)
    assert allowed_count == 5
