import asyncio

import pytest

from app.storage.gcra_memory import MemoryGCRAStore


@pytest.fixture
def gcra_store() -> MemoryGCRAStore:
    return MemoryGCRAStore()


@pytest.mark.asyncio
async def test_allows_burst_up_to_configured_size(gcra_store):
    # burst=5, period=1s -> 5 requests can land back-to-back with no wait
    results = [
        await gcra_store.check_and_update("user-1", period=1.0, burst=5, ttl=60) for _ in range(5)
    ]
    assert all(allowed for allowed, _ in results)

    allowed, retry_after = await gcra_store.check_and_update("user-1", period=1.0, burst=5, ttl=60)
    assert not allowed
    assert retry_after > 0


@pytest.mark.asyncio
async def test_admits_again_after_waiting_period(gcra_store):
    await gcra_store.check_and_update("user-1", period=0.1, burst=1, ttl=60)
    allowed, _ = await gcra_store.check_and_update("user-1", period=0.1, burst=1, ttl=60)
    assert not allowed

    await asyncio.sleep(0.15)
    allowed, _ = await gcra_store.check_and_update("user-1", period=0.1, burst=1, ttl=60)
    assert allowed


@pytest.mark.asyncio
async def test_rejection_does_not_advance_state(gcra_store):
    """A rejected request must not push the TAT further out, otherwise a
    burst of rejected requests would keep extending the required wait."""
    await gcra_store.check_and_update("user-1", period=1.0, burst=1, ttl=60)
    _, retry_after_1 = await gcra_store.check_and_update("user-1", period=1.0, burst=1, ttl=60)
    await asyncio.sleep(0.05)
    _, retry_after_2 = await gcra_store.check_and_update("user-1", period=1.0, burst=1, ttl=60)
    assert retry_after_2 < retry_after_1


@pytest.mark.asyncio
async def test_independent_keys_do_not_share_state(gcra_store):
    for _ in range(3):
        allowed, _ = await gcra_store.check_and_update("user-1", period=1.0, burst=3, ttl=60)
        assert allowed
    # user-2 must still have a fresh bucket, unaffected by user-1's usage
    allowed, _ = await gcra_store.check_and_update("user-2", period=1.0, burst=3, ttl=60)
    assert allowed


@pytest.mark.asyncio
async def test_concurrent_requests_never_exceed_burst(gcra_store):
    results = await asyncio.gather(
        *[gcra_store.check_and_update("user-1", period=0.001, burst=5, ttl=60) for _ in range(50)]
    )
    allowed_count = sum(1 for allowed, _ in results if allowed)
    assert allowed_count == 5
