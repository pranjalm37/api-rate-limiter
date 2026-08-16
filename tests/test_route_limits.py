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
