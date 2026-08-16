"""Per-route rate limit overrides -- set via /api/config/routes, enforced
by LimiterManager._limiter_for(), currently only reachable through
/api/demo/resource (the one endpoint that has a real "route")."""

import pytest


@pytest.mark.asyncio
async def test_two_routes_with_different_capacities_are_independent(client):
    await client.post(
        "/api/config",
        json={
            "algorithm": "fixed_window",
            "backend": "memory",
            "capacity": 10,
            "window_seconds": 5,
            "refill_rate": 1,
        },
    )
    await client.post("/api/limiter/reset")

    # /api/demo/resource is overridden down to a tight capacity of 2.
    await client.post("/api/config/routes", json={"path": "/api/demo/resource", "capacity": 2})

    headers = {"X-Client-Id": "independent-routes-test"}

    # The overridden route blocks after 2, at well below the global capacity.
    demo_results = [await client.get("/api/demo/resource", headers=headers) for _ in range(3)]
    assert [r.status_code for r in demo_results] == [200, 200, 429]

    # /api/limiter/check has no route context, so it's still governed by the
    # untouched global capacity of 10 -- same client_id, same moment in time,
    # genuinely different quota because it's a different route.
    check_results = [
        await client.post("/api/limiter/check", json={"client_id": "independent-routes-test"})
        for _ in range(5)
    ]
    assert all(r.json()["allowed"] for r in check_results)


@pytest.mark.asyncio
async def test_route_with_no_override_uses_global_config(client):
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
    await client.post("/api/config/routes/clear", json={"path": "/api/demo/resource"})

    headers = {"X-Client-Id": "no-override-test"}
    results = [await client.get("/api/demo/resource", headers=headers) for _ in range(4)]

    # No override exists, so this should behave exactly like the global
    # config: capacity 3 allowed, the 4th blocked.
    assert [r.status_code for r in results] == [200, 200, 200, 429]
    assert all(r.headers["X-RateLimit-Limit"] == "3" for r in results)


@pytest.mark.asyncio
async def test_override_on_a_different_route_does_not_affect_this_one(client):
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

    # An override exists in route_limits, but for a path nobody is calling --
    # /api/demo/resource must still fall back to the global config, not get
    # caught by some accidental "any override present" logic.
    await client.post("/api/config/routes", json={"path": "/api/some/other/route", "capacity": 1})

    headers = {"X-Client-Id": "unrelated-override-test"}
    results = [await client.get("/api/demo/resource", headers=headers) for _ in range(3)]

    assert [r.status_code for r in results] == [200, 200, 200]
    assert all(r.headers["X-RateLimit-Limit"] == "3" for r in results)
