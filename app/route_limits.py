from dataclasses import dataclass


@dataclass
class RouteLimitOverride:
    """Per-route override of the global limiter configuration's numbers.

    All fields are optional -- a route can override just one knob (e.g.
    capacity) and inherit the rest from the global LimiterConfig.

    Deliberately numbers-only: a route cannot override the algorithm, only
    capacity/window_seconds/refill_rate. Decided against per-route algorithm
    overrides -- it would mean picking the right Store type per algorithm in
    the route-limiter cache too (GCRA needs a GCRAStore, others need a
    Store), for a use case ("this one endpoint needs a different limiting
    strategy entirely") that's rare enough not to be worth that complexity.
    """

    capacity: int | None = None
    window_seconds: float | None = None
    refill_rate: float | None = None
