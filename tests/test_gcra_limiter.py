import asyncio

import pytest

from app.limiters.gcra import GCRALimiter
from app.storage.gcra_memory import MemoryGCRAStore


@pytest.fixture
def gcra_store() -> MemoryGCRAStore:
    return MemoryGCRAStore()


@pytest.mark.asyncio
async def test_allows_burst_up_to_capacity(gcra_store):
    limiter = GCRALimiter(gcra_store, capacity=5, refill_rate=1)
    results = [await limiter.check("user-1") for _ in range(5)]
    assert all(r.allowed for r in results)
    assert not (await limiter.check("user-1")).allowed


@pytest.mark.asyncio
async def test_refills_over_time(gcra_store):
    limiter = GCRALimiter(gcra_store, capacity=1, refill_rate=10)  # refills fast: 0.1s/request
    assert (await limiter.check("user-1")).allowed
    assert not (await limiter.check("user-1")).allowed

    await asyncio.sleep(0.15)
    assert (await limiter.check("user-1")).allowed


@pytest.mark.asyncio
async def test_result_fields_match_rate_limiter_contract(gcra_store):
    limiter = GCRALimiter(gcra_store, capacity=3, refill_rate=5)
    result = await limiter.check("user-1")
    assert result.allowed is True
    assert result.limit == 3
    assert result.remaining == 2
    assert result.retry_after == 0.0

    # drain the rest of the burst
    await limiter.check("user-1")
    await limiter.check("user-1")
    blocked = await limiter.check("user-1")
    assert blocked.allowed is False
    assert blocked.limit == 3
    assert blocked.retry_after > 0


@pytest.mark.asyncio
async def test_peek_does_not_consume_quota(gcra_store):
    limiter = GCRALimiter(gcra_store, capacity=5, refill_rate=1)
    for _ in range(20):
        await limiter.peek("user-1")
    allowed = [(await limiter.check("user-1")).allowed for _ in range(5)]
    assert all(allowed)


@pytest.mark.asyncio
async def test_peek_tracks_consumption(gcra_store):
    limiter = GCRALimiter(gcra_store, capacity=5, refill_rate=1)
    await limiter.check("user-1")
    await limiter.check("user-1")
    assert await limiter.peek("user-1") == 3


@pytest.mark.asyncio
async def test_concurrent_requests_never_exceed_capacity(gcra_store):
    limiter = GCRALimiter(gcra_store, capacity=5, refill_rate=0.1)  # slow refill
    results = await asyncio.gather(*[limiter.check("user-1") for _ in range(50)])
    allowed_count = sum(r.allowed for r in results)
    assert allowed_count == 5


@pytest.mark.asyncio
async def test_reset_after_positive_even_when_allowed(gcra_store):
    """retry_after is 0 once a request is allowed, but reset_after (time
    until the burst is back to FULL capacity) should still be positive --
    same distinction as token_bucket, since GCRA has the same shape."""
    limiter = GCRALimiter(gcra_store, capacity=5, refill_rate=1)
    result = await limiter.check("user-1")
    assert result.allowed
    assert result.retry_after == 0.0
    assert result.reset_after > 0.0


@pytest.mark.asyncio
async def test_reset_after_exceeds_retry_after_when_blocked(gcra_store):
    limiter = GCRALimiter(gcra_store, capacity=5, refill_rate=1)
    for _ in range(5):
        await limiter.check("user-1")
    blocked = await limiter.check("user-1")
    assert not blocked.allowed
    assert blocked.reset_after > blocked.retry_after > 0.0


@pytest.mark.asyncio
async def test_reset_after_decreases_as_burst_refills(gcra_store):
    limiter = GCRALimiter(gcra_store, capacity=3, refill_rate=10)  # capacity/rate = 0.3s to full
    for _ in range(3):
        await limiter.check("user-1")
    empty = await limiter.check("user-1")
    assert not empty.allowed

    # Same reasoning as token_bucket's equivalent test: sleeping past
    # capacity/refill_rate guarantees the burst is fully available again
    # before this check consumes one slot from it.
    await asyncio.sleep(0.31)
    refilled = await limiter.check("user-1")
    assert refilled.reset_after < empty.reset_after
