# One load-generating process for the polling test, run by poll.py as `python -m`. A single
# Python process can't send requests as fast as two API instances answer them, so the test runs
# several; each reports back as one JSON object on standard output.
import asyncio
import json
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass

import httpx


@dataclass(frozen=True, slots=True)
class _Plan:
    revalidate: bool
    connections: int
    # Wall-clock time, so every worker process begins at the same moment.
    start_at: float
    seconds: float


async def _poll(base_url: str, sdk_key: str, plan: _Plan) -> dict[str, object]:
    connections = plan.connections
    limits = httpx.Limits(max_connections=connections, max_keepalive_connections=connections)
    headers = {"Authorization": f"Bearer {sdk_key}"}
    latencies: list[float] = []
    statuses: Counter[int] = Counter()
    errors: list[str] = []
    async with httpx.AsyncClient(
        base_url=base_url, headers=headers, limits=limits, timeout=10.0
    ) as client:
        held = (await client.get("/sdk/ruleset")).headers["ETag"]
        # An SDK that polls sends the ETag of the rules it holds and mostly hears 304.
        request_headers = {"If-None-Match": held} if plan.revalidate else {}
        await asyncio.sleep(max(0.0, plan.start_at - time.time()))
        deadline = time.perf_counter() + plan.seconds

        async def keep_asking() -> None:
            while time.perf_counter() < deadline:
                sent = time.perf_counter()
                try:
                    response = await client.get("/sdk/ruleset", headers=request_headers)
                    await response.aread()
                except httpx.HTTPError as error:
                    errors.append(repr(error))
                    continue
                latencies.append(time.perf_counter() - sent)
                statuses[response.status_code] += 1

        async with asyncio.TaskGroup() as tasks:
            for _ in range(connections):
                tasks.create_task(keep_asking())
    return {
        "latencies": latencies,
        "statuses": dict(statuses),
        "errors": len(errors),
        "first_error": errors[0] if errors else None,
    }


def main() -> None:
    base_url, revalidate, connections, start_at, seconds = sys.argv[1:6]
    plan = _Plan(
        revalidate=revalidate == "revalidate",
        connections=int(connections),
        start_at=float(start_at),
        seconds=float(seconds),
    )
    result = asyncio.run(_poll(base_url, os.environ["FLAGSTAFF_LOAD_SDK_KEY"], plan))
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
