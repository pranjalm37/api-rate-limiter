"""Tests for the Redis-down-falls-back-to-memory behavior in
LimiterManager.check()/peek(). Uses a dead port rather than mocking, since
the actual failure mode we care about is a real connection error."""

import pytest

from app.config import get_settings
from app.limiter_manager import LimiterManager
from app.limiters import Algorithm

DEAD_REDIS_URL = "redis://localhost:6399/0"


@pytest.fixture
def manager_with_dead_redis():
    manager = LimiterManager()
    original_url = get_settings().redis_url
    get_settings().redis_url = DEAD_REDIS_URL
    yield manager
    get_settings().redis_url = original_url


@pytest.mark.asyncio
async def test_gcra_check_falls_back_to_memory_when_redis_down(manager_with_dead_redis):
    manager = manager_with_dead_redis
    manager.config.algorithm = Algorithm.GCRA
    manager.config.backend = "redis"
    manager.config.capacity = 3
    manager.config.refill_rate = 1.0
    manager._rebuild()

    results = [await manager.check("gcra-fallback-test") for _ in range(4)]
    assert [r.allowed for r in results] == [True, True, True, False]
    assert manager._redis_healthy is False


@pytest.mark.asyncio
async def test_gcra_peek_falls_back_to_memory_when_redis_down(manager_with_dead_redis):
    manager = manager_with_dead_redis
    manager.config.algorithm = Algorithm.GCRA
    manager.config.backend = "redis"
    manager.config.capacity = 3
    manager.config.refill_rate = 1.0
    manager._rebuild()

    remaining = await manager.peek("gcra-peek-fallback-test")
    assert remaining == 3
    assert manager._redis_healthy is False
