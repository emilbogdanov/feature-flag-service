import asyncio

from flagstaff_load.fanout import Fleet, StreamWatcher


def feed(watcher: StreamWatcher, lines: list[str], now: float) -> None:
    for line in lines:
        watcher.feed(line, now)


async def test_notes_when_each_version_arrived() -> None:
    watcher = StreamWatcher(Fleet(1))

    feed(watcher, ["retry: 1000", ""], 0.5)
    feed(watcher, ["id: 3", "event: ruleset", 'data: {"version":3}', ""], 1.0)
    feed(watcher, [": keep-alive", ""], 2.0)
    feed(watcher, ["id: 4", "event: ruleset", 'data: {"version":4}', ""], 3.0)

    assert watcher.arrivals == {3: 1.0, 4: 3.0}
    assert watcher.latest == 4


async def test_keeps_the_first_arrival_of_a_version_sent_twice() -> None:
    watcher = StreamWatcher(Fleet(1))

    feed(watcher, ["id: 3", 'data: {"version":3}', ""], 1.0)
    feed(watcher, ["id: 3", 'data: {"version":3}', ""], 2.0)

    assert watcher.arrivals == {3: 1.0}


async def test_the_fleet_is_complete_once_every_stream_has_the_version() -> None:
    fleet = Fleet(2)
    first, second = StreamWatcher(fleet), StreamWatcher(fleet)
    waiting = asyncio.ensure_future(fleet.all_have(7))

    feed(first, ["id: 7", "data: {}", ""], 1.0)
    await asyncio.sleep(0)
    assert not waiting.done()

    feed(second, ["id: 7", "data: {}", ""], 1.1)
    async with asyncio.timeout(1):
        await waiting
