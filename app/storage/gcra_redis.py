import time

import redis.asyncio as redis

from app.storage.gcra_store import GCRAStore

# Atomic GCRA check-and-update: read the stored TAT, decide admit/reject,
# and write the new TAT back -- all inside one Lua script, so no other
# client can interleave a read between this read and this write. That's
# the fix for the race the plain (HMGET-then-HSET) version had: two
# concurrent requests could both read the same TAT before either wrote
# back, letting more requests through than `burst` allows.
# ARGV: period, burst, ttl_seconds, now
_GCRA_CHECK_AND_UPDATE = """
local period = tonumber(ARGV[1])
local burst = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

local vals = redis.call('HMGET', KEYS[1], 'tat', 'expires_at')
local tat
if vals[1] == false then
    tat = now
else
    local expires_at = tonumber(vals[2])
    if expires_at ~= nil and now >= expires_at then
        tat = now
    else
        tat = tonumber(vals[1])
    end
end

local allow_at = math.max(tat, now)
local burst_tolerance = period * math.max(burst - 1, 0)

if allow_at - now <= burst_tolerance then
    local new_tat = allow_at + period
    redis.call('HSET', KEYS[1], 'tat', new_tat, 'expires_at', now + ttl)
    redis.call('PEXPIRE', KEYS[1], math.max(math.floor(ttl * 1000), 1))
    return {1, '0'}
end

local retry_after = allow_at - now - burst_tolerance
return {0, tostring(retry_after)}
"""


class RedisGCRAStore(GCRAStore):
    """Redis-backed GCRA state, shared across app instances/processes.

    The check-and-update is a single Lua script (see `_GCRA_CHECK_AND_UPDATE`),
    so it's atomic on Redis's side -- no concurrent-request race, matching
    the guarantee `MemoryGCRAStore` gets from its asyncio lock.
    """

    def __init__(self, url: str) -> None:
        self._client = redis.from_url(url, decode_responses=True)
        self._check_and_update_script = self._client.register_script(_GCRA_CHECK_AND_UPDATE)

    async def check_and_update(
        self, key: str, period: float, burst: float, ttl: float
    ) -> tuple[bool, float]:
        allowed, retry_after = await self._check_and_update_script(
            keys=[key], args=[period, burst, ttl, time.time()]
        )
        return bool(int(allowed)), float(retry_after)

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
