import re
from dataclasses import dataclass
from typing import Final

from flagstaff_server.domain.errors import InvalidValueError

NAME_MAX_LENGTH: Final = 100
DESCRIPTION_MAX_LENGTH: Final = 1_000
SLUG_MAX_LENGTH: Final = 50

_SLUG: Final = re.compile(rf"[a-z0-9](?:[a-z0-9-]{{0,{SLUG_MAX_LENGTH - 2}}}[a-z0-9])?")


# Project and environment keys sit in URLs and in every SDK's configuration, so they are kept
# to the characters nobody has to escape or argue about the case of.
@dataclass(frozen=True, slots=True)
class Slug:
    value: str

    def __post_init__(self) -> None:
        if not _SLUG.fullmatch(self.value):
            raise InvalidValueError(
                f"key {self.value!r} must be 1-{SLUG_MAX_LENGTH} lowercase letters, digits "
                "or hyphens, and cannot start or end with a hyphen"
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Name:
    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise InvalidValueError("name must not be blank")
        if len(self.value) > NAME_MAX_LENGTH:
            raise InvalidValueError(f"name must be at most {NAME_MAX_LENGTH} characters")
        if "\n" in self.value or "\r" in self.value:
            raise InvalidValueError("name must be a single line")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Description:
    value: str = ""

    def __post_init__(self) -> None:
        if len(self.value) > DESCRIPTION_MAX_LENGTH:
            raise InvalidValueError(
                f"description must be at most {DESCRIPTION_MAX_LENGTH} characters"
            )

    def __str__(self) -> str:
        return self.value
