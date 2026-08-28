"""Redis-backed concurrency test for sliding_window_log -- this is the
backend the original race actually lived in (confirmed empirically: 50
concurrent requests at capacity=5 let 16 through before the fix). The
memory-backed version of this test lives in test_sliding_window_log.py."""

import asyncio
import uuid

import pytest
import redis.asyncio as redis

from app.limiters.sliding_window_log import SlidingWindowLogLimiter
from app.storage.redis_store import RedisStore

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
async def store():
    s = RedisStore(REDIS_URL)
    yield s
    await s.reset(key_prefix="test-swl:")
    await s.close()


@pytest.mark.asyncio
async def test_concurrent_requests_never_exceed_capacity_against_real_redis(store):
    key = f"test-swl:{uuid.uuid4()}"
    limiter = SlidingWindowLogLimiter(store, capacity=5, window_seconds=10)
    results = await asyncio.gather(*[limiter.check(key) for _ in range(50)])
    allowed_count = sum(r.allowed for r in results)
    assert allowed_count == 5


@pytest.mark.asyncio
async def test_sequential_behavior_unaffected_by_the_fix(store):
    """The atomic swap shouldn't change ordinary sequential behavior --
    just close the concurrency hole."""
    key = f"test-swl:{uuid.uuid4()}"
    limiter = SlidingWindowLogLimiter(store, capacity=3, window_seconds=10)
    results = [await limiter.check(key) for _ in range(4)]
    assert [r.allowed for r in results] == [True, True, True, False]


@pytest.mark.asyncio
async def test_window_still_slides_correctly(store):
    key = f"test-swl:{uuid.uuid4()}"
    limiter = SlidingWindowLogLimiter(store, capacity=1, window_seconds=0.2)
    assert (await limiter.check(key)).allowed
    assert not (await limiter.check(key)).allowed

    await asyncio.sleep(0.25)
    assert (await limiter.check(key)).allowed
