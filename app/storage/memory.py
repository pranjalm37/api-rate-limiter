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

    async def peek_tokens(self, key: str, capacity: float, refill_rate: float) -> float:
        async with self._lock:
            now = time.time()
            entry = self._buckets.get(key)
            if entry is None or now >= entry[2]:
                return capacity
            tokens, last_ts, _ = entry
            return min(capacity, tokens + max(now - last_ts, 0.0) * refill_rate)

    async def reset(self, key_prefix: str = "") -> None:
        async with self._lock:
            self._counters = {k: v for k, v in self._counters.items() if not k.startswith(key_prefix)}
            self._sorted_sets = defaultdict(
                dict, {k: v for k, v in self._sorted_sets.items() if not k.startswith(key_prefix)}
            )
            self._buckets = {k: v for k, v in self._buckets.items() if not k.startswith(key_prefix)}

    async def oldest_score(self, key: str) -> float | None:
        async with self._lock:
            members = self._sorted_sets.get(key)
            if not members:
                return None
            return min(members.values())

    async def ttl(self, key: str) -> float:
        async with self._lock:
            _, expires_at = self._counters.get(key, (0, 0.0))
            return max(expires_at - time.time(), 0.0)

    async def zadd_if_under_capacity(
        self, key: str, window_start: float, capacity: int, score: float, member: str, ttl: float
    ) -> tuple[bool, int]:
        # Trim, count, and conditionally add all inside one lock acquisition
        # -- genuinely atomic, not just "each call individually locked" (the
        # old zremrangebyscore+zcard+zadd sequence releases and re-acquires
        # the lock between calls, which happens not to matter today only
        # because asyncio never yields control on an uncontended acquire;
        # that's an accident of the scheduler, not a real guarantee).
        async with self._lock:
            members = self._sorted_sets[key]
            to_drop = [m for m, s in members.items() if s <= window_start]
            for m in to_drop:
                del members[m]

            count = len(members)
            allowed = count < capacity
            if allowed:
                members[member] = score
                count += 1

            return allowed, count

    async def incr_weighted_if_under_capacity(
        self, current_key: str, previous_key: str, previous_weight: float, capacity: float, ttl: float
    ) -> tuple[bool, float]:
        # Same reasoning as zadd_if_under_capacity: read both counters,
        # decide, and conditionally increment all inside one lock
        # acquisition instead of three separately-locked calls.
        async with self._lock:
            now = time.time()

            prev_count, prev_expires_at = self._counters.get(previous_key, (0, 0.0))
            previous = 0 if now >= prev_expires_at else prev_count

            current, current_expires_at = self._counters.get(current_key, (0, 0.0))
            if now >= current_expires_at:
                current = 0
                current_expires_at = now + ttl

            weighted = previous * previous_weight + current
            allowed = weighted < capacity

            if allowed:
                current += 1
                weighted = previous * previous_weight + current

            self._counters[current_key] = (current, current_expires_at)
            return allowed, weighted
