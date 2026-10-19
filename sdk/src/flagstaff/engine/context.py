from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

from flagstaff.engine.errors import InvalidContextError

if TYPE_CHECKING:
    from collections.abc import Mapping

type AttributeValue = str | int | float | bool


@dataclass(frozen=True, slots=True)
class EvaluationContext:
    user_key: str
    attributes: Mapping[str, AttributeValue] = field(default_factory=dict, hash=False)

    def __post_init__(self) -> None:
        if not self.user_key:
            raise InvalidContextError("user_key must not be empty")
        for name, value in self.attributes.items():
            _require_attribute_value(name, value)
        # A private copy: the caller's dict may change afterwards, this context may not.
        object.__setattr__(self, "attributes", MappingProxyType(dict(self.attributes)))

    def attribute(self, name: str) -> AttributeValue | None:
        return self.attributes.get(name)


# Typed callers can't get this wrong, but the SDK is called from untyped code too, and a list
# or None that slipped in would otherwise show up much later as a rule that never matches.
def _require_attribute_value(name: str, value: object) -> None:
    if not isinstance(value, str | int | float):
        raise InvalidContextError(
            f"attribute {name!r} is a {type(value).__name__}; use str, int, float or bool"
        )
