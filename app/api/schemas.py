from pydantic import BaseModel, ConfigDict, Field

from app.limiters import Algorithm


class ConfigureRequest(BaseModel):
    algorithm: Algorithm
    backend: str = Field(default="memory", pattern="^(memory|redis)$")
    capacity: int = Field(gt=0, le=10_000)
    window_seconds: float = Field(gt=0, le=3600)
    refill_rate: float = Field(gt=0, le=1000)


class ConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    algorithm: Algorithm
    backend: str
    capacity: int
    window_seconds: float
    refill_rate: float


class CheckRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=128, default="demo-client")


class CheckResponse(BaseModel):
    allowed: bool
    limit: int
    remaining: int
    retry_after: float
    algorithm: Algorithm


class PeekResponse(BaseModel):
    remaining: int
    limit: int
    algorithm: Algorithm


class RouteLimitRequest(BaseModel):
    """All override fields are optional -- a route can override just one
    knob and inherit the rest from the global config. Storage only for now;
    nothing enforces these yet."""

    path: str = Field(min_length=1, max_length=256)
    algorithm: Algorithm | None = None
    capacity: int | None = Field(default=None, gt=0, le=10_000)
    window_seconds: float | None = Field(default=None, gt=0, le=3600)
    refill_rate: float | None = Field(default=None, gt=0, le=1000)


class RouteLimitResponse(BaseModel):
    path: str
    algorithm: Algorithm | None
    capacity: int | None
    window_seconds: float | None
    refill_rate: float | None


class RouteLimitClearRequest(BaseModel):
    path: str = Field(min_length=1, max_length=256)
