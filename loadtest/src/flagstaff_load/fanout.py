from __future__ import annotations

import asyncio
import time
from collections import Counter, defaultdict
from contextlib import suppress
from dataclasses import dataclass, field

import httpx

from flagstaff_load.stats import Summary
from flagstaff_load.target import Target, switch


# How many of the streams have each ruleset version, so the test can wait for all of them
# without polling every stream in a loop that would compete with them for the event loop.
class Fleet:
    def __init__(self, size: int) -> None:
        self.size = size
        self._received: Counter[int] = Counter()
        self._complete: defaultdict[int, asyncio.Event] = defaultdict(asyncio.Event)

    def received(self, version: int) -> None:
        self._received[version] += 1
        if self._received[version] == self.size:
            self._complete[version].set()

    async def all_have(self, version: int) -> None:
        await self._complete[version].wait()


# One SSE stream's ruleset events, and when each version arrived. The time is taken as the
# event ends, which is when an SDK would have the new rules.
@dataclass
class StreamWatcher:
    fleet: Fleet
    arrivals: dict[int, float] = field(default_factory=dict)
    _event_id: int | None = None

    @property
    def latest(self) -> int | None:
        return max(self.arrivals, default=None)

    def feed(self, line: str, now: float) -> None:
        if line.startswith("id:"):
            self._event_id = int(line.removeprefix("id:").strip())
        elif not line and self._event_id is not None:
            if self._event_id not in self.arrivals:
                self.arrivals[self._event_id] = now
                self.fleet.received(self._event_id)
            self._event_id = None


@dataclass(frozen=True, slots=True)
class FanoutResult:
    streams: int
    edits: int
    open_seconds: float
    # From sending the edit until each stream had the new rules, one sample per stream and edit.
    delivery: Summary
    # Only the last stream to get each edit: when every SDK had it.
    last_delivery: Summary


async def measure_fanout(
    base_url: str, admin: httpx.AsyncClient, target: Target, *, streams: int, edits: int
) -> FanoutResult:
    limits = httpx.Limits(max_connections=streams, max_keepalive_connections=0)
    # The server sends a keep-alive every 15 s, so a minute without a byte is a dead stream.
    timeout = httpx.Timeout(10.0, read=60.0)
    headers = {"Authorization": f"Bearer {target.sdk_key}"}
    async with httpx.AsyncClient(
        base_url=base_url, headers=headers, limits=limits, timeout=timeout
    ) as client:
        opened_at = time.perf_counter()
        open_streams = _OpenStreams(client, streams)
        try:
            # Every stream opens with the current ruleset, the same version for all of them.
            version = await open_streams.first_version()
            await open_streams.until_all_have(version, within=120.0)
            open_seconds = time.perf_counter() - opened_at
            delivery, last_delivery = await _time_edits(admin, target, open_streams, version, edits)
        finally:
            await open_streams.close()
    return FanoutResult(
        streams=streams,
        edits=edits,
        open_seconds=open_seconds,
        delivery=delivery,
        last_delivery=last_delivery,
    )


async def _time_edits(
    admin: httpx.AsyncClient, target: Target, streams: _OpenStreams, version: int, edits: int
) -> tuple[Summary, Summary]:
    delivery: list[float] = []
    last_delivery: list[float] = []
    # The load flag starts switched on, so the first edit switches it off.
    on = False
    for _ in range(edits):
        # Every switch moves the environment's ruleset on by exactly one version.
        version += 1
        sent = time.perf_counter()
        await switch(admin, target, on=on)
        on = not on
        await streams.until_all_have(version, within=30.0)
        delays = [arrived - sent for arrived in streams.arrivals_of(version)]
        delivery.extend(delays)
        last_delivery.append(max(delays))
        # Lets the streams go quiet again, so each edit is timed on its own.
        await asyncio.sleep(0.25)
    return Summary.of(delivery), Summary.of(last_delivery)


class _OpenStreams:
    def __init__(self, client: httpx.AsyncClient, count: int) -> None:
        self._fleet = Fleet(count)
        self._watchers = [StreamWatcher(self._fleet) for _ in range(count)]
        self._tasks = [asyncio.create_task(self._follow(client, w)) for w in self._watchers]

    async def first_version(self) -> int:
        deadline = time.perf_counter() + 30.0
        while (version := self._watchers[0].latest) is None:
            self._raise_if_any_failed()
            if time.perf_counter() > deadline:
                raise RuntimeError("the first stream sent no ruleset within 30 s")
            await asyncio.sleep(0.01)
        return version

    # A stream only ever ends by failing, so a finished one means the run can't complete.
    async def until_all_have(self, version: int, *, within: float) -> None:
        waiting = asyncio.ensure_future(self._fleet.all_have(version))
        done, _ = await asyncio.wait(
            [waiting, *self._tasks], timeout=within, return_when=asyncio.FIRST_COMPLETED
        )
        if waiting in done:
            return
        waiting.cancel()
        self._raise_if_any_failed()
        raise RuntimeError(f"not every stream had version {version} within {within:.0f} s")

    def arrivals_of(self, version: int) -> list[float]:
        return [watcher.arrivals[version] for watcher in self._watchers]

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.gather(*self._tasks, return_exceptions=True)

    @staticmethod
    async def _follow(client: httpx.AsyncClient, watcher: StreamWatcher) -> None:
        async with client.stream("GET", "/sdk/stream") as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                watcher.feed(line, time.perf_counter())

    def _raise_if_any_failed(self) -> None:
        failed = [task for task in self._tasks if task.done() and not task.cancelled()]
        if failed:
            first = failed[0].exception()
            raise RuntimeError(f"{len(failed)} streams failed, the first with: {first!r}")
