// Client-side ports of the four algorithms implemented server-side in
// app/limiters/*.py. This file makes no network calls -- it exists so the
// visualizer can be hosted as a static page. The production implementations,
// with concurrency-safe atomic storage and a pytest suite, live in the repo.
//
// Each limiter exposes:
//   check() -> { allowed, limit, remaining }   consumes quota
//   peek()  -> remaining                        inspects without consuming
// peek() is what lets the chart sample available quota continuously, so
// refill and window resets are visible even while no traffic is flowing.

function nowSeconds() {
  return Date.now() / 1000;
}

class FixedWindowLimiter {
  constructor(capacity, windowSeconds) {
    this.capacity = capacity;
    this.windowSeconds = windowSeconds;
    this.count = 0;
    this.windowStart = nowSeconds();
  }

  _rollWindow(t) {
    if (t - this.windowStart >= this.windowSeconds) {
      this.count = 0;
      this.windowStart = t;
    }
  }

  check() {
    const t = nowSeconds();
    this._rollWindow(t);
    this.count += 1;
    return {
      allowed: this.count <= this.capacity,
      limit: this.capacity,
      remaining: Math.max(this.capacity - this.count, 0),
    };
  }

  peek() {
    const t = nowSeconds();
    if (t - this.windowStart >= this.windowSeconds) return this.capacity;
    return Math.max(this.capacity - this.count, 0);
  }
}

class SlidingWindowLogLimiter {
  constructor(capacity, windowSeconds) {
    this.capacity = capacity;
    this.windowSeconds = windowSeconds;
    this.log = [];
  }

  _trim(t) {
    const cutoff = t - this.windowSeconds;
    this.log = this.log.filter((ts) => ts > cutoff);
  }

  check() {
    const t = nowSeconds();
    this._trim(t);
    const allowed = this.log.length < this.capacity;
    if (allowed) this.log.push(t);
    return {
      allowed,
      limit: this.capacity,
      remaining: Math.max(this.capacity - this.log.length, 0),
    };
  }

  peek() {
    this._trim(nowSeconds());
    return Math.max(this.capacity - this.log.length, 0);
  }
}

class SlidingWindowCounterLimiter {
  constructor(capacity, windowSeconds) {
    this.capacity = capacity;
    this.windowSeconds = windowSeconds;
    this.counts = new Map(); // window index -> count
  }

  _weighted(t) {
    const index = Math.floor(t / this.windowSeconds);
    const elapsed = (t % this.windowSeconds) / this.windowSeconds;
    const current = this.counts.get(index) || 0;
    const previous = this.counts.get(index - 1) || 0;
    return { index, current, weighted: previous * (1 - elapsed) + current };
  }

  check() {
    const t = nowSeconds();
    let { index, current, weighted } = this._weighted(t);
    const allowed = weighted < this.capacity;

    if (allowed) {
      this.counts.set(index, current + 1);
      weighted = this._weighted(t).weighted;
    }

    for (const key of this.counts.keys()) {
      if (key < index - 1) this.counts.delete(key);
    }

    return {
      allowed,
      limit: this.capacity,
      remaining: Math.max(Math.floor(this.capacity - weighted), 0),
    };
  }

  peek() {
    const { weighted } = this._weighted(nowSeconds());
    return Math.max(Math.floor(this.capacity - weighted), 0);
  }
}

class TokenBucketLimiter {
  constructor(capacity, refillRate) {
    this.capacity = capacity;
    this.refillRate = refillRate; // tokens per second
    this.tokens = capacity;
    this.lastTs = nowSeconds();
  }

  _refill(t) {
    const elapsed = Math.max(t - this.lastTs, 0);
    this.tokens = Math.min(this.capacity, this.tokens + elapsed * this.refillRate);
    this.lastTs = t;
  }

  check() {
    this._refill(nowSeconds());
    let allowed = false;
    if (this.tokens >= 1) {
      this.tokens -= 1;
      allowed = true;
    }
    return { allowed, limit: this.capacity, remaining: Math.floor(this.tokens) };
  }

  peek() {
    this._refill(nowSeconds());
    return Math.floor(this.tokens);
  }
}

const ALGORITHMS = {
  token_bucket: {
    label: "Token bucket",
    ctor: TokenBucketLimiter,
    usesRefill: true,
    blurb:
      "Refills tokens continuously and lets short bursts through up to the bucket size, while capping the long-run average rate. What most production APIs use.",
  },
  fixed_window: {
    label: "Fixed window",
    ctor: FixedWindowLimiter,
    usesRefill: false,
    blurb:
      "Counts requests in fixed clock-aligned intervals. Cheapest to run, but a burst straddling a window boundary can push through roughly twice the limit.",
  },
  sliding_window_log: {
    label: "Sliding window log",
    ctor: SlidingWindowLogLimiter,
    usesRefill: false,
    blurb:
      "Stores every request timestamp and evaluates the trailing window exactly. No boundary burst, but memory grows with request volume.",
  },
  sliding_window_counter: {
    label: "Sliding window counter",
    ctor: SlidingWindowCounterLimiter,
    usesRefill: false,
    blurb:
      "Approximates the sliding window by weighting two adjacent fixed-window counters. Close to exact, at fixed-window cost.",
  },
};
