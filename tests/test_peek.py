"""peek() must report remaining quota without consuming any -- if it had side
effects, the dashboard's own sampling would show up as traffic."""

import asyncio

import pytest

from app.limiters.fixed_window import FixedWindowLimiter
from app.limiters.sliding_window_counter import SlidingWindowCounterLimiter
from app.limiters.sliding_window_log import SlidingWindowLogLimiter
from app.limiters.token_bucket import TokenBucketLimiter


def all_limiters(store):
    return [
        FixedWindowLimiter(store, capacity=5, window_seconds=10),
        SlidingWindowLogLimiter(store, capacity=5, window_seconds=10),
        SlidingWindowCounterLimiter(store, capacity=5, window_seconds=10),
        TokenBucketLimiter(store, capacity=5, refill_rate=1),
    ]


@pytest.mark.asyncio
async def test_peek_reports_full_quota_when_untouched(store):
    for limiter in all_limiters(store):
        assert await limiter.peek(f"fresh-{limiter.name}") == 5


@pytest.mark.asyncio
async def test_peek_does_not_consume_quota(store):
    for limiter in all_limiters(store):
        key = f"nonconsuming-{limiter.name}"
        for _ in range(20):
            await limiter.peek(key)
        # All 5 units must still be available after heavy peeking.
        allowed = [(await limiter.check(key)).allowed for _ in range(5)]
        assert all(allowed), f"{limiter.name} lost quota to peek()"


@pytest.mark.asyncio
async def test_peek_tracks_consumption(store):
    for limiter in all_limiters(store):
        key = f"tracking-{limiter.name}"
        await limiter.check(key)
        await limiter.check(key)
        assert await limiter.peek(key) == 3, limiter.name


@pytest.mark.asyncio
async def test_peek_sees_token_bucket_refill(store):
    limiter = TokenBucketLimiter(store, capacity=5, refill_rate=20)
    for _ in range(5):
        await limiter.check("refill")
    assert await limiter.peek("refill") == 0

    await asyncio.sleep(0.15)  # ~3 tokens back at 20/s
    refilled = await limiter.peek("refill")
    assert 1 <= refilled <= 5
