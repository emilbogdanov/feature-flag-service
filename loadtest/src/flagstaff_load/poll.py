from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass

from flagstaff_load.stats import Summary

# Time for every worker process to start and connect before they all begin together.
_START_DELAY_SECONDS = 3.0


@dataclass(frozen=True, slots=True)
class PollSettings:
    workers: int
    connections: int
    seconds: float


@dataclass(frozen=True, slots=True)
class PollResult:
    seconds: float
    latency: Summary
    statuses: dict[int, int]
    errors: int

    @property
    def requests_per_second(self) -> float:
        return self.latency.count / self.seconds


async def measure_polling(
    base_url: str, sdk_key: str, settings: PollSettings, *, revalidate: bool
) -> PollResult:
    start_at = time.time() + _START_DELAY_SECONDS
    environment = {**os.environ, "FLAGSTAFF_LOAD_SDK_KEY": sdk_key}
    arguments = [
        base_url,
        "revalidate" if revalidate else "fetch",
        str(settings.connections),
        str(start_at),
        str(settings.seconds),
    ]
    processes = [
        await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "flagstaff_load.poll_worker",
            *arguments,
            env=environment,
            stdout=asyncio.subprocess.PIPE,
        )
        for _ in range(settings.workers)
    ]
    outputs = await asyncio.gather(*(process.communicate() for process in processes))
    if failed := [p.returncode for p in processes if p.returncode != 0]:
        raise RuntimeError(f"{len(failed)} polling workers failed; their errors are above")

    latencies: list[float] = []
    statuses: Counter[int] = Counter()
    errors = 0
    for stdout, _ in outputs:
        part = json.loads(stdout)
        latencies.extend(part["latencies"])
        statuses.update({int(status): count for status, count in part["statuses"].items()})
        errors += part["errors"]
        if part["first_error"]:
            sys.stderr.write(f"a polling worker saw: {part['first_error']}\n")
    return PollResult(
        seconds=settings.seconds,
        latency=Summary.of(latencies),
        statuses=dict(statuses),
        errors=errors,
    )
