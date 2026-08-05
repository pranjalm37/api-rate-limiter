# API Rate Limiter

A rate limiter built from scratch in Python/FastAPI, implementing four
classic algorithms behind a common interface, with a pluggable in-memory or
Redis backend, and a live browser dashboard for demoing the behavior of each
algorithm in real time.

![status](https://img.shields.io/badge/tests-17%20passing-brightgreen)

## Why this project

Rate limiting is a small system with a lot of real engineering underneath it:
concurrency correctness, algorithm trade-offs, and distributed state. This
project implements it directly (no `slowapi`/`fastapi-limiter` dependency)
to demonstrate understanding of:

- **Algorithm trade-offs** — fixed window (cheap, bursty at boundaries),
  sliding window log (exact, memory-heavy), sliding window counter
  (approximate, cheap), and token bucket (allows controlled bursts).
- **Concurrency correctness** — the token bucket's refill-then-consume step
  is a classic read-modify-write race. It's implemented as a single atomic
  operation per backend (a lock in memory, a Lua script in Redis) and
  covered by a test that fires 50 concurrent requests at a 5-token bucket
  and asserts exactly 5 get through.
- **Swappable storage** — algorithms are written against a `Store` interface
  (`app/storage/base.py`), not against Redis or a dict directly, so the same
  algorithm code runs in-process for a demo or against Redis for a
  multi-instance deployment.

## Architecture

```
app/
  limiters/          # the 4 algorithms, each implementing RateLimiter.check()
    fixed_window.py
    sliding_window_log.py
    sliding_window_counter.py
    token_bucket.py
  storage/            # pluggable backend behind a shared Store interface
    memory.py         # in-process, asyncio.Lock-guarded
    redis_store.py    # Redis, Lua scripts for atomic incr / token consume
  api/routes.py        # /config, /limiter/check, /demo/resource
  limiter_manager.py    # holds the "live" configuration used by API + GUI
  main.py               # FastAPI app, serves the API and the static GUI
frontend/               # vanilla HTML/CSS/JS live traffic simulator (no build step)
tests/                  # 17 pytest cases: per-algorithm + API-level
```

### Request flow

```
client ──▶ /api/demo/resource ──▶ LimiterManager.check(client_id)
                                        │
                                        ▼
                          RateLimiter (current algorithm)
                                        │
                                        ▼
                          Store (memory or redis) — atomic ops
                                        │
                              allow (200) / deny (429 + Retry-After)
```

## Running it locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://localhost:8000` for the live dashboard, or `http://localhost:8000/docs`
for the Swagger UI.

### With Redis (distributed backend)

```bash
docker compose up -d redis
RATE_LIMITER_BACKEND=redis uvicorn app.main:app --reload
```

Or run everything in Docker:

```bash
docker compose up --build
```

### Tests

```bash
pytest tests/ -v
```

## Using the dashboard

1. Pick an algorithm, backend, capacity/window (or refill rate for token
   bucket), and click **Apply configuration**.
2. Click **Fire 1 request** / **Fire burst of 20**, or toggle **Auto-fire**
   to send a steady stream at an adjustable rate.
3. Watch the live timeline: green bars are allowed requests, red bars are
   429s. The remaining-quota bar and stat cards update in real time.
4. The **Try it from a real client** panel gives you a `curl` command
   hitting the exact same rate-limited endpoint the dashboard is driving —
   copy it into a terminal to see it get rate limited too.

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/config` | GET/POST | Read or change the active algorithm/backend/limits |
| `/api/limiter/check` | POST | Consume one unit of quota for a `client_id` (used by the GUI) |
| `/api/limiter/reset` | POST | Clear all rate-limit state |
| `/api/demo/resource` | GET | A protected demo endpoint, rate limited by `X-Client-Id` header (or caller IP) |

`demo/resource` returns `429` with `Retry-After`, `X-RateLimit-Limit`, and
`X-RateLimit-Remaining` headers when blocked — the standard shape a real API
gateway would return.

## Algorithms at a glance

| Algorithm | Accuracy | Memory cost | Notes |
|---|---|---|---|
| Fixed window | Low at boundaries | O(1) per key | Can allow ~2x capacity across a window edge |
| Sliding window log | Exact | O(requests in window) | Correct but stores every timestamp |
| Sliding window counter | Approximate | O(1) per key | Good accuracy/cost trade-off |
| Token bucket | Exact, burst-friendly | O(1) per key | Industry default (AWS, Stripe) |
