from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RATE_LIMITER_")

    redis_url: str = "redis://localhost:6379/0"
    backend: str = "memory"  # "memory" or "redis"
    default_capacity: int = 10
    default_window_seconds: float = 10.0
    default_refill_rate: float = 1.0  # tokens per second, token bucket only


@lru_cache
def get_settings() -> Settings:
    return Settings()
