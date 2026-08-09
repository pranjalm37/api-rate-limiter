from app.limiters.base import RateLimitResult, RateLimiter
from app.storage.base import Store


class TokenBucketLimiter(RateLimiter):
    """A bucket holds up to `capacity` tokens and refills at `refill_rate`
    tokens/second. Each request spends one token. Unlike the window
    algorithms, it allows short bursts up to the full capacity while still
    enforcing a steady average rate over time -- the industry-standard
    approach (used by AWS API Gateway, Stripe, etc.)."""

    name = "token_bucket"

    def __init__(self, store: Store, capacity: int, refill_rate: float) -> None:
        self.store = store
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second

    async def check(self, key: str) -> RateLimitResult:
        storage_key = f"tb:{key}"
        # Bucket state should outlive an idle period long enough to fully refill.
        ttl = max(self.capacity / self.refill_rate, 1.0) * 2 if self.refill_rate > 0 else 60.0

        allowed, tokens_remaining = await self.store.consume_token(
            storage_key, float(self.capacity), self.refill_rate, ttl
        )

        if allowed:
            retry_after = 0.0
        else:
            missing = 1.0 - tokens_remaining
            retry_after = missing / self.refill_rate if self.refill_rate > 0 else float("inf")

        # Distinct from retry_after: retry_after is "when can I send one more
        # request" (needs 1 token), reset_after is "when is the bucket back
        # to full capacity" (needs capacity - tokens_remaining tokens).
        deficit = self.capacity - tokens_remaining
        reset_after = deficit / self.refill_rate if self.refill_rate > 0 else float("inf")

        return RateLimitResult(
            allowed=allowed,
            limit=self.capacity,
            remaining=int(tokens_remaining),
            retry_after=retry_after,
            reset_after=reset_after,
        )

    async def peek(self, key: str) -> int:
        tokens = await self.store.peek_tokens(f"tb:{key}", float(self.capacity), self.refill_rate)
        return int(tokens)
