from dataclasses import dataclass

from app.config import get_settings
from app.limiters import Algorithm, RateLimiter, RateLimitResult, build_limiter
from app.route_limits import RouteLimitOverride
from app.storage.base import Store
from app.storage.gcra_memory import MemoryGCRAStore
from app.storage.gcra_store import GCRAStore
from app.storage.memory import MemoryStore


@dataclass
class LimiterConfig:
    algorithm: Algorithm
    backend: str
    capacity: int
    window_seconds: float
    refill_rate: float


class LimiterManager:
    """Holds the single "live" rate limiter configuration used by both the
    demo endpoints and the GUI simulator, so changing settings in the GUI
    immediately changes how the real /api/demo/* endpoints behave too."""

    def __init__(self) -> None:
        settings = get_settings()
        self._memory_store = MemoryStore()
        self._redis_store: Store | None = None
        self._gcra_memory_store = MemoryGCRAStore()
        self._gcra_redis_store: GCRAStore | None = None
        self.config = LimiterConfig(
            algorithm=Algorithm.TOKEN_BUCKET,
            backend=settings.backend,
            capacity=settings.default_capacity,
            window_seconds=settings.default_window_seconds,
            refill_rate=settings.default_refill_rate,
        )
        # Live, settable per-route overrides -- seeded from Settings but
        # editable at runtime via the API, unlike Settings itself.
        self.route_limits: dict[str, RouteLimitOverride] = dict(settings.route_limits)
        # Lazily-built limiters for routes with a capacity override, keyed
        # by route path. Cleared whenever the global config or a specific
        # route's override changes, so a stale capacity never lingers.
        self._route_limiters: dict[str, RateLimiter] = {}
        self._limiter: RateLimiter | None = None
        self._rebuild()

    def set_route_limit(self, path: str, override: RouteLimitOverride) -> None:
        self.route_limits[path] = override
        self._route_limiters.pop(path, None)

    def clear_route_limit(self, path: str) -> None:
        self.route_limits.pop(path, None)
        self._route_limiters.pop(path, None)

    def _store_for(self, algorithm: Algorithm, backend: str) -> Store | GCRAStore:
        if algorithm == Algorithm.GCRA:
            if backend == "redis":
                if self._gcra_redis_store is None:
                    from app.storage.gcra_redis import RedisGCRAStore

                    self._gcra_redis_store = RedisGCRAStore(get_settings().redis_url)
                return self._gcra_redis_store
            return self._gcra_memory_store

        if backend == "redis":
            if self._redis_store is None:
                from app.storage.redis_store import RedisStore

                self._redis_store = RedisStore(get_settings().redis_url)
            return self._redis_store
        return self._memory_store

    def _rebuild(self) -> None:
        store = self._store_for(self.config.algorithm, self.config.backend)
        self._limiter = build_limiter(
            self.config.algorithm,
            store,
            self.config.capacity,
            self.config.window_seconds,
            self.config.refill_rate,
        )
        # Route limiters were built against the old global config -- drop
        # them so the next check()/peek() rebuilds against the new one.
        self._route_limiters.clear()

    def _limiter_for(self, route: str | None) -> tuple[RateLimiter, str]:
        """Picks the limiter to use, and a key prefix to keep its storage
        state isolated from the global keyspace and from other routes.

        capacity/window_seconds/refill_rate are all wired up -- a route can
        override any subset of them and inherit the rest from the global
        config. Routes always use the global algorithm; see route_limits.py
        for why per-route algorithm overrides were decided against."""
        assert self._limiter is not None
        if route is None:
            return self._limiter, ""

        override = self.route_limits.get(route)
        if override is None:
            return self._limiter, ""
        if override.capacity is None and override.window_seconds is None and override.refill_rate is None:
            return self._limiter, ""

        if route not in self._route_limiters:
            store = self._store_for(self.config.algorithm, self.config.backend)
            self._route_limiters[route] = build_limiter(
                self.config.algorithm,
                store,
                override.capacity if override.capacity is not None else self.config.capacity,
                override.window_seconds
                if override.window_seconds is not None
                else self.config.window_seconds,
                override.refill_rate if override.refill_rate is not None else self.config.refill_rate,
            )
        return self._route_limiters[route], f"route:{route}:"

    async def reconfigure(
        self,
        algorithm: Algorithm,
        backend: str,
        capacity: int,
        window_seconds: float,
        refill_rate: float,
    ) -> None:
        store = self._store_for(algorithm, backend)
        await store.reset()
        self.config = LimiterConfig(algorithm, backend, capacity, window_seconds, refill_rate)
        self._rebuild()

    async def reset(self) -> None:
        store = self._store_for(self.config.algorithm, self.config.backend)
        await store.reset()

    async def check(self, client_id: str, route: str | None = None) -> RateLimitResult:
        limiter, prefix = self._limiter_for(route)
        return await limiter.check(prefix + client_id)

    async def peek(self, client_id: str, route: str | None = None) -> int:
        limiter, prefix = self._limiter_for(route)
        return await limiter.peek(prefix + client_id)


_manager: LimiterManager | None = None


def get_manager() -> LimiterManager:
    global _manager
    if _manager is None:
        _manager = LimiterManager()
    return _manager
