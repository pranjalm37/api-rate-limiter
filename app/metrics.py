class MetricsRegistry:
    """In-process counters backing /api/metrics.

    Single-process, in-memory -- same scope as the rest of this app's
    non-Redis state. Not wired into any endpoint yet; that's a follow-up
    change. Split-by-allowed/rejected/algorithm and latency histograms are
    also follow-ups -- this is just the total-request counter.
    """

    def __init__(self) -> None:
        self.total_requests = 0

    def record_request(self) -> None:
        self.total_requests += 1
