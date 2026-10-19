from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from itertools import accumulate
from typing import TYPE_CHECKING, Protocol

from flagstaff.engine.bucketing import BUCKET_COUNT, bucket
from flagstaff.engine.errors import InvalidFlagError

if TYPE_CHECKING:
    from flagstaff.engine.context import EvaluationContext


# What a matched rule, or a flag with no matching rule, hands out.
class Serve(Protocol):
    @property
    def variant_keys(self) -> frozenset[str]: ...

    def variant_for(self, flag_key: str, context: EvaluationContext) -> str: ...


@dataclass(frozen=True, slots=True)
class FixedVariant:
    variant_key: str

    @property
    def variant_keys(self) -> frozenset[str]:
        return frozenset({self.variant_key})

    def variant_for(self, flag_key: str, context: EvaluationContext) -> str:  # noqa: ARG002
        return self.variant_key


@dataclass(frozen=True, slots=True)
class WeightedVariant:
    variant_key: str
    weight: int

    def __post_init__(self) -> None:
        if not 0 <= self.weight <= BUCKET_COUNT:
            raise InvalidFlagError(
                f"variant {self.variant_key!r} has weight {self.weight}; "
                f"weights run from 0 to {BUCKET_COUNT}"
            )


# Variants own consecutive bucket ranges in the order listed. Growing a variant at the expense
# of its neighbours only moves the boundaries next to it, so nobody it already serves is moved
# out; with two variants that holds for any change. Keep the order stable when editing weights.
@dataclass(frozen=True, slots=True)
class Rollout:
    weights: tuple[WeightedVariant, ...]
    _upper_bounds: tuple[int, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        keys = [weighted.variant_key for weighted in self.weights]
        if not keys:
            raise InvalidFlagError("a rollout needs at least one variant")
        if len(set(keys)) != len(keys):
            raise InvalidFlagError(f"a rollout lists a variant more than once: {keys}")
        upper_bounds = tuple(accumulate(weighted.weight for weighted in self.weights))
        if upper_bounds[-1] != BUCKET_COUNT:
            raise InvalidFlagError(
                f"rollout weights add up to {upper_bounds[-1]}, not {BUCKET_COUNT}"
            )
        object.__setattr__(self, "_upper_bounds", upper_bounds)

    @property
    def variant_keys(self) -> frozenset[str]:
        return frozenset(weighted.variant_key for weighted in self.weights)

    def variant_for(self, flag_key: str, context: EvaluationContext) -> str:
        position = bisect_right(self._upper_bounds, bucket(flag_key, context.user_key))
        return self.weights[position].variant_key
