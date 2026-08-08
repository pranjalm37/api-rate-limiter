import asyncio
import time

from app.storage.gcra_store import GCRAStore


class MemoryGCRAStore(GCRAStore):
    """In-process GCRA state: one theoretical-arrival-time (TAT) per key."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._tat: dict[str, tuple[float, float]] = {}  # key -> (tat, expires_at)

    async def check_and_update(
        self, key: str, period: float, burst: float, ttl: float
    ) -> tuple[bool, float]:
        async with self._lock:
            now = time.time()
            tat, expires_at = self._tat.get(key, (0.0, 0.0))
            if now >= expires_at:
                tat = now

            allow_at = max(tat, now)
            burst_tolerance = period * max(burst - 1, 0)

            if allow_at - now <= burst_tolerance:
                self._tat[key] = (allow_at + period, now + ttl)
                return True, 0.0

            retry_after = allow_at - now - burst_tolerance
            self._tat[key] = (tat, now + ttl)
            return False, retry_after

    async def reset(self, key_prefix: str = "") -> None:
        async with self._lock:
            self._tat = {k: v for k, v in self._tat.items() if not k.startswith(key_prefix)}
