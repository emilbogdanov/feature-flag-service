# Flagstaff

A feature-flag service: targeting rules managed through an API, evaluated inside your app by a
Python SDK that the server keeps current over server-sent events.

[![backend](https://github.com/emilbogdanov/feature-flag-service/actions/workflows/backend.yml/badge.svg)](https://github.com/emilbogdanov/feature-flag-service/actions/workflows/backend.yml)
[![sdk](https://github.com/emilbogdanov/feature-flag-service/actions/workflows/sdk.yml/badge.svg)](https://github.com/emilbogdanov/feature-flag-service/actions/workflows/sdk.yml)
[![stack](https://github.com/emilbogdanov/feature-flag-service/actions/workflows/stack.yml/badge.svg)](https://github.com/emilbogdanov/feature-flag-service/actions/workflows/stack.yml)
![Python](https://img.shields.io/badge/python-3.12%2B-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## Features

- Projects with any number of environments (`dev`, `staging` and `prod` to start with). Each
  flag has variants of one kind (boolean, string, number or JSON) and its own targeting in every
  environment: ordered rules on user lists and attributes, percentage rollouts, a fallthrough,
  and a kill switch.
- The [`flagstaff`](sdk/) SDK evaluates in-process, in about 5 µs a check, and falls back to the
  default in your code, with a reason, whenever it can't answer. Sync and asyncio clients.
- An edit reaches a connected SDK in about 100 ms at the median, and the last of 1,000 in about
  170 ms, whichever instance each is on: the instance that saved the edit announces the new
  version on Redis, and each instance pushes the new rules down its own streams.
- SDKs that can't hold a stream open poll with `ETag`s instead, and a poll for unchanged rules
  usually costs the server no database query at all.
- Edits carry the version they were based on in `If-Match` and fail with `412` rather than
  overwrite a change made since. Every change lands in a cursor-paged audit log with who made it.
- API keys stored only as hashes: admin keys for the API, SDK keys that read one environment.
- Prometheus metrics, JSON logs with a request id on every line, and a shutdown that ends SDK
  streams at once so they reconnect to the other instance.

## Tech stack

Python 3.13, FastAPI, async SQLAlchemy 2.0 with asyncpg, PostgreSQL 18, Alembic, Redis 8 pub/sub,
uvicorn, nginx, Docker Compose. The SDK needs only httpx; its evaluation engine is standard
library only, and the server runs the same engine for previews. uv, ruff, mypy (strict), pytest
with testcontainers, and GitHub Actions.

## Quickstart

```
git clone https://github.com/emilbogdanov/feature-flag-service.git && cd feature-flag-service
docker compose up --build --wait
docker compose exec api-1 flagstaff-server create-admin-key --name "Release tooling"
```

The API answers on `http://localhost:8080` (set `FLAGSTAFF_PORT` to move it), with its schema at
`/docs`. The last command prints an admin key; it is shown once and only its hash is stored.

```
 ✔ Container flagstaff-postgres-1  Healthy
 ✔ Container flagstaff-redis-1     Healthy
 ✔ Container flagstaff-migrate-1   Exited
 ✔ Container flagstaff-api-1-1     Healthy
 ✔ Container flagstaff-api-2-1     Healthy
 ✔ Container flagstaff-proxy-1     Healthy
fs_admin_dq8eAjZLldv...
Admin key issued. Store the secret now: it cannot be shown again.
```

## Usage

A project, a flag, and targeting for production, with `ADMIN` holding that key:

```
$ curl -s -X POST localhost:8080/projects -H "Authorization: Bearer $ADMIN" \
    -H "Content-Type: application/json" -d '{"key": "storefront", "name": "Storefront"}'
{"key":"storefront","name":"Storefront","created_at":"2026-10-19T22:45:24.959927Z"}

$ curl -s -X POST localhost:8080/projects/storefront/flags -H "Authorization: Bearer $ADMIN" \
    -H "Content-Type: application/json" -d '{"key": "new-checkout", "name": "New checkout",
    "kind": "boolean", "variants": [{"key": "on", "value": true}, {"key": "off", "value": false}],
    "off_variant": "off", "on_variant": "on"}'
{"key":"new-checkout","name":"New checkout","kind":"boolean","version":1,"environments":{"dev":
{"enabled":false,"off_variant":"off","rules":[],"fallthrough":{"variant":"on"}},...}

$ curl -s -X PUT localhost:8080/projects/storefront/flags/new-checkout/environments/prod/targeting \
    -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" -H 'If-Match: "1"' \
    -d @targeting.json
```

where `targeting.json` switches the flag on for two testers, and for a quarter of pro customers
in Bulgaria and Germany:

```json
{
  "enabled": true,
  "off_variant": "off",
  "rules": [
    {
      "id": "beta-testers",
      "conditions": [{"type": "user_list", "user_keys": ["user-7", "user-1042"]}],
      "serve": {"variant": "on"}
    },
    {
      "id": "eu-pro",
      "conditions": [
        {"type": "attribute", "attribute": "country", "operator": "in", "values": ["BG", "DE"]},
        {"type": "attribute", "attribute": "plan", "operator": "in", "values": ["pro"]}
      ],
      "serve": {"rollout": [{"variant": "on", "weight": 25000}, {"variant": "off", "weight": 75000}]}
    }
  ],
  "fallthrough": {"variant": "off"}
}
```

Saving it again from the same `If-Match` fails, since the flag has moved on:

```
{"detail":"flag 'new-checkout' is no longer at version 1, it is at 2","code":"version_mismatch"}
```

An SDK key for production:

```
$ curl -s -X POST localhost:8080/api-keys -H "Authorization: Bearer $ADMIN" \
    -H "Content-Type: application/json" \
    -d '{"kind": "sdk", "name": "checkout-api", "project": "storefront", "environment": "prod"}'
{"id":"2832b1be-08b1-45af-9886-fda290becc3a","kind":"sdk","name":"checkout-api",
"project":"storefront","environment":"prod",...,"secret":"fs_sdk_5on8MtLbHkVd..."}
```

What the SDK receives over its stream, before and after someone hits the kill switch:

```
$ curl -sN localhost:8080/sdk/stream -H "Authorization: Bearer $SDK"
retry: 1000

id: 2
event: ruleset
data: {"format":1,"version":2,"flags":[{"key":"new-checkout","kind":"boolean","enabled":true,...

id: 3
event: ruleset
data: {"format":1,"version":3,"flags":[{"key":"new-checkout","kind":"boolean","enabled":false,...
```

Switched back on, the flag read from an app:

```python
from flagstaff import EvaluationContext, FlagstaffClient

with FlagstaffClient(sdk_key, base_url="http://localhost:8080") as flags:
    flags.wait_until_ready(timeout=5)
    print(flags.bool_value("new-checkout", "user-7", default=False))
    shopper = EvaluationContext("user-310", {"country": "DE", "plan": "pro"})
    print(flags.bool_detail("new-checkout", shopper, default=False))
```

```
True
FlagDetail(value=False, variant='off', reason=<Reason.RULE_MATCH: 'rule_match'>, rule_id='eu-pro', ruleset_version=4)
```

The [SDK README](sdk/README.md) covers the clients and their options, and the
[server README](backend/README.md) every endpoint, command and error.

## Performance

Measured on a laptop (Ryzen 7 4800H, Windows 11, Docker Desktop) with the stack above and the
load generated on the same machine; the method and the full tables are in
[docs/load-test.md](docs/load-test.md). The first column is the first run; the second is after
caching authenticated keys and ruleset versions, which the profiler showed were most of what an
unchanged-rules poll cost.

| | First run | Now |
| --- | --- | --- |
| Flag check in the SDK | 5.4 µs | 5.3 µs |
| Polls answered `304`, 40 connections | 288 a second, p50 127.6 ms | 457 a second, p50 46.8 ms |
| Polls answered with the whole ruleset | 189 a second, p50 203.5 ms | 242 a second, p50 159.6 ms |
| An edit reaching each of 1,000 streams, p50 | 253 ms | 103.5 ms |
| ... reaching the last of them, p50 | 310 ms | 170 ms |
| Opening 1,000 streams | 9.4 s | 4.4 s |

Part of the stream improvement is the measurement itself: the first run read all 1,000 streams in
one process, whose own lag counted as delivery time. The `304` tail is still long (p99 704 ms),
and two single-process instances on Docker Desktop are what these numbers describe.

## Project structure

```
backend/        the API: domain, application services, Postgres and Redis adapters, routes
  migrations/   Alembic
  tests/        unit, API, integration (testcontainers) and stack tests
sdk/            the flagstaff package; src/flagstaff/engine is the evaluation engine
loadtest/       flagstaff-load, which produced docs/load-test.md
deploy/         nginx and Prometheus configuration for the compose stack
compose.yaml    Postgres, Redis, migrations, two API instances, nginx
```

## Configuration

The server reads `FLAGSTAFF_` environment variables, or a `.env` file
([example](backend/.env.example)).

| Variable | Default | |
| --- | --- | --- |
| `FLAGSTAFF_DATABASE_URL` | required | `postgresql+asyncpg://...` |
| `FLAGSTAFF_REDIS_URL` | required | carries change notifications between instances |
| `FLAGSTAFF_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR` |
| `FLAGSTAFF_LOG_FORMAT` | `json` | `json` for shipping, `text` for a terminal |
| `FLAGSTAFF_STREAM_HEARTBEAT_SECONDS` | `15` | keep-alive on quiet streams, below any proxy's idle timeout |
| `FLAGSTAFF_RULESET_RESYNC_SECONDS` | `30` | how often streams are checked against the database, in case a notification was lost |
| `FLAGSTAFF_KEY_CACHE_SECONDS` | `10` | how long an instance trusts an authenticated key; `0` checks every time |
| `FLAGSTAFF_VERSION_CACHE_SECONDS` | `5` | how long an instance trusts a ruleset version it heard of |
| `FLAGSTAFF_PORT` | `8080` | compose only: where nginx listens on the host |

## Running tests

Each of `backend/`, `sdk/` and `loadtest/` is its own uv project:

```
cd backend && uv run pytest
```

The backend's integration tests start Postgres and Redis with testcontainers, so Docker has to be
running. `ruff check`, `ruff format --check` and `mypy` (strict) run the same way, and pre-commit
runs them on every commit. CI runs each project on every push, the SDK on Python 3.12, 3.13 and
3.14, and a `stack` job that starts the compose stack and tests it from outside, through a rolling
restart of both instances.

## Design notes

- **One engine, everywhere.** Evaluation lives in the SDK as plain Python with no dependencies, and
  the server imports the same package for its previews, so the dashboard and the app can't
  disagree. Users land in rollouts by SHA-256 of flag and user key over 100,000 buckets: the same
  user gets the same variant in every process, and widening a two-variant rollout only adds users.
- **Everything hangs on a version.** Each environment's ruleset has a number that every change
  moves on, in the same transaction as the change. It is the SSE event id, so a reconnecting SDK
  sends `Last-Event-ID` and isn't sent rules it has; it is the `ETag` for polls; and the SDK
  ignores anything older than what it holds.
- **Redis only says "environment X is at version N".** Each instance loads that version from
  Postgres once, however many of its streams want it. Pub/sub can drop a message, so instances also
  compare their streams with the database every 30 s; a lost notification costs at most that.
- **Ending streams on shutdown.** uvicorn waits for open connections before it shuts the app down,
  and an SDK stream never closes by itself, so every deploy waited out the graceful timeout and
  then cut the streams. `flagstaff-server serve` ends them as shutdown begins; nginx sends the
  reconnects to the other instance and never takes either out of rotation.
- **Bounded staleness for speed.** An instance trusts a key for 10 s and a ruleset version for 5 s.
  Revoking a key through one instance stops it there at once; through the other, within 10 s.

## Limitations and roadmap

- No dashboard yet: everything is done through the API. A React dashboard on the generated
  OpenAPI types is next.
- A revoked SDK key keeps a stream it already has open until that stream reconnects.
- Admin keys can do everything; there are no roles or per-project admin keys.
- An SDK never accepts an older ruleset, so after restoring the database to an earlier version,
  running SDKs keep their newer rules until the version passes them again.
- The SDK is Python only, and has no hook yet for being told when a flag changes.
- The SDK isn't on PyPI yet, so apps install it from a tag of this repository.
- Each instance is one process. Throughput grows by running more instances behind nginx; the
  numbers above are for two.

## License

MIT
