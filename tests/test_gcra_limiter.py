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
