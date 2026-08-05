// Client-side ports of the same 4 algorithms implemented server-side in
// app/limiters/*.py. This file has no network calls -- it's a self-contained
// visualizer so the demo can be hosted as a static GitHub Pages site.
// The real, backend-verified implementations (with concurrency-safe atomic
// storage and a pytest suite) live in the repo this page links back to.

function now() {
  return Date.now() / 1000;
}

class FixedWindowLimiter {
  constructor(capacity, windowSeconds) {
    this.capacity = capacity;
    this.windowSeconds = windowSeconds;
    this.count = 0;
    this.windowStart = now();
  }

  check() {
    const t = now();
    if (t - this.windowStart >= this.windowSeconds) {
      this.count = 0;
      this.windowStart = t;
    }
    this.count += 1;
    const allowed = this.count <= this.capacity;
    return {
      allowed,
      limit: this.capacity,
      remaining: Math.max(this.capacity - this.count, 0),
    };
  }
}

class SlidingWindowLogLimiter {
  constructor(capacity, windowSeconds) {
    this.capacity = capacity;
    this.windowSeconds = windowSeconds;
    this.log = [];
  }

  check() {
    const t = now();
    const cutoff = t - this.windowSeconds;
    this.log = this.log.filter((ts) => ts > cutoff);

    const allowed = this.log.length < this.capacity;
    if (allowed) this.log.push(t);

    return {
      allowed,
      limit: this.capacity,
      remaining: Math.max(this.capacity - this.log.length, 0),
    };
  }
}

class SlidingWindowCounterLimiter {
  constructor(capacity, windowSeconds) {
    this.capacity = capacity;
    this.windowSeconds = windowSeconds;
    this.counts = new Map(); // windowIndex -> count
  }

  check() {
    const t = now();
    const windowIndex = Math.floor(t / this.windowSeconds);
    const elapsedFraction = (t % this.windowSeconds) / this.windowSeconds;

    const current = this.counts.get(windowIndex) || 0;
    const previous = this.counts.get(windowIndex - 1) || 0;

    let weighted = previous * (1 - elapsedFraction) + current;
    const allowed = weighted < this.capacity;

    if (allowed) {
      this.counts.set(windowIndex, current + 1);
      weighted = previous * (1 - elapsedFraction) + (current + 1);
    }

    // Keep the map small.
    for (const key of this.counts.keys()) {
      if (key < windowIndex - 1) this.counts.delete(key);
    }

    return {
      allowed,
      limit: this.capacity,
      remaining: Math.max(Math.floor(this.capacity - weighted), 0),
    };
  }
}

class TokenBucketLimiter {
  constructor(capacity, refillRate) {
    this.capacity = capacity;
    this.refillRate = refillRate; // tokens per second
    this.tokens = capacity;
    this.lastTs = now();
  }

  check() {
    const t = now();
    const elapsed = Math.max(t - this.lastTs, 0);
    this.tokens = Math.min(this.capacity, this.tokens + elapsed * this.refillRate);
    this.lastTs = t;

    let allowed;
    if (this.tokens >= 1.0) {
      this.tokens -= 1.0;
      allowed = true;
    } else {
      allowed = false;
    }

    return {
      allowed,
      limit: this.capacity,
      remaining: Math.floor(this.tokens),
    };
  }
}

const ALGORITHMS = {
  token_bucket: { label: "Token Bucket", ctor: TokenBucketLimiter, usesRefill: true },
  fixed_window: { label: "Fixed Window", ctor: FixedWindowLimiter, usesRefill: false },
  sliding_window_log: { label: "Sliding Window Log", ctor: SlidingWindowLogLimiter, usesRefill: false },
  sliding_window_counter: {
    label: "Sliding Window Counter",
    ctor: SlidingWindowCounterLimiter,
    usesRefill: false,
  },
};
