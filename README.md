# API Rate Limiter

[![CI](https://github.com/pranjalm37/api-rate-limiter/actions/workflows/ci.yml/badge.svg)](https://github.com/pranjalm37/api-rate-limiter/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Live demo](https://img.shields.io/badge/demo-live-2a78d6.svg)](https://pranjalm37.github.io/api-rate-limiter/)

Four rate-limiting algorithms implemented from scratch in Python, behind one
interface, with a pluggable in-memory or Redis backend and an interactive
visualizer that shows how each one actually behaves under load.

**[→ Try the live demo](https://pranjalm37.github.io/api-rate-limiter/)**

![The visualizer showing a token bucket draining under a burst, then refilling](docs/preview.png)

## What this demonstrates

Rate limiting looks trivial and isn't. This implements it directly — no
`slowapi`, no `fastapi-limiter` — to work through the parts that are actually
hard:

**Algorithm trade-offs.** Fixed window is cheap but lets a burst straddling a
boundary through at roughly twice the limit. A sliding window log is exact but
stores every timestamp. A sliding window counter approximates the log at
constant cost. A token bucket allows controlled bursts while capping the
long-run rate. The demo makes each one's signature visible: watch the quota
line cliff-reset under fixed window versus ramp back under a token bucket.

**Concurrency correctness.** Refill-then-consume on a token bucket is a
textbook read-modify-write race: two simultaneous requests can both read the
same token count and both be allowed. It's implemented as one atomic step per
backend — an `asyncio.Lock` in memory, a Lua script in Redis — and pinned by a
test that fires 50 concurrent requests at a 5-token bucket and asserts exactly
5 get through.

**Storage that swaps without touching the algorithms.** Every limiter is
written against the `Store` interface in `app/storage/base.py`, so the same
algorithm code runs in-process for a demo or against Redis across many
instances. Nothing in `app/limiters/` knows which backend it has.

**Observability without side effects.** The dashboard charts remaining quota
over time, which needs a *non-consuming* read — otherwise the chart's own
polling would register as traffic and corrupt what it's measuring. Hence
`peek()` alongside `check()`, with tests asserting it never spends quota.

## Quickstart

```bash
pip install -r requirements.txt && uvicorn app.main:app --reload
```

Then open <http://localhost:8000> for the dashboard, or `/docs` for the
generated OpenAPI reference.

Everything above runs in-process with no external services. To use the
distributed backend:

```bash
docker compose up --build
```

That starts Redis alongside the API; switch the store to `redis` in the
dashboard, or set `RATE_LIMITER_BACKEND=redis`.

## Architecture

```
app/
  limiters/          four algorithms, each implementing RateLimiter.check()/.peek()
    fixed_window.py
    sliding_window_log.py
    sliding_window_counter.py
    token_bucket.py
  storage/           pluggable backend behind one Store interface
    memory.py        in-process, asyncio.Lock-guarded
    redis_store.py   Redis, Lua scripts for atomic incr / token consume
  api/routes.py      /config, /limiter/check, /limiter/peek, /demo/resource
  limiter_manager.py holds the live configuration shared by the API and the UI
  main.py            FastAPI app; also serves the dashboard
docs/                the static visualizer published to GitHub Pages
frontend/            the dashboard served by FastAPI, driving the real API
tests/               21 tests: per-algorithm, concurrency, peek, and API-level
```

A request takes this path:

```
client ──▶ /api/demo/resource ──▶ LimiterManager.check(client_id)
                                        │
                                        ▼
                          RateLimiter (active algorithm)
                                        │
                                        ▼
                          Store (memory or redis) — atomic ops
                                        │
                              allow 200 / deny 429 + Retry-After
```

## The algorithms

| Algorithm | Accuracy | Cost per key | Notes |
|---|---|---|---|
| Fixed window | Loose at edges | O(1) | Can pass ~2× the limit across a boundary |
| Sliding window log | Exact | O(requests in window) | Correct, but stores every timestamp |
| Sliding window counter | Approximate | O(1) | Weights two adjacent windows; good cost/accuracy trade |
| Token bucket | Exact, burst-friendly | O(1) | Industry default — AWS API Gateway, Stripe |

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/demo/resource` | GET | A protected endpoint, limited by `X-Client-Id` (falls back to caller IP) |
| `/api/limiter/check` | POST | Consume one unit of quota for a `client_id` |
| `/api/limiter/peek` | GET | Read remaining quota **without** consuming |
| `/api/limiter/reset` | POST | Clear all limiter state |
| `/api/config` | GET/POST | Read or change the active algorithm, backend, and limits |

`demo/resource` returns `429` with `Retry-After`, `X-RateLimit-Limit`, and
`X-RateLimit-Remaining` — the response shape a real gateway would produce:

```bash
curl -i -H "X-Client-Id: demo" http://localhost:8000/api/demo/resource
```

## Two frontends

| | `frontend/` | `docs/` |
|---|---|---|
| Runs against | The real FastAPI service | Nothing — pure client-side JS |
| Hosted at | Wherever you run it | [GitHub Pages](https://pranjalm37.github.io/api-rate-limiter/) |
| Exists to | Prove the system works end to end, including atomic storage | Let anyone see the algorithms without hosting a server |

`docs/algorithms.js` ports the decision logic from `app/limiters/*.py` — same
math, same edge cases — so the hosted demo behaves like the real thing without
needing a backend. Both share a design: self-hosted Geist / Geist Mono (SIL
OFL) so neither page has an external dependency, and allowed vs rejected
requests are distinguished by tick *direction* as well as colour, since
green/red alone is not separable with red-green colour blindness.

Regenerate the README image after a design change:

```bash
python scripts/screenshot.py
```

## Tests

```bash
pytest tests/ -v
```

21 tests, no network or external services required. Covers each algorithm's
limit and recovery behaviour, the concurrency guarantee, `peek()`
non-consumption, and the API surface (including 429 headers and validation).
CI runs them on every push and also builds the Docker image and smoke-tests
the container.

## What I'd add next

- Per-endpoint and per-tier limits rather than one global configuration
- A middleware wrapper so any route can be decorated instead of calling the limiter directly
- Prometheus metrics for allow/deny rates
- Benchmarks comparing the backends under concurrent load

## License

MIT — see [LICENSE](LICENSE). Bundled Geist fonts are SIL OFL 1.1.
