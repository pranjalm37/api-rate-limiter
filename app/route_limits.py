from dataclasses import dataclass

from app.limiters import Algorithm


@dataclass
class RouteLimitOverride:
    """Per-route override of the global limiter configuration.

    All fields are optional -- a route can override just one knob (e.g.
    capacity) and inherit the rest from the global LimiterConfig. Whether
    `algorithm` overrides get honored is still an open decision (a route
    running a different algorithm than the global one is a bigger change
    than overriding numbers); it's included here so this shape doesn't
    need to change later if the answer turns out to be yes.

    Not wired into anything yet -- this is just the data shape.
    """

    algorithm: Algorithm | None = None
    capacity: int | None = None
    window_seconds: float | None = None
    refill_rate: float | None = None
