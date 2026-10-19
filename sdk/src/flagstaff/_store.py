from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from flagstaff.engine.ruleset import Ruleset


# The ruleset every evaluation reads. Reads take no lock: swapping one immutable Ruleset for
# another is a single reference assignment, so an evaluation sees either the old rules or the
# new ones, never a mix. Only writers lock, so a late, older ruleset can't replace a newer one.
class RulesetStore:
    def __init__(self) -> None:
        self._ruleset: Ruleset | None = None
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._listeners: list[Callable[[Ruleset], None]] = []

    @property
    def ruleset(self) -> Ruleset | None:
        return self._ruleset

    def replace(self, ruleset: Ruleset) -> bool:
        with self._lock:
            current = self._ruleset
            if current is not None and ruleset.version <= current.version:
                return False
            self._ruleset = ruleset
            listeners = list(self._listeners)
        self._ready.set()
        for listener in listeners:
            listener(ruleset)
        return True

    # Called, on the writer's thread, with every ruleset that replaces the one before.
    def add_listener(self, listener: Callable[[Ruleset], None]) -> None:
        with self._lock:
            self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[Ruleset], None]) -> None:
        with self._lock:
            self._listeners.remove(listener)

    def wait_until_ready(self, timeout: float | None) -> bool:
        return self._ready.wait(timeout)
