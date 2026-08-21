"""End-to-end tests for /api/demo/api-resource -- the endpoint gated by
X-API-Key instead of X-Client-Id/IP. Unit-level coverage of the extraction
helper itself lives in test_apikey.py."""

import pytest


@pytest.mark.asyncio
async def test_two_api_keys_on_the_same_route_stay_independent(client):
    await client.post(
        "/api/config",
        json={
            "algorithm": "fixed_window",
            "backend": "memory",
            "capacity": 2,
            "window_seconds": 5,
            "refill_rate": 1,
        },
    )
    await client.post("/api/limiter/reset")

    key_a = {"X-API-Key": "key-a-independent-test"}
    key_b = {"X-API-Key": "key-b-independent-test"}

    # Drain key A's quota completely.
    first_a = await client.get("/api/demo/api-resource", headers=key_a)
    second_a = await client.get("/api/demo/api-resource", headers=key_a)
    blocked_a = await client.get("/api/demo/api-resource", headers=key_a)
    assert [first_a.status_code, second_a.status_code, blocked_a.status_code] == [200, 200, 429]

    # Key B has never been seen -- it must have its own full quota,
    # completely unaffected by key A being drained.
    first_b = await client.get("/api/demo/api-resource", headers=key_b)
    second_b = await client.get("/api/demo/api-resource", headers=key_b)
    assert first_b.status_code == 200
    assert second_b.status_code == 200
