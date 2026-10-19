# A flag's version travels as its ETag, and edits send it back in If-Match, so an edit made from
# a stale page fails with 412 instead of silently undoing someone else's change.
import re
from typing import Final

from flagstaff_server.domain.errors import InvalidValueError

_VERSION_TAG: Final = re.compile(r'"(\d{1,18})"')


class VersionRequiredError(Exception):
    def __init__(self) -> None:
        super().__init__(
            'this edit needs an If-Match header with the flag\'s ETag, such as If-Match: "3"'
        )


def etag(version: int) -> str:
    return f'"{version}"'


# "*" asks for the edit whatever the current version is, the same as leaving the header out
# where that is allowed.
def expected_version(if_match: str | None, *, required: bool) -> int | None:
    if if_match is None:
        if required:
            raise VersionRequiredError
        return None
    if if_match.strip() == "*":
        return None
    match = _VERSION_TAG.fullmatch(if_match.strip())
    if match is None:
        raise InvalidValueError(f'If-Match must be one ETag such as "3", not {if_match!r}')
    return int(match.group(1))
