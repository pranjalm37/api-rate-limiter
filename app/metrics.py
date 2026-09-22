from collections import defaultdict


class MetricsRegistry:
    """In-process counters backing /api/metrics.

    Single-process, in-memory -- same scope as the rest of this app's
    non-Redis state. Wired into the demo endpoints only (not /limiter/check,
    a synthetic GUI-testing path); latency histograms are a follow-up.
    """

    def __init__(self) -> None:
        self.total_requests = 0
        # (algorithm, "allowed" | "rejected") -> count
        self._by_algorithm_outcome: dict[tuple[str, str], int] = defaultdict(int)

    def record_request(self, algorithm: str, allowed: bool) -> None:
        self.total_requests += 1
        outcome = "allowed" if allowed else "rejected"
        self._by_algorithm_outcome[(algorithm, outcome)] += 1

    def counts_by_algorithm_outcome(self) -> dict[tuple[str, str], int]:
        """A snapshot copy -- callers must not be able to mutate internal state."""
        return dict(self._by_algorithm_outcome)


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
