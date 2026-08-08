import time

import redis.asyncio as redis

from app.storage.gcra_store import GCRAStore


class RedisGCRAStore(GCRAStore):
    """Redis-backed GCRA state, shared across app instances/processes.

    Deliberately plain for now: the read (HMGET) and write (HSET) are two
    separate round-trips, not one atomic operation. That's a real race --
    two concurrent requests for the same key can both read the same TAT
    before either writes back, letting more requests through than the
    burst allows. A follow-up change replaces this with a Lua script (see
    RedisStore's _CONSUME_TOKEN for the pattern this will mirror).
    """

    def __init__(self, url: str) -> None:
        self._client = redis.from_url(url, decode_responses=True)

    async def check_and_update(
        self, key: str, period: float, burst: float, ttl: float
    ) -> tuple[bool, float]:
        now = time.time()

        tat_raw, expires_raw = await self._client.hmget(key, "tat", "expires_at")
        if tat_raw is None or (expires_raw is not None and now >= float(expires_raw)):
            tat = now
        else:
            tat = float(tat_raw)

        allow_at = max(tat, now)
        burst_tolerance = period * max(burst - 1, 0)

        if allow_at - now <= burst_tolerance:
            new_tat = allow_at + period
            await self._client.hset(key, mapping={"tat": new_tat, "expires_at": now + ttl})
            await self._client.expire(key, max(int(ttl), 1))
            return True, 0.0

        retry_after = allow_at - now - burst_tolerance
        return False, retry_after

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
