from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


# How many streams have each ruleset version, calling back once all of them do, so nothing has
# to poll every stream in a loop that would compete with them for the event loop.
class Fleet:
    def __init__(self, size: int, on_complete: Callable[[int], None]) -> None:
        self.size = size
        self._on_complete = on_complete
        self._received: Counter[int] = Counter()

    def received(self, version: int) -> None:
        self._received[version] += 1
        if self._received[version] == self.size:
            self._on_complete(version)


# One SSE stream's ruleset events, and when each version arrived, in wall-clock time so the
# process that made the edit can compare. The time is taken as the event ends, which is when an
# SDK would have the new rules.
@dataclass
class StreamWatcher:
    fleet: Fleet
    clock: Callable[[], float] = time.time
    arrivals: dict[int, float] = field(default_factory=dict)
    _event_id: int | None = None

    def feed(self, line: str) -> None:
        if line.startswith("id:"):
            self._event_id = int(line.removeprefix("id:").strip())
        elif not line and self._event_id is not None:
            if self._event_id not in self.arrivals:
                self.arrivals[self._event_id] = self.clock()
                self.fleet.received(self._event_id)
            self._event_id = None
