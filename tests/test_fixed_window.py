import asyncio

import pytest

from app.limiters.fixed_window import FixedWindowLimiter


@pytest.mark.asyncio
async def test_allows_up_to_capacity(store):
    limiter = FixedWindowLimiter(store, capacity=3, window_seconds=10)
    results = [await limiter.check("user-1") for _ in range(3)]
    assert all(r.allowed for r in results)


@pytest.mark.asyncio
async def test_blocks_after_capacity(store):
    limiter = FixedWindowLimiter(store, capacity=3, window_seconds=10)
    for _ in range(3):
        await limiter.check("user-1")
    blocked = await limiter.check("user-1")
    assert not blocked.allowed
    assert blocked.remaining == 0


@pytest.mark.asyncio
async def test_resets_after_window(store):
    limiter = FixedWindowLimiter(store, capacity=1, window_seconds=0.2)
    first = await limiter.check("user-1")
    assert first.allowed
    blocked = await limiter.check("user-1")
    assert not blocked.allowed

    await asyncio.sleep(0.25)
    after_reset = await limiter.check("user-1")
    assert after_reset.allowed


@pytest.mark.asyncio
async def test_keys_are_independent(store):
    limiter = FixedWindowLimiter(store, capacity=1, window_seconds=10)
    a = await limiter.check("user-a")
    b = await limiter.check("user-b")
    assert a.allowed and b.allowed


@pytest.mark.asyncio
async def test_reset_after_reflects_window_ttl(store):
    limiter = FixedWindowLimiter(store, capacity=3, window_seconds=0.3)
    result = await limiter.check("user-1")
    assert 0 < result.reset_after <= 0.3

    await asyncio.sleep(0.15)
    later = await limiter.check("user-1")
    assert later.reset_after < result.reset_after


@pytest.mark.asyncio
async def test_reset_after_restarts_with_a_new_window(store):
    limiter = FixedWindowLimiter(store, capacity=1, window_seconds=0.2)
    await limiter.check("user-1")
    await asyncio.sleep(0.25)  # let the window fully expire

    fresh = await limiter.check("user-1")
    assert fresh.reset_after > 0.15  # back to close to the full window
