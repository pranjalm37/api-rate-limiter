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


@pytest.mark.asyncio
async def test_missing_api_key_is_rejected_with_401(client):
    res = await client.get("/api/demo/api-resource")
    assert res.status_code == 401
    assert "X-API-Key" in res.json()["detail"]


@pytest.mark.asyncio
async def test_blank_api_key_header_is_also_rejected_with_401(client):
    """A present-but-empty header is treated the same as a missing one --
    extract_api_key() already does this; this confirms the endpoint
    actually relies on that instead of just checking the header exists."""
    res = await client.get("/api/demo/api-resource", headers={"X-API-Key": "   "})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_rejected_request_does_not_consume_quota(client):
    """A 401 should never spend rate-limit quota for anyone -- there's no
    key to attribute it to, and it never reached manager.check()."""
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

    await client.get("/api/demo/api-resource")  # 401, no key
    await client.get("/api/demo/api-resource")  # 401, no key

    # A real key should still get its full, untouched quota.
    res = await client.get("/api/demo/api-resource", headers={"X-API-Key": "fresh-after-401s"})
    assert res.status_code == 200
