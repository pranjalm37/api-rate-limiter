import time

import redis.asyncio as redis

from app.storage.base import Store

# INCR then set TTL only the moment the key is created (count == 1),
# so a window's expiry is anchored to its first request, atomically.
_INCR_WITH_TTL = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('PEXPIRE', KEYS[1], ARGV[1])
end
return count
"""

# Refill-then-consume a token bucket atomically: read current state, compute
# the refill owed since last_ts, spend a token if available, write back.
# ARGV: capacity, refill_rate, ttl_ms, now
_CONSUME_TOKEN = """
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local ttl_ms = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

local vals = redis.call('HMGET', KEYS[1], 'tokens', 'last_ts')
local tokens
local last_ts
if vals[1] == false then
    tokens = capacity
    last_ts = now
else
    tokens = tonumber(vals[1])
    last_ts = tonumber(vals[2])
    local elapsed = math.max(now - last_ts, 0)
    tokens = math.min(capacity, tokens + elapsed * refill_rate)
    last_ts = now
end

local allowed
if tokens >= 1.0 then
    tokens = tokens - 1.0
    allowed = 1
else
    allowed = 0
end

redis.call('HSET', KEYS[1], 'tokens', tokens, 'last_ts', last_ts)
redis.call('PEXPIRE', KEYS[1], ttl_ms)
return {allowed, tostring(tokens)}
"""


class RedisStore(Store):
    """Redis-backed store — shared state across multiple app instances/processes."""

    def __init__(self, url: str) -> None:
        self._client = redis.from_url(url, decode_responses=True)
        self._incr_script = self._client.register_script(_INCR_WITH_TTL)
        self._consume_token_script = self._client.register_script(_CONSUME_TOKEN)

    async def incr_and_get(self, key: str, ttl: float) -> int:
        ttl_ms = max(int(ttl * 1000), 1)
        result = await self._incr_script(keys=[key], args=[ttl_ms])
        return int(result)

    async def get_counter(self, key: str) -> int:
        value = await self._client.get(key)
        return int(value) if value is not None else 0

    async def zadd(self, key: str, score: float, member: str) -> None:
        await self._client.zadd(key, {member: score})

    async def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> None:
        await self._client.zremrangebyscore(key, min_score, max_score)

    async def zcard(self, key: str) -> int:
        return int(await self._client.zcard(key))

    async def expire(self, key: str, ttl: float) -> None:
        await self._client.expire(key, max(int(ttl), 1))

    async def consume_token(
        self, key: str, capacity: float, refill_rate: float, ttl: float
    ) -> tuple[bool, float]:
        ttl_ms = max(int(ttl * 1000), 1)
        allowed, tokens = await self._consume_token_script(
            keys=[key], args=[capacity, refill_rate, ttl_ms, time.time()]
        )
        return bool(int(allowed)), float(tokens)

    async def peek_tokens(self, key: str, capacity: float, refill_rate: float) -> float:
        tokens, last_ts = await self._client.hmget(key, "tokens", "last_ts")
        if tokens is None:
            return capacity
        elapsed = max(time.time() - float(last_ts), 0.0)
        return min(capacity, float(tokens) + elapsed * refill_rate)

    async def reset(self, key_prefix: str = "") -> None:
        pattern = f"{key_prefix}*" if key_prefix else "*"
        cursor = 0
        while True:
            cursor, keys = await self._client.scan(cursor=cursor, match=pattern, count=200)
            if keys:
                await self._client.delete(*keys)
            if cursor == 0:
                break

    async def close(self) -> None:
        await self._client.aclose()
