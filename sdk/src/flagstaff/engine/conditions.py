from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from operator import ge, gt, le, lt
from typing import TYPE_CHECKING, Final, Protocol

from flagstaff.engine.errors import InvalidFlagError
from flagstaff.engine.numeric import is_number

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from flagstaff.engine.context import AttributeValue, EvaluationContext

type Matcher = Callable[[AttributeValue], bool]
type _Compiler = Callable[[Operator, tuple[AttributeValue, ...]], Matcher]


class Condition(Protocol):
    def matches(self, context: EvaluationContext) -> bool: ...


class Operator(StrEnum):
    IN = "in"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    LESS_THAN = "lt"
    LESS_THAN_OR_EQUAL = "lte"
    GREATER_THAN = "gt"
    GREATER_THAN_OR_EQUAL = "gte"

    # Values are checked and turned into a matcher once, when the flag is built, so evaluating a
    # condition with hundreds of values is a set lookup rather than a scan.
    def compile(self, values: tuple[AttributeValue, ...]) -> Matcher:
        if not values:
            raise InvalidFlagError(f"operator {self} needs at least one value")
        return _COMPILERS[self](self, values)


@dataclass(frozen=True, slots=True, kw_only=True)
class AttributeCondition:
    attribute: str
    operator: Operator
    values: tuple[AttributeValue, ...]
    negate: bool = False
    _matcher: Matcher = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.attribute:
            raise InvalidFlagError("a condition needs an attribute name")
        object.__setattr__(self, "_matcher", self.operator.compile(self.values))

    def matches(self, context: EvaluationContext) -> bool:
        value = context.attribute(self.attribute)
        # A missing attribute fails the condition, negated or not: "plan is not enterprise" is
        # not something we know about a context that has no plan at all.
        if value is None:
            return False
        return self._matcher(value) != self.negate


@dataclass(frozen=True, slots=True)
class UserListCondition:
    user_keys: frozenset[str]

    def __post_init__(self) -> None:
        if not self.user_keys:
            raise InvalidFlagError("a user list needs at least one user key")
        if "" in self.user_keys:
            raise InvalidFlagError("a user list cannot contain an empty user key")

    def matches(self, context: EvaluationContext) -> bool:
        return context.user_key in self.user_keys


def _compile_in(_operator: Operator, values: tuple[AttributeValue, ...]) -> Matcher:
    accepted = frozenset(_comparable(value) for value in values)
    return lambda value: _comparable(value) in accepted


# bool is a subclass of int and True == 1, so without the type tag a condition on seats in [1]
# would also match a context whose seats attribute is True. 1 and 1.0 share a tag on purpose.
def _comparable(value: AttributeValue) -> tuple[type, AttributeValue]:
    if isinstance(value, bool):
        return bool, value
    if isinstance(value, int | float):
        return float, value
    return str, value


def _compile_contains(operator: Operator, values: tuple[AttributeValue, ...]) -> Matcher:
    needles = _texts(operator, values)
    return lambda value: isinstance(value, str) and any(needle in value for needle in needles)


def _compile_starts_with(operator: Operator, values: tuple[AttributeValue, ...]) -> Matcher:
    prefixes = _texts(operator, values)
    return lambda value: isinstance(value, str) and value.startswith(prefixes)


def _compile_ends_with(operator: Operator, values: tuple[AttributeValue, ...]) -> Matcher:
    suffixes = _texts(operator, values)
    return lambda value: isinstance(value, str) and value.endswith(suffixes)


def _texts(operator: Operator, values: tuple[AttributeValue, ...]) -> tuple[str, ...]:
    texts = tuple(value for value in values if isinstance(value, str))
    if len(texts) != len(values):
        raise InvalidFlagError(f"operator {operator} compares text, got {values!r}")
    return texts


def _comparison(compare: Callable[[float, float], bool]) -> _Compiler:
    def compile_comparison(operator: Operator, values: tuple[AttributeValue, ...]) -> Matcher:
        bound = _single_number(operator, values)

        def matches(value: AttributeValue) -> bool:
            if isinstance(value, bool) or not isinstance(value, int | float):
                return False
            return compare(value, bound)

        return matches

    return compile_comparison


def _single_number(operator: Operator, values: tuple[AttributeValue, ...]) -> float:
    if len(values) == 1:
        (bound,) = values
        if isinstance(bound, int | float) and is_number(bound):
            return bound
    raise InvalidFlagError(f"operator {operator} takes exactly one finite number, got {values!r}")


_COMPILERS: Final[Mapping[Operator, _Compiler]] = {
    Operator.IN: _compile_in,
    Operator.CONTAINS: _compile_contains,
    Operator.STARTS_WITH: _compile_starts_with,
    Operator.ENDS_WITH: _compile_ends_with,
    Operator.LESS_THAN: _comparison(lt),
    Operator.LESS_THAN_OR_EQUAL: _comparison(le),
    Operator.GREATER_THAN: _comparison(gt),
    Operator.GREATER_THAN_OR_EQUAL: _comparison(ge),
}
