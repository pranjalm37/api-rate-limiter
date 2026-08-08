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
    assert second.status_code == 429
    assert "Retry-After" in second.headers


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
