import asyncio
import uuid

import pytest
import redis.asyncio as redis

from app.storage.gcra_redis import RedisGCRAStore

REDIS_URL = "redis://localhost:6379/0"


async def _redis_available() -> bool:
    try:
        client = redis.from_url(REDIS_URL)
        await client.ping()
        await client.aclose()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not asyncio.run(_redis_available()), reason="redis not running on localhost:6379"
)


@pytest.fixture
async def gcra_store():
    store = RedisGCRAStore(REDIS_URL)
    yield store
    await store.reset(key_prefix="test-gcra:")
    await store.close()


def _key() -> str:
    return f"test-gcra:{uuid.uuid4()}"


@pytest.mark.asyncio
async def test_allows_burst_up_to_configured_size(gcra_store):
    key = _key()
    results = [await gcra_store.check_and_update(key, period=1.0, burst=5, ttl=60) for _ in range(5)]
    assert all(allowed for allowed, _ in results)

    allowed, retry_after = await gcra_store.check_and_update(key, period=1.0, burst=5, ttl=60)
    assert not allowed
    assert retry_after > 0


@pytest.mark.asyncio
async def test_admits_again_after_waiting_period(gcra_store):
    key = _key()
    await gcra_store.check_and_update(key, period=0.1, burst=1, ttl=60)
    allowed, _ = await gcra_store.check_and_update(key, period=0.1, burst=1, ttl=60)
    assert not allowed

    await asyncio.sleep(0.15)
    allowed, _ = await gcra_store.check_and_update(key, period=0.1, burst=1, ttl=60)
    assert allowed


@pytest.mark.asyncio
async def test_independent_keys_do_not_share_state(gcra_store):
    key_a, key_b = _key(), _key()
    for _ in range(3):
        allowed, _ = await gcra_store.check_and_update(key_a, period=1.0, burst=3, ttl=60)
        assert allowed
    allowed, _ = await gcra_store.check_and_update(key_b, period=1.0, burst=3, ttl=60)
    assert allowed


@pytest.mark.asyncio
async def test_concurrent_requests_never_exceed_burst(gcra_store):
    """The check-and-update Lua script makes the read-then-write atomic on
    Redis's side, so concurrent requests can no longer race each other into
    an oversold burst -- this used to fail before the Lua script existed.

    `period` is deliberately large (no legitimate time-based refill can
    happen within the test's runtime), so any count above `burst` could
    only come from a race, not real elapsed time.
    """
    key = _key()
    results = await asyncio.gather(
        *[gcra_store.check_and_update(key, period=10.0, burst=5, ttl=60) for _ in range(50)]
    )
    allowed_count = sum(1 for allowed, _ in results if allowed)
    assert allowed_count == 5


@pytest.mark.asyncio
async def test_rejection_does_not_advance_state(gcra_store):
    """A rejected request must not push the TAT further out, otherwise a
    burst of rejected requests would keep extending the required wait."""
    key = _key()
    await gcra_store.check_and_update(key, period=1.0, burst=1, ttl=60)
    _, retry_after_1 = await gcra_store.check_and_update(key, period=1.0, burst=1, ttl=60)
    await asyncio.sleep(0.05)
    _, retry_after_2 = await gcra_store.check_and_update(key, period=1.0, burst=1, ttl=60)
    assert retry_after_2 < retry_after_1
