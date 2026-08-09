from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: float  # seconds until the caller should retry, 0 if allowed
    # Seconds until quota is back to full ("the window/bucket resets").
    # Defaults to 0.0 -- each limiter fills this in with real per-algorithm
    # logic in a follow-up change; until then it's just present on the type.
    reset_after: float = 0.0


class RateLimiter(ABC):
    """Common interface every algorithm implements, so the API layer and the
    GUI simulator can swap algorithms without caring how each one works."""

    name: str

    @abstractmethod
    async def check(self, key: str) -> RateLimitResult:
        """Consume one unit of quota for `key` and report the outcome."""

    @abstractmethod
    async def peek(self, key: str) -> int:
        """Report remaining quota for `key` without consuming any.

        Used for observability -- the dashboard samples this to plot how
        quota recovers over time, which must not itself count as traffic.
        """
