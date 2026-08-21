from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from app.api.apikey import extract_api_key
from app.api.schemas import (
    CheckRequest,
    CheckResponse,
    ConfigResponse,
    ConfigureRequest,
    PeekResponse,
    RouteLimitClearRequest,
    RouteLimitRequest,
    RouteLimitResponse,
)
from app.limiter_manager import LimiterManager, get_manager
from app.limiters import RateLimitResult
from app.route_limits import RouteLimitOverride

router = APIRouter()


def _apply_headers_and_raise_if_blocked(response: Response, result: RateLimitResult) -> None:
    response.headers["X-RateLimit-Limit"] = str(result.limit)
    response.headers["X-RateLimit-Remaining"] = str(result.remaining)
    response.headers["X-RateLimit-Reset"] = str(round(result.reset_after, 2))
    if not result.allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "Retry-After": str(round(result.retry_after, 2)),
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": str(result.remaining),
                "X-RateLimit-Reset": str(round(result.reset_after, 2)),
            },
        )


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


@router.get("/config/routes", response_model=dict[str, RouteLimitResponse])
async def list_route_limits(
    manager: LimiterManager = Depends(get_manager),
) -> dict[str, RouteLimitResponse]:
    """Storage only right now -- nothing in check()/peek() enforces these yet."""
    return {
        path: RouteLimitResponse(path=path, **override.__dict__)
        for path, override in manager.route_limits.items()
    }


@router.post("/config/routes", response_model=RouteLimitResponse)
async def set_route_limit(
    body: RouteLimitRequest, manager: LimiterManager = Depends(get_manager)
) -> RouteLimitResponse:
    override = RouteLimitOverride(
        capacity=body.capacity,
        window_seconds=body.window_seconds,
        refill_rate=body.refill_rate,
    )
    manager.set_route_limit(body.path, override)
    return RouteLimitResponse(path=body.path, **override.__dict__)


@router.post("/config/routes/clear")
async def clear_route_limit(
    body: RouteLimitClearRequest, manager: LimiterManager = Depends(get_manager)
) -> dict:
    manager.clear_route_limit(body.path)
    return {"status": "cleared", "path": body.path}


@router.post("/limiter/check", response_model=CheckResponse)
async def check_limiter(
    body: CheckRequest, response: Response, manager: LimiterManager = Depends(get_manager)
) -> CheckResponse:
    """Used by the GUI's live traffic simulator: fires one real request
    through the currently configured limiter and reports the outcome."""
    result = await manager.check(body.client_id)
    response.headers["X-RateLimit-Limit"] = str(result.limit)
    response.headers["X-RateLimit-Remaining"] = str(result.remaining)
    response.headers["X-RateLimit-Reset"] = str(round(result.reset_after, 2))
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
    result = await manager.check(client_id, route=request.url.path)
    _apply_headers_and_raise_if_blocked(response, result)

    return {"message": "here is your data", "client_id": client_id, "remaining": result.remaining}


@router.get("/demo/api-resource")
async def demo_api_resource(
    request: Request,
    response: Response,
    manager: LimiterManager = Depends(get_manager),
) -> dict:
    """Like /demo/resource, but gated by X-API-Key instead of X-Client-Id/IP
    -- demonstrates per-API-key rate limiting. No fallback to IP here: a
    missing key is rejected with 401, per the project's decision on this
    (unlike demo_resource, which does fall back to IP)."""
    api_key = extract_api_key(request.headers)
    if api_key is None:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    result = await manager.check(api_key, route=request.url.path)
    _apply_headers_and_raise_if_blocked(response, result)

    return {"message": "here is your data", "api_key": api_key, "remaining": result.remaining}
