from __future__ import annotations

import json
import logging
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Final

from flagstaff.engine.errors import InvalidFlagError
from flagstaff.engine.wire import ruleset_from_document, ruleset_to_document

if TYPE_CHECKING:
    from flagstaff.engine.ruleset import Ruleset

logger = logging.getLogger("flagstaff")

# Windows won't replace a file that anything has open: another process loading the cache, or a
# virus scanner looking at the file just written. Either lets go within milliseconds.
_REPLACE_ATTEMPTS: Final = 5
_REPLACE_BACKOFF_SECONDS: Final = 0.02


# The last ruleset this app received, so a process that starts while the server is down still
# serves the rules it last knew instead of every default in the code.
class RulesetFile:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Ruleset | None:
        try:
            document = json.loads(self._path.read_text(encoding="utf-8"))
            return ruleset_from_document(document)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, InvalidFlagError):
            logger.warning("ignored an unreadable ruleset cache at %s", self._path, exc_info=True)
            return None

    # Written to a temporary file and renamed into place, so a crash mid-write leaves the old
    # cache rather than half of a new one.
    def save(self, ruleset: Ruleset) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self._path.parent, delete=False, suffix=".tmp"
            ) as temporary:
                json.dump(ruleset_to_document(ruleset), temporary, separators=(",", ":"))
        except OSError:
            logger.warning("could not write the ruleset cache at %s", self._path, exc_info=True)
            return
        written = Path(temporary.name)
        try:
            self._replace_with(written)
        except OSError:
            written.unlink(missing_ok=True)
            logger.warning("could not write the ruleset cache at %s", self._path, exc_info=True)

    # The SDK saves from a worker thread, never the event loop, so waiting here blocks nothing.
    def _replace_with(self, written: Path) -> None:
        for attempt in range(1, _REPLACE_ATTEMPTS + 1):
            try:
                written.replace(self._path)
            except PermissionError:
                if attempt == _REPLACE_ATTEMPTS:
                    raise
                time.sleep(_REPLACE_BACKOFF_SECONDS * attempt)
            else:
                return
