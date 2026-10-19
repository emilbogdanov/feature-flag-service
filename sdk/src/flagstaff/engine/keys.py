import re
from typing import Final

from flagstaff.engine.errors import InvalidFlagError

# No ":" allowed: bucketing hashes "flag-key:user-key", and keys travel in URLs and log lines.
_KEY: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def require_key(kind: str, key: str) -> None:
    if not _KEY.fullmatch(key):
        raise InvalidFlagError(
            f"{kind} key {key!r} must be 1-128 letters, digits, '.', '_' or '-', "
            "starting with a letter or digit"
        )
