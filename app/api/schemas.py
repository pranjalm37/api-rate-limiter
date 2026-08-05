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
