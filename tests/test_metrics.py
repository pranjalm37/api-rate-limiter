"""Unit tests for MetricsRegistry's counting/bucketing logic, plus
API-level tests confirming the demo endpoints (and only the demo
endpoints) actually update it. Prometheus text validity is covered
separately in test_metrics_rendering.py."""

import pytest

from app.metrics import MetricsRegistry


def test_total_requests_increments_per_record():
    m = MetricsRegistry()
    assert m.total_requests == 0
    m.record_request("fixed_window", allowed=True)
    m.record_request("fixed_window", allowed=False)
    assert m.total_requests == 2


def test_counts_split_by_algorithm_and_outcome():
    m = MetricsRegistry()
    m.record_request("fixed_window", allowed=True)
    m.record_request("fixed_window", allowed=True)
    m.record_request("fixed_window", allowed=False)
    m.record_request("token_bucket", allowed=True)

    counts = m.counts_by_algorithm_outcome()
    assert counts[("fixed_window", "allowed")] == 2
    assert counts[("fixed_window", "rejected")] == 1
    assert counts[("token_bucket", "allowed")] == 1
    assert ("token_bucket", "rejected") not in counts


def test_counts_snapshot_does_not_expose_internal_state():
    m = MetricsRegistry()
    m.record_request("fixed_window", allowed=True)
    snapshot = m.counts_by_algorithm_outcome()
    snapshot[("fixed_window", "allowed")] = 999
    assert m.counts_by_algorithm_outcome()[("fixed_window", "allowed")] == 1


def test_latency_samples_recorded_in_order():
    m = MetricsRegistry()
    m.record_latency(0.001)
    m.record_latency(0.002)
    assert m.latency_samples() == [0.001, 0.002]


def test_latency_histogram_buckets_are_cumulative_and_monotonic():
    m = MetricsRegistry()
    for s in [0.00005, 0.0003, 0.0003, 0.02, 2.0]:
        m.record_latency(s)

    histogram = m.latency_histogram()
    counts = [count for _, count in histogram["buckets"]]

    assert counts == sorted(counts)  # cumulative buckets never decrease
    assert histogram["count"] == 5
    assert histogram["sum"] == pytest.approx(2.02065)
    # The +Inf bucket (last one) must cover every sample, including the
    # 2.0s outlier that's past every finite boundary.
    assert histogram["buckets"][-1] == (float("inf"), 5)


def test_latency_histogram_empty_registry():
    m = MetricsRegistry()
    histogram = m.latency_histogram()
    assert histogram["count"] == 0
    assert histogram["sum"] == 0
    assert all(count == 0 for _, count in histogram["buckets"])


@pytest.mark.asyncio
async def test_demo_endpoints_increment_metrics_but_check_and_401_dont(client):
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

    from app.limiter_manager import get_manager

    manager = get_manager()
    start = manager.metrics.total_requests

    await client.get("/api/demo/resource", headers={"X-Client-Id": "metrics-a"})
    await client.get("/api/demo/api-resource", headers={"X-API-Key": "metrics-b"})
    assert manager.metrics.total_requests == start + 2

    await client.get("/api/demo/api-resource")  # 401, missing key
    assert manager.metrics.total_requests == start + 2  # unchanged

    await client.post("/api/limiter/check", json={"client_id": "metrics-c"})
    assert manager.metrics.total_requests == start + 2  # unchanged
