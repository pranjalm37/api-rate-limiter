from abc import ABC, abstractmethod


class GCRAStore(ABC):
    """Storage backend for the GCRA (leaky bucket) algorithm.

    Kept separate from the main `Store` interface: GCRA's state is a single
    "theoretical arrival time" (TAT) per key, not a counter or sorted set,
    so it doesn't fit the existing primitives cleanly. A Redis-backed
    implementation lands in a follow-up change.
    """

    @abstractmethod
    async def check_and_update(
        self, key: str, period: float, burst: float, ttl: float
    ) -> tuple[bool, float]:
        """Attempt to admit one request under GCRA.

        `period` is the minimum spacing between requests at the target
        rate (1 / requests-per-second). `burst` is how many requests may
        be admitted back-to-back before the steady rate kicks in.

        Returns (allowed, retry_after_seconds). On success the stored TAT
        advances by `period`; on rejection it is left untouched so a
        burst of rejected requests doesn't keep pushing the wait out.
        """

    @abstractmethod
    async def peek(self, key: str, period: float, burst: float) -> float:
        """Report the token-bucket-equivalent quota remaining, without consuming any.

        GCRA has no explicit token count, but `burst - (deficit / period)`
        (deficit = how far the stored TAT sits ahead of now) is the same
        quantity a token bucket would report, so callers can treat GCRA
        and token-bucket remaining-quota the same way.
        """
