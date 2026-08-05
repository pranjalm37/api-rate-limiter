from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: float  # seconds until the caller should retry, 0 if allowed


class RateLimiter(ABC):
    """Common interface every algorithm implements, so the API layer and the
    GUI simulator can swap algorithms without caring how each one works."""

    name: str

    @abstractmethod
    async def check(self, key: str) -> RateLimitResult:
        """Consume one unit of quota for `key` and report the outcome."""
