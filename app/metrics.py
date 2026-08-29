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
