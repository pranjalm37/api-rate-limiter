from app.limiters.base import RateLimitResult, RateLimiter
from app.storage.gcra_store import GCRAStore


class GCRALimiter(RateLimiter):
    """GCRA ("leaky bucket") -- generic cell rate algorithm.

    Equivalent in effect to the token bucket (same burst-then-steady-rate
    shape, used by Stripe's API among others), but implemented without an
    explicit token count: state is a single "theoretical arrival time"
    timestamp per key instead of a token count that needs refilling.
    `capacity` sets the burst size and `refill_rate` (requests/second) sets
    the steady-state rate -- the same two knobs the token bucket uses.
    """

    name = "gcra"

    def __init__(self, store: GCRAStore, capacity: int, refill_rate: float) -> None:
        self.store = store
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.period = 1.0 / refill_rate if refill_rate > 0 else float("inf")

    async def check(self, key: str) -> RateLimitResult:
        storage_key = f"gcra:{key}"
        # State should outlive an idle period long enough for a full burst
        # to become available again, same reasoning as the token bucket's ttl.
        ttl = max(self.period * self.capacity, 1.0) * 2 if self.refill_rate > 0 else 60.0

        allowed, retry_after = await self.store.check_and_update(
            storage_key, self.period, float(self.capacity), ttl
        )
        remaining = await self.store.peek(storage_key, self.period, float(self.capacity))

        # Same split as token_bucket: retry_after is "when can I send one
        # more request" (already computed above), reset_after is "when is
        # the burst back to full capacity" -- a distinct, larger value.
        deficit = self.capacity - remaining
        reset_after = deficit * self.period if self.refill_rate > 0 else float("inf")

        return RateLimitResult(
            allowed=allowed,
            limit=self.capacity,
            remaining=int(remaining),
            retry_after=retry_after,
            reset_after=reset_after,
        )

    async def peek(self, key: str) -> int:
        remaining = await self.store.peek(f"gcra:{key}", self.period, float(self.capacity))
        return int(remaining)
