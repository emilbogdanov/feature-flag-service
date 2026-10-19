# Load test results

Measured on 2026-10-19 by `flagstaff-load` against the stack in [compose.yaml](../compose.yaml): nginx in front of two API instances, Postgres and Redis. The load came from the same machine, so it competed with the stack for the same cores.

| Machine | |
| --- | --- |
| OS | Windows-11 |
| CPU | AMD Ryzen 7 4800H with Radeon Graphics, 16 logical cores |
| Docker | 29.1.3, with 16 CPUs and 7.5 GiB for containers |
| Python running the load | 3.13.16 |

## Evaluating a flag in the app

An SDK holds its environment's rules in memory, so checking a flag never leaves the process. `bool_value` on a flag with a user-list rule and a two-condition attribute rule served by a 25% rollout, for a spread of users, on one thread:

- **184,716 evaluations a second**, 5.4 µs each

## Polling for rules

`GET /sdk/ruleset` through nginx, from 4 processes with 10 connections each, for 10 s per row. The ruleset holds 20 flags.

| | Requests a second | p50 | p95 | p99 | Max | Errors |
| --- | --- | --- | --- | --- | --- | --- |
| Rules unchanged, answered `304` | 288 | 127.6 ms | 225.4 ms | 312.2 ms | 519.0 ms | 0 |
| Whole ruleset, answered `200` | 189 | 203.5 ms | 275.1 ms | 436.6 ms | 577.5 ms | 0 |

## Pushing an edit to open streams

1,000 SDK streams open through nginx, spread over both instances, and 20 edits made one at a time through the admin API, each landing on whichever instance nginx picked and reaching the other through Redis. Time from sending the edit to a stream having the new ruleset:

| | p50 | p95 | p99 | Max |
| --- | --- | --- | --- | --- |
| Each stream | 253.0 ms | 326.0 ms | 381.0 ms | 396.9 ms |
| Last stream to get each edit | 310.1 ms | 343.0 ms | 396.9 ms | 396.9 ms |

Opening all 1,000 streams, each with its first ruleset, took 9.4 s.
