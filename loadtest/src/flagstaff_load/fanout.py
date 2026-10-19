from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from flagstaff_load.stats import Summary
from flagstaff_load.target import Target, switch

if TYPE_CHECKING:
    import httpx

_REPORT_LIMIT_BYTES = 64 * 2**20


@dataclass(frozen=True, slots=True)
class FanoutSettings:
    streams: int
    # Processes holding the streams between them.
    workers: int
    edits: int


@dataclass(frozen=True, slots=True)
class FanoutResult:
    streams: int
    workers: int
    edits: int
    open_seconds: float
    # From sending the edit until each stream had the new rules, one sample per stream and edit.
    delivery: Summary
    # Only the last stream to get each edit: when every SDK had it.
    last_delivery: Summary


async def measure_fanout(
    base_url: str, admin: httpx.AsyncClient, target: Target, settings: FanoutSettings
) -> FanoutResult:
    streams, workers = settings.streams, settings.workers
    shares = [streams // workers + (1 if n < streams % workers else 0) for n in range(workers)]
    opened_at = time.perf_counter()
    holders = [await _Holder.start(base_url, target.sdk_key, share) for share in shares if share]
    try:
        # Every stream opens with the current ruleset, the same version for all of them.
        versions = {await holder.expect("ready", within=120.0) for holder in holders}
        if len(versions) != 1:
            raise RuntimeError(f"the streams opened on different versions: {sorted(versions)}")
        open_seconds = time.perf_counter() - opened_at
        sent_at = await _time_edits(admin, target, holders, versions.pop(), settings.edits)
        arrivals: dict[int, list[float]] = {}
        for holder in holders:
            for version, times in (await holder.stop()).items():
                arrivals.setdefault(version, []).extend(times)
    finally:
        for holder in holders:
            holder.kill()
    delays = {version: [t - sent for t in arrivals[version]] for version, sent in sent_at.items()}
    return FanoutResult(
        streams=streams,
        workers=len(holders),
        edits=settings.edits,
        open_seconds=open_seconds,
        delivery=Summary.of([delay for per_edit in delays.values() for delay in per_edit]),
        last_delivery=Summary.of([max(per_edit) for per_edit in delays.values()]),
    )


async def _time_edits(
    admin: httpx.AsyncClient, target: Target, holders: list[_Holder], version: int, edits: int
) -> dict[int, float]:
    sent_at: dict[int, float] = {}
    # The load flag starts switched on, so the first edit switches it off.
    on = False
    for _ in range(edits):
        # Every switch moves the environment's ruleset on by exactly one version.
        version += 1
        sent_at[version] = time.time()
        await switch(admin, target, on=on)
        on = not on
        for holder in holders:
            await holder.expect("have", version=version, within=30.0)
        # Lets the streams go quiet again, so each edit is timed on its own.
        await asyncio.sleep(0.25)
    return sent_at


# One stream_worker process and the lines it sends back.
class _Holder:
    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self._process = process

    @classmethod
    async def start(cls, base_url: str, sdk_key: str, count: int) -> _Holder:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "flagstaff_load.stream_worker",
            base_url,
            str(count),
            env={**os.environ, "FLAGSTAFF_LOAD_SDK_KEY": sdk_key},
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            # The closing report is one line holding every arrival time.
            limit=_REPORT_LIMIT_BYTES,
        )
        return cls(process)

    async def expect(self, kind: str, *, within: float, version: int | None = None) -> int:
        async with asyncio.timeout(within):
            while True:
                word, _, value = (await self._line()).partition(" ")
                if word == "failed":
                    raise RuntimeError(f"a stream worker stopped: {value}")
                if word == kind and (version is None or int(value) == version):
                    return int(value)

    async def stop(self) -> dict[int, list[float]]:
        stdin = self._process.stdin
        if stdin is None:
            raise RuntimeError("the stream worker has no stdin")
        stdin.write(b"stop\n")
        await stdin.drain()
        async with asyncio.timeout(30.0):
            report = json.loads(await self._line())
        await self._process.wait()
        return {int(version): times for version, times in report.items()}

    def kill(self) -> None:
        if self._process.returncode is None:
            self._process.kill()

    async def _line(self) -> str:
        stdout = self._process.stdout
        if stdout is None:
            raise RuntimeError("the stream worker has no stdout")
        line = await stdout.readline()
        if not line:
            raise RuntimeError("a stream worker exited before it was done")
        return line.decode().rstrip("\n")
