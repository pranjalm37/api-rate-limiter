import asyncio
import time
from collections import defaultdict

from app.storage.base import Store


class MemoryStore(Store):
    """In-process backend. Fast, zero setup, but not shared across workers/instances."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._counters: dict[str, tuple[int, float]] = {}  # key -> (count, expires_at)
        self._sorted_sets: dict[str, dict[str, float]] = defaultdict(dict)  # key -> {member: score}
        self._buckets: dict[str, tuple[float, float, float]] = {}  # key -> (tokens, last_ts, expires_at)

    async def incr_and_get(self, key: str, ttl: float) -> int:
        async with self._lock:
            now = time.time()
            count, expires_at = self._counters.get(key, (0, 0.0))
            if now >= expires_at:
                count = 0
                expires_at = now + ttl
            count += 1
            self._counters[key] = (count, expires_at)
            return count

    async def get_counter(self, key: str) -> int:
        async with self._lock:
            count, expires_at = self._counters.get(key, (0, 0.0))
            if time.time() >= expires_at:
                return 0
            return count

    async def zadd(self, key: str, score: float, member: str) -> None:
        async with self._lock:
            self._sorted_sets[key][member] = score

    async def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> None:
        async with self._lock:
            members = self._sorted_sets.get(key)
            if not members:
                return
            to_drop = [m for m, s in members.items() if min_score <= s <= max_score]
            for m in to_drop:
                del members[m]

    async def zcard(self, key: str) -> int:
        async with self._lock:
            return len(self._sorted_sets.get(key, {}))

    async def expire(self, key: str, ttl: float) -> None:
        # Sorted sets are periodically trimmed by zremrangebyscore; no separate TTL needed in memory.
        return None

    async def consume_token(
        self, key: str, capacity: float, refill_rate: float, ttl: float
    ) -> tuple[bool, float]:
        async with self._lock:
            now = time.time()
            entry = self._buckets.get(key)
            if entry is None or now >= entry[2]:
                tokens, last_ts = capacity, now
            else:
                tokens, last_ts, _ = entry
                elapsed = max(now - last_ts, 0.0)
                tokens = min(capacity, tokens + elapsed * refill_rate)
                last_ts = now

            if tokens >= 1.0:
                tokens -= 1.0
                allowed = True
            else:
                allowed = False

            self._buckets[key] = (tokens, last_ts, now + ttl)
            return allowed, tokens

    async def reset(self, key_prefix: str = "") -> None:
        async with self._lock:
            self._counters = {k: v for k, v in self._counters.items() if not k.startswith(key_prefix)}
            self._sorted_sets = defaultdict(
                dict, {k: v for k, v in self._sorted_sets.items() if not k.startswith(key_prefix)}
            )
            self._buckets = {k: v for k, v in self._buckets.items() if not k.startswith(key_prefix)}
