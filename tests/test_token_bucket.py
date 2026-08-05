import asyncio

import pytest

from app.limiters.token_bucket import TokenBucketLimiter


@pytest.mark.asyncio
async def test_allows_burst_up_to_capacity(store):
    limiter = TokenBucketLimiter(store, capacity=5, refill_rate=1)
    results = [await limiter.check("user-1") for _ in range(5)]
    assert all(r.allowed for r in results)
    assert not (await limiter.check("user-1")).allowed


@pytest.mark.asyncio
async def test_refills_over_time(store):
    limiter = TokenBucketLimiter(store, capacity=1, refill_rate=10)  # refills fast: 0.1s/token
    assert (await limiter.check("user-1")).allowed
    assert not (await limiter.check("user-1")).allowed

    await asyncio.sleep(0.15)
    assert (await limiter.check("user-1")).allowed


@pytest.mark.asyncio
async def test_never_exceeds_capacity_after_long_idle(store):
    limiter = TokenBucketLimiter(store, capacity=3, refill_rate=100)
    await limiter.check("user-1")  # establish bucket, spend 1 token
    await asyncio.sleep(0.5)  # plenty of time to overflow if refill weren't capped
    result = await limiter.check("user-1")
    assert result.allowed
    assert result.remaining <= 3


@pytest.mark.asyncio
async def test_concurrent_requests_never_oversell_tokens(store):
    """Fires more concurrent requests than the bucket has tokens for and
    asserts the total allowed count never exceeds capacity -- this is the
    race condition the atomic consume_token() storage method exists to prevent."""
    limiter = TokenBucketLimiter(store, capacity=5, refill_rate=0.001)
    results = await asyncio.gather(*[limiter.check("user-1") for _ in range(50)])
    allowed_count = sum(r.allowed for r in results)
    assert allowed_count == 5
