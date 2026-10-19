# flagstaff-server

The Flagstaff API: projects and their environments, flags and their targeting, API keys, the
audit log, and the endpoints SDKs read rules from. FastAPI on async SQLAlchemy and Postgres, with
Redis carrying change notifications between instances. Setting it up with Docker, the design and
the measurements are in the [repository README](../README.md); this page is the reference.

## Running it without Docker

Needs Python 3.13, [uv](https://docs.astral.sh/uv/), and a Postgres and a Redis to point at.

```
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run flagstaff-server serve --port 8000
```

`uv run uvicorn --factory --reload flagstaff_server.main:app` reloads on every change instead,
but doesn't end SDK streams at once on shutdown, so a reload waits for them to time out.

## Command line

| Command | |
| --- | --- |
| `flagstaff-server serve [--host] [--port] [--graceful-timeout SECONDS]` | run the API; on SIGTERM it ends SDK streams first, then gives other requests up to 10 s |
| `flagstaff-server create-admin-key --name NAME` | issue an admin key and print only its secret, for scripts to capture; the first key has to come from here |
| `flagstaff-server openapi [--output FILE]` | write the OpenAPI schema; needs no database or settings |
| `alembic upgrade head` | apply the migrations |

Errors in the settings or an unreachable database end with one line on stderr and exit status 2
or 1, not a traceback.

## API

Every request carries `Authorization: Bearer <secret>`. Admin keys (`fs_admin_...`) manage
everything; SDK keys (`fs_sdk_...`) read one environment's rules and nothing else. The full schema
is served at `/docs` and `/openapi.json`.

| Method and path | Key | |
| --- | --- | --- |
| `POST /projects` | admin | create a project, with `dev`, `staging` and `prod` environments |
| `GET /projects`, `GET /projects/{project}` | admin | |
| `GET /projects/{project}/environments`, `POST` the same | admin | list or add environments |
| `POST /projects/{project}/flags` | admin | create a flag, switched off everywhere |
| `GET /projects/{project}/flags`, `GET .../flags/{flag}` | admin | |
| `PATCH .../flags/{flag}` | admin | name and description; needs `If-Match` |
| `PUT .../flags/{flag}/variants` | admin | needs `If-Match` |
| `PUT .../flags/{flag}/environments/{env}/targeting` | admin | rules, fallthrough and off variant for one environment; needs `If-Match` |
| `POST .../flags/{flag}/environments/{env}/enable`, `.../disable` | admin | the kill switch; `If-Match` optional |
| `POST .../flags/{flag}/archive` | admin | takes the flag out of every ruleset; `If-Match` optional |
| `GET /projects/{project}/environments/{env}/ruleset` | admin | what that environment's SDKs receive |
| `POST /projects/{project}/environments/{env}/evaluate` | admin | what given users would get, without an SDK |
| `POST /api-keys`, `GET /api-keys`, `POST /api-keys/{id}/revoke` | admin | |
| `GET /audit?project=&limit=&cursor=` | admin | every change, newest first, paged by cursor |
| `GET /sdk/ruleset` | SDK | the environment's rules; answers `304` to the current `If-None-Match` |
| `GET /sdk/stream` | SDK | server-sent events: the ruleset now and after every change |
| `POST /sdk/evaluate` | SDK | evaluation on the server, for clients without an SDK |
| `GET /health`, `GET /metrics` | none | liveness, and Prometheus metrics for each instance |

A flag's version is its `ETag`. Edits send it back in `If-Match`: a stale one gets `412`, a
missing one `428`. A kill switch doesn't need it, because turning a flag off has to work from a
script that never read the flag; if two switches race, the one that loses is applied again on
the flag as the other left it.

Targeting rules are tried in order and the first match serves. A rule's conditions all have to
hold. A condition is either a `user_list` of keys, or an `attribute` compared with `in`,
`contains`, `starts_with`, `ends_with`, `lt`, `lte`, `gt` or `gte`, optionally negated. A rule
serves one variant or a percentage `rollout`, in weights out of 100,000 that add up to 100,000.

Errors share one body, with a stable `code` to branch on:

```json
{"detail": "flag 'new-checkout' is no longer at version 1, it is at 2", "code": "version_mismatch"}
```

## Tests

```
uv run pytest
```

Integration tests start Postgres and Redis with testcontainers, so Docker has to be running. To
use ones you already have, set `FLAGSTAFF_TEST_DATABASE_URL` and `FLAGSTAFF_TEST_REDIS_URL`: the
tests drop and recreate the schema and flush Redis, so point them at nothing you want to keep.
`tests/stack` drives the compose stack from outside and only runs with `FLAGSTAFF_STACK_URL` set.
