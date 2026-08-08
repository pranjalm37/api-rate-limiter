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
    # period is deliberately large so no legitimate time-based refill can
    # happen within the test's runtime -- any count above burst would have
    # to come from a race, not real elapsed time.
    results = await asyncio.gather(
        *[gcra_store.check_and_update("user-1", period=10.0, burst=5, ttl=60) for _ in range(50)]
    )
    allowed_count = sum(1 for allowed, _ in results if allowed)
    assert allowed_count == 5


@pytest.mark.asyncio
async def test_peek_reports_full_burst_when_untouched(gcra_store):
    remaining = await gcra_store.peek("user-1", period=1.0, burst=5)
    assert remaining == 5


@pytest.mark.asyncio
async def test_peek_does_not_consume(gcra_store):
    for _ in range(20):
        await gcra_store.peek("user-1", period=1.0, burst=5)
    # Heavy peeking must not have spent anything -- all 5 should still admit.
    results = [
        await gcra_store.check_and_update("user-1", period=1.0, burst=5, ttl=60) for _ in range(5)
    ]
    assert all(allowed for allowed, _ in results)


@pytest.mark.asyncio
async def test_peek_tracks_consumption(gcra_store):
    await gcra_store.check_and_update("user-1", period=1.0, burst=5, ttl=60)
    await gcra_store.check_and_update("user-1", period=1.0, burst=5, ttl=60)
    remaining = await gcra_store.peek("user-1", period=1.0, burst=5)
    # int(), not ==: real wall-clock time passes between the two calls above
    # and this peek, so a sliver of legitimate refill can nudge the raw float
    # just past 3 (e.g. 3.00003) -- GCRALimiter truncates the same way.
    assert int(remaining) == 3


@pytest.mark.asyncio
async def test_peek_reflects_refill_over_time(gcra_store):
    period = 0.05  # fast refill: one slot back every 50ms
    for _ in range(5):
        await gcra_store.check_and_update("user-1", period=period, burst=5, ttl=60)
    assert int(await gcra_store.peek("user-1", period=period, burst=5)) == 0

    await asyncio.sleep(0.12)  # ~2 slots' worth of time
    remaining = await gcra_store.peek("user-1", period=period, burst=5)
    assert 1 <= remaining <= 5


@pytest.mark.asyncio
async def test_peek_resets_to_full_after_ttl_expiry(gcra_store):
    await gcra_store.check_and_update("user-1", period=1.0, burst=5, ttl=0.05)
    await asyncio.sleep(0.1)  # let the key's ttl lapse
    remaining = await gcra_store.peek("user-1", period=1.0, burst=5)
    assert remaining == 5
