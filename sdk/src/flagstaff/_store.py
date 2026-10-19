from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flagstaff.engine.ruleset import Ruleset


# The ruleset every evaluation reads. Reads take no lock: swapping one immutable Ruleset for
# another is a single reference assignment, so an evaluation sees either the old rules or the
# new ones, never a mix. Only writers lock, so a late, older ruleset can't replace a newer one.
class RulesetStore:
    def __init__(self) -> None:
        self._ruleset: Ruleset | None = None
        self._lock = threading.Lock()
        self._ready = threading.Event()

    @property
    def ruleset(self) -> Ruleset | None:
        return self._ruleset

    def replace(self, ruleset: Ruleset) -> bool:
        with self._lock:
            current = self._ruleset
            if current is not None and ruleset.version <= current.version:
                return False
            self._ruleset = ruleset
        self._ready.set()
        return True

    def wait_until_ready(self, timeout: float | None) -> bool:
        return self._ready.wait(timeout)
