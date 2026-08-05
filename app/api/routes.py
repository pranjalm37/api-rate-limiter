from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from app.api.schemas import (
    CheckRequest,
    CheckResponse,
    ConfigResponse,
    ConfigureRequest,
    PeekResponse,
)
from app.limiter_manager import LimiterManager, get_manager

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/config", response_model=ConfigResponse)
async def get_config(manager: LimiterManager = Depends(get_manager)) -> ConfigResponse:
    return ConfigResponse.model_validate(manager.config)


@router.post("/config", response_model=ConfigResponse)
async def set_config(
    body: ConfigureRequest, manager: LimiterManager = Depends(get_manager)
) -> ConfigResponse:
    await manager.reconfigure(
        algorithm=body.algorithm,
        backend=body.backend,
        capacity=body.capacity,
        window_seconds=body.window_seconds,
        refill_rate=body.refill_rate,
    )
    return ConfigResponse.model_validate(manager.config)


@router.post("/limiter/reset")
async def reset_limiter(manager: LimiterManager = Depends(get_manager)) -> dict:
    await manager.reset()
    return {"status": "reset"}


@router.post("/limiter/check", response_model=CheckResponse)
async def check_limiter(
    body: CheckRequest, manager: LimiterManager = Depends(get_manager)
) -> CheckResponse:
    """Used by the GUI's live traffic simulator: fires one real request
    through the currently configured limiter and reports the outcome."""
    result = await manager.check(body.client_id)
    return CheckResponse(
        allowed=result.allowed,
        limit=result.limit,
        remaining=result.remaining,
        retry_after=result.retry_after,
        algorithm=manager.config.algorithm,
    )


@router.get("/limiter/peek", response_model=PeekResponse)
async def peek_limiter(
    client_id: str = "demo-client", manager: LimiterManager = Depends(get_manager)
) -> PeekResponse:
    """Report remaining quota without consuming any. The dashboard polls this
    to chart how quota recovers, which must not itself count as traffic."""
    return PeekResponse(
        remaining=await manager.peek(client_id),
        limit=manager.config.capacity,
        algorithm=manager.config.algorithm,
    )


@router.get("/demo/resource")
async def demo_resource(
    request: Request,
    response: Response,
    x_client_id: str | None = Header(default=None),
    manager: LimiterManager = Depends(get_manager),
) -> dict:
    """A real protected endpoint. Rate limited by X-Client-Id header (falls
    back to the caller's IP), exactly how you'd gate a production API."""
    client_id = x_client_id or (request.client.host if request.client else "unknown")
    result = await manager.check(client_id)

    response.headers["X-RateLimit-Limit"] = str(result.limit)
    response.headers["X-RateLimit-Remaining"] = str(result.remaining)
    if not result.allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "Retry-After": str(round(result.retry_after, 2)),
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": str(result.remaining),
            },
        )

    return {"message": "here is your data", "client_id": client_id, "remaining": result.remaining}
