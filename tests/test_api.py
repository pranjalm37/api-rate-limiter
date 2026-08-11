import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client):
    res = await client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_configure_and_check_flow(client):
    configure = await client.post(
        "/api/config",
        json={
            "algorithm": "fixed_window",
            "backend": "memory",
            "capacity": 2,
            "window_seconds": 5,
            "refill_rate": 1,
        },
    )
    assert configure.status_code == 200
    assert configure.json()["algorithm"] == "fixed_window"

    await client.post("/api/limiter/reset")

    first = await client.post("/api/limiter/check", json={"client_id": "api-test"})
    second = await client.post("/api/limiter/check", json={"client_id": "api-test"})
    third = await client.post("/api/limiter/check", json={"client_id": "api-test"})

    assert first.json()["allowed"] is True
    assert second.json()["allowed"] is True
    assert third.json()["allowed"] is False

    # /limiter/check always returns 200 (blocked is reported in the JSON
    # body, not a 429), but the same X-RateLimit-* headers should still be
    # set correctly on every response, allowed or not.
    assert [r.headers["X-RateLimit-Limit"] for r in (first, second, third)] == ["2", "2", "2"]
    assert [r.headers["X-RateLimit-Remaining"] for r in (first, second, third)] == ["1", "0", "0"]
    assert all(float(r.headers["X-RateLimit-Reset"]) > 0 for r in (first, second, third))


@pytest.mark.asyncio
async def test_demo_resource_returns_429_with_headers_when_blocked(client):
    await client.post(
        "/api/config",
        json={
            "algorithm": "fixed_window",
            "backend": "memory",
            "capacity": 1,
            "window_seconds": 5,
            "refill_rate": 1,
        },
    )
    await client.post("/api/limiter/reset")

    headers = {"X-Client-Id": "demo-resource-test"}
    first = await client.get("/api/demo/resource", headers=headers)
    second = await client.get("/api/demo/resource", headers=headers)

    assert first.status_code == 200
    assert first.headers["X-RateLimit-Limit"] == "1"
    assert first.headers["X-RateLimit-Remaining"] == "0"
    assert float(first.headers["X-RateLimit-Reset"]) > 0

    assert second.status_code == 429
    assert "Retry-After" in second.headers
    assert second.headers["X-RateLimit-Limit"] == "1"
    assert second.headers["X-RateLimit-Remaining"] == "0"
    assert float(second.headers["X-RateLimit-Reset"]) > 0


@pytest.mark.asyncio
async def test_demo_resource_remaining_header_decrements_across_allowed_requests(client):
    await client.post(
        "/api/config",
        json={
            "algorithm": "fixed_window",
            "backend": "memory",
            "capacity": 3,
            "window_seconds": 5,
            "refill_rate": 1,
        },
    )
    await client.post("/api/limiter/reset")

    headers = {"X-Client-Id": "demo-resource-remaining-test"}
    responses = [await client.get("/api/demo/resource", headers=headers) for _ in range(3)]

    assert [r.status_code for r in responses] == [200, 200, 200]
    assert [r.headers["X-RateLimit-Remaining"] for r in responses] == ["2", "1", "0"]
    assert all(r.headers["X-RateLimit-Limit"] == "3" for r in responses)


@pytest.mark.asyncio
async def test_gcra_selectable_as_algorithm(client):
    configure = await client.post(
        "/api/config",
        json={
            "algorithm": "gcra",
            "backend": "memory",
            "capacity": 2,
            "window_seconds": 5,
            "refill_rate": 1,
        },
    )
    assert configure.status_code == 200
    assert configure.json()["algorithm"] == "gcra"

    await client.post("/api/limiter/reset")

    first = await client.post("/api/limiter/check", json={"client_id": "gcra-api-test"})
    second = await client.post("/api/limiter/check", json={"client_id": "gcra-api-test"})
    third = await client.post("/api/limiter/check", json={"client_id": "gcra-api-test"})

    assert first.json()["allowed"] is True
    assert second.json()["allowed"] is True
    assert third.json()["allowed"] is False
    assert third.json()["algorithm"] == "gcra"

    peek = await client.get("/api/limiter/peek", params={"client_id": "gcra-api-test"})
    assert peek.status_code == 200
    assert peek.json()["algorithm"] == "gcra"


@pytest.mark.asyncio
async def test_configure_rejects_invalid_capacity(client):
    res = await client.post(
        "/api/config",
        json={
            "algorithm": "token_bucket",
            "backend": "memory",
            "capacity": -1,
            "window_seconds": 5,
            "refill_rate": 1,
        },
    )
    assert res.status_code == 422
