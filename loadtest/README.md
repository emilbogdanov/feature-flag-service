# flagstaff-loadtest

`flagstaff-load` measures a running Flagstaff stack and writes the results as Markdown. It creates
a project of its own on every run, so it never touches anything else on the server. The numbers
in [docs/load-test.md](../docs/load-test.md) come from it.

```
docker compose up --build --wait
docker compose exec api-1 flagstaff-server create-admin-key --name "load test"
cd loadtest
uv run flagstaff-load --url http://localhost:8080 --admin-key fs_admin_... --output ../docs/load-test.md
```

It measures three things, one after the other:

1. **Flag checks in the SDK.** `bool_value` on a flag with a user-list rule and a two-condition
   attribute rule served by a 25% rollout, for a spread of users, on one thread, for 3 s.
2. **Ruleset polls.** `GET /sdk/ruleset` for 10 s with the current `ETag`, answered `304`, then
   10 s without it, answered with the whole ruleset. A single Python process can't send requests
   as fast as two instances answer them, so 4 worker processes with 10 connections each do it.
3. **Edits reaching open streams.** 1,000 SDK streams held by 4 processes, then 20 edits made one
   at a time, each timed from sending it until every stream has the new ruleset. One process
   reading every stream fell behind when an edit reached them all at once and counted its own lag
   as the server's.

`flagstaff-load --help` lists the options for each of those numbers. The load comes from the same
machine as the stack, so the two compete for the same cores; the report says which machine it was.
