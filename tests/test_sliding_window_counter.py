import asyncio
import time

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
    """A full-capacity burst in one window should not be immediately followed
    by another full burst at the same phase of the next window."""
    window = 0.3
    limiter = SlidingWindowCounterLimiter(store, capacity=4, window_seconds=window)

    # Windows are clock-aligned, so align to just after a boundary before
    # starting. Without this the burst lands at an arbitrary phase, and how
    # much of it still carries over one window later is wall-clock luck --
    # which made this test pass or fail at random.
    await asyncio.sleep(window - (time.time() % window) + 0.01)

    for _ in range(4):
        assert (await limiter.check("user-1")).allowed

    await asyncio.sleep(window)  # same phase, one window on

    # The previous window is still ~95% weighted in, so a second full-capacity
    # burst must not get through.
    allowed_count = sum([(await limiter.check("user-1")).allowed for _ in range(4)])
    assert allowed_count < 4


@pytest.mark.asyncio
async def test_reset_after_within_window_bounds(store):
    limiter = SlidingWindowCounterLimiter(store, capacity=5, window_seconds=0.3)
    result = await limiter.check("user-1")
    assert 0 < result.reset_after <= 0.3


@pytest.mark.asyncio
async def test_reset_after_decreases_within_the_same_window(store):
    window = 0.3
    limiter = SlidingWindowCounterLimiter(store, capacity=5, window_seconds=window)
    # Align to just after a boundary so both checks land in the same window
    # (otherwise which window each check falls in is wall-clock luck).
    await asyncio.sleep(window - (time.time() % window) + 0.01)

    first = await limiter.check("user-1")
    await asyncio.sleep(0.05)
    second = await limiter.check("user-1")
    assert second.reset_after < first.reset_after


@pytest.mark.asyncio
async def test_concurrent_requests_never_exceed_capacity(store):
    """Fires more concurrent requests than the window has room for and
    asserts the total allowed count never exceeds capacity -- this is the
    race condition incr_weighted_if_under_capacity() exists to prevent.
    window_seconds is large so all 50 requests reliably land in the same
    window regardless of how long the gather takes to run."""
    limiter = SlidingWindowCounterLimiter(store, capacity=5, window_seconds=10)
    results = await asyncio.gather(*[limiter.check("user-1") for _ in range(50)])
    allowed_count = sum(r.allowed for r in results)
    assert allowed_count == 5
