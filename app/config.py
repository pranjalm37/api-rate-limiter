from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.route_limits import RouteLimitOverride


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RATE_LIMITER_")

    redis_url: str = "redis://localhost:6379/0"
    backend: str = "memory"  # "memory" or "redis"
    default_capacity: int = 10
    default_window_seconds: float = 10.0
    default_refill_rate: float = 1.0  # tokens per second, token bucket only
    # Per-route overrides, keyed by request path (e.g. "/api/demo/resource").
    # Empty by default -- not enforced anywhere yet, just available to set.
    route_limits: dict[str, RouteLimitOverride] = Field(default_factory=dict)


@lru_cache
def get_settings() -> Settings:
    return Settings()
