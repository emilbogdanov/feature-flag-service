from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from flagstaff.engine.keys import require_key

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

type JSONValue = bool | int | float | str | list[JSONValue] | dict[str, JSONValue] | None


class FlagKind(StrEnum):
    BOOLEAN = "boolean"
    STRING = "string"
    NUMBER = "number"
    JSON = "json"

    def accepts(self, value: JSONValue) -> bool:
        return _ACCEPTS[self](value)


@dataclass(frozen=True, slots=True)
class Variant:
    key: str
    value: JSONValue = field(hash=False)

    def __post_init__(self) -> None:
        require_key("variant", self.key)


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _is_json(value: object) -> bool:
    if value is None or isinstance(value, bool | str):
        return True
    if isinstance(value, int | float):
        return _is_number(value)
    if isinstance(value, list):
        return all(_is_json(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json(item) for key, item in value.items())
    return False


_ACCEPTS: Final[Mapping[FlagKind, Callable[[object], bool]]] = {
    FlagKind.BOOLEAN: lambda value: isinstance(value, bool),
    FlagKind.STRING: lambda value: isinstance(value, str),
    FlagKind.NUMBER: _is_number,
    FlagKind.JSON: _is_json,
}
