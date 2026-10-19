from flagstaff_load.streams import Fleet, StreamWatcher


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def feed(watcher: StreamWatcher, lines: list[str]) -> None:
    for line in lines:
        watcher.feed(line)


def test_notes_when_each_version_arrived() -> None:
    clock = Clock()
    watcher = StreamWatcher(Fleet(1, lambda _: None), clock)

    clock.now = 0.5
    feed(watcher, ["retry: 1000", ""])
    clock.now = 1.0
    feed(watcher, ["id: 3", "event: ruleset", 'data: {"version":3}', ""])
    clock.now = 2.0
    feed(watcher, [": keep-alive", ""])
    clock.now = 3.0
    feed(watcher, ["id: 4", "event: ruleset", 'data: {"version":4}', ""])

    assert watcher.arrivals == {3: 1.0, 4: 3.0}


def test_keeps_the_first_arrival_of_a_version_sent_twice() -> None:
    clock = Clock()
    watcher = StreamWatcher(Fleet(1, lambda _: None), clock)

    clock.now = 1.0
    feed(watcher, ["id: 3", 'data: {"version":3}', ""])
    clock.now = 2.0
    feed(watcher, ["id: 3", 'data: {"version":3}', ""])

    assert watcher.arrivals == {3: 1.0}


def test_the_fleet_reports_a_version_once_every_stream_has_it() -> None:
    complete: list[int] = []
    fleet = Fleet(2, complete.append)
    first, second = StreamWatcher(fleet), StreamWatcher(fleet)

    feed(first, ["id: 7", "data: {}", ""])
    assert complete == []

    feed(second, ["id: 7", "data: {}", ""])
    assert complete == [7]
