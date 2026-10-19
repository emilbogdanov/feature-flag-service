# Holds a share of the SDK streams for the fan-out test, run by fanout.py as `python -m`. One
# process reading a thousand streams falls behind as an edit lands on all of them at once, and
# its lag would be counted as the server's; several processes keep that out of the numbers.
#
# It talks to fanout.py in lines: "ready <version>" once every stream has its first ruleset,
# "have <version>" once every stream has a later one, then, when told "stop", every arrival as
# JSON. "failed <reason>" ends it early.
import asyncio
import json
import os
import sys

import httpx

from flagstaff_load.streams import Fleet, StreamWatcher


def _say(line: str) -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


async def _follow(client: httpx.AsyncClient, watcher: StreamWatcher) -> None:
    async with client.stream("GET", "/sdk/stream") as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            watcher.feed(line)


async def _hold(base_url: str, sdk_key: str, count: int) -> dict[int, list[float]]:
    first: list[int] = []

    def on_complete(version: int) -> None:
        _say(f"have {version}" if first else f"ready {version}")
        first.append(version)

    fleet = Fleet(count, on_complete)
    watchers = [StreamWatcher(fleet) for _ in range(count)]
    limits = httpx.Limits(max_connections=count, max_keepalive_connections=0)
    # The server sends a keep-alive every 15 s, so a minute without a byte is a dead stream.
    timeout = httpx.Timeout(10.0, read=60.0)
    headers = {"Authorization": f"Bearer {sdk_key}"}
    async with httpx.AsyncClient(
        base_url=base_url, headers=headers, limits=limits, timeout=timeout
    ) as client:
        following = [asyncio.create_task(_follow(client, watcher)) for watcher in watchers]
        stopping = asyncio.create_task(asyncio.to_thread(sys.stdin.readline))
        done, _ = await asyncio.wait([stopping, *following], return_when=asyncio.FIRST_COMPLETED)
        for task in following:
            task.cancel()
        await asyncio.gather(*following, return_exceptions=True)
        if stopping not in done:
            failed = next(task for task in following if task in done)
            raise RuntimeError(f"a stream failed: {failed.exception()!r}")
    arrivals: dict[int, list[float]] = {}
    for watcher in watchers:
        for version, arrived in watcher.arrivals.items():
            arrivals.setdefault(version, []).append(arrived)
    return arrivals


def main() -> None:
    base_url, count = sys.argv[1:3]
    try:
        arrivals = asyncio.run(_hold(base_url, os.environ["FLAGSTAFF_LOAD_SDK_KEY"], int(count)))
    except RuntimeError as error:
        _say(f"failed {error}")
        sys.exit(1)
    _say(json.dumps(arrivals))


if __name__ == "__main__":
    main()
