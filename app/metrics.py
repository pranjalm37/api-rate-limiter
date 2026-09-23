from collections import defaultdict

# Seconds. Spans microseconds (in-memory checks, typically single-digit
# microseconds) through low hundreds of milliseconds (a slow/contended
# Redis round trip) -- Prometheus's own default buckets top out at 10s and
# start at 5ms, which would dump nearly everything this app produces into
# the smallest bucket and tell you nothing.
DEFAULT_LATENCY_BUCKETS = (
    0.0001,  # 100us
    0.0005,  # 500us
    0.001,  # 1ms
    0.005,  # 5ms
    0.01,  # 10ms
    0.05,  # 50ms
    0.1,  # 100ms
    0.5,  # 500ms
    1.0,  # 1s
)


class MetricsRegistry:
    """In-process counters backing /api/metrics.

    Single-process, in-memory -- same scope as the rest of this app's
    non-Redis state. Wired into the demo endpoints only (not /limiter/check,
    a synthetic GUI-testing path); bucketing latency into a histogram is a
    follow-up (raw samples are collected already).
    """

    def __init__(self) -> None:
        self.total_requests = 0
        # (algorithm, "allowed" | "rejected") -> count
        self._by_algorithm_outcome: dict[tuple[str, str], int] = defaultdict(int)
        # Raw check() latency samples, in seconds. Not bucketed into a
        # histogram yet -- that's a follow-up change.
        self._latencies: list[float] = []

    def record_request(self, algorithm: str, allowed: bool) -> None:
        self.total_requests += 1
        outcome = "allowed" if allowed else "rejected"
        self._by_algorithm_outcome[(algorithm, outcome)] += 1

    def counts_by_algorithm_outcome(self) -> dict[tuple[str, str], int]:
        """A snapshot copy -- callers must not be able to mutate internal state."""
        return dict(self._by_algorithm_outcome)

    def record_latency(self, seconds: float) -> None:
        self._latencies.append(seconds)

    def latency_samples(self) -> list[float]:
        """A snapshot copy -- callers must not be able to mutate internal state."""
        return list(self._latencies)

    def latency_histogram(
        self, buckets: tuple[float, ...] = DEFAULT_LATENCY_BUCKETS
    ) -> dict[str, object]:
        """Bucket the raw samples into Prometheus histogram shape: cumulative
        per-boundary counts (each counts every sample <= that boundary, plus
        a final +Inf bucket covering everything), a sum, and a total count.

        Not rendered as Prometheus text yet -- that's a follow-up change.
        """
        samples = self._latencies
        cumulative = [(boundary, sum(1 for s in samples if s <= boundary)) for boundary in buckets]
        cumulative.append((float("inf"), len(samples)))
        return {
            "buckets": cumulative,
            "sum": sum(samples),
            "count": len(samples),
        }


def render_prometheus(registry: MetricsRegistry) -> str:
    """Render the registry's current state as Prometheus exposition text.

    Co-located with MetricsRegistry rather than in routes.py so the
    histogram-rendering follow-up extends this same function.
    """
    lines = [
        "# HELP rate_limiter_requests_total Total number of rate-limited requests processed.",
        "# TYPE rate_limiter_requests_total counter",
        f"rate_limiter_requests_total {registry.total_requests}",
        "",
        "# HELP rate_limiter_requests_by_outcome_total Requests processed, by algorithm and outcome.",
        "# TYPE rate_limiter_requests_by_outcome_total counter",
    ]
    # Sorted for deterministic output -- dict insertion order would otherwise
    # make this endpoint's response depend on which algorithm/outcome combo
    # happened to occur first, which is both untestable and unpleasant to read.
    for (algorithm, outcome), count in sorted(registry.counts_by_algorithm_outcome().items()):
        lines.append(
            f'rate_limiter_requests_by_outcome_total{{algorithm="{algorithm}",outcome="{outcome}"}} {count}'
        )
    return "\n".join(lines) + "\n"
