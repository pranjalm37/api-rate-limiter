from abc import ABC, abstractmethod


class Store(ABC):
    """Storage backend used by rate-limiting algorithms.

    Two implementations exist (memory, redis) behind this same interface so
    an algorithm's logic never changes when the backend is swapped.
    """

    @abstractmethod
    async def incr_and_get(self, key: str, ttl: float) -> int:
        """Atomically increment a counter, creating it with the given TTL if new."""

    @abstractmethod
    async def get_counter(self, key: str) -> int:
        """Read a counter's current value without incrementing it (0 if absent/expired)."""

    @abstractmethod
    async def zadd(self, key: str, score: float, member: str) -> None:
        """Add a timestamped member to a sorted set (used as a request log)."""

    @abstractmethod
    async def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> None:
        """Drop sorted-set members whose score falls in [min_score, max_score]."""

    @abstractmethod
    async def zcard(self, key: str) -> int:
        """Count members currently in the sorted set."""

    @abstractmethod
    async def expire(self, key: str, ttl: float) -> None:
        """Set/refresh a key's TTL."""

    @abstractmethod
    async def consume_token(
        self, key: str, capacity: float, refill_rate: float, ttl: float
    ) -> tuple[bool, float]:
        """Atomically refill-then-consume one token from a bucket.

        Returns (allowed, tokens_remaining_after_this_call). Refill and
        consume must happen as a single atomic step per backend, otherwise
        two concurrent requests could both read the same token count and
        both be allowed through.
        """

    @abstractmethod
    async def peek_tokens(self, key: str, capacity: float, refill_rate: float) -> float:
        """Return a bucket's token count including refill owed, without writing.

        Read-only counterpart to consume_token: the refill is a pure function
        of elapsed time, so observability can sample it without side effects.
        """

    @abstractmethod
    async def reset(self, key_prefix: str = "") -> None:
        """Clear all state (used by tests / the GUI's reset button)."""

    @abstractmethod
    async def oldest_score(self, key: str) -> float | None:
        """The lowest score currently in the sorted set at `key` (None if empty).

        Used by sliding_window_log to report reset_after: a sliding window
        has no single boundary, so "reset" means when the oldest logged
        request ages out of the window and frees a slot.
        """

    @abstractmethod
    async def ttl(self, key: str) -> float:
        """Seconds remaining before `key`'s state expires (0 if absent/expired).

        Used by fixed_window to report reset_after: how long until this
        window's counter clears, without the limiter needing to track
        window-start timestamps itself.
        """
