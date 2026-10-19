from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from flagstaff.engine.errors import InvalidFlagError
from flagstaff.engine.wire import ruleset_from_document, ruleset_to_document

if TYPE_CHECKING:
    from flagstaff.engine.ruleset import Ruleset

logger = logging.getLogger("flagstaff")


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
            Path(temporary.name).replace(self._path)
        except OSError:
            logger.warning("could not write the ruleset cache at %s", self._path, exc_info=True)
