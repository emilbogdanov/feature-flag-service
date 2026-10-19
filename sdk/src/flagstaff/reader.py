from __future__ import annotations

import copy
import logging
import math
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, TypeGuard

from flagstaff.engine.context import EvaluationContext
from flagstaff.engine.errors import InvalidContextError
from flagstaff.engine.variants import FlagKind

if TYPE_CHECKING:
    from collections.abc import Callable

    from flagstaff._store import RulesetStore
    from flagstaff.engine.variants import JSONValue

logger = logging.getLogger("flagstaff")


class Reason(StrEnum):
    # The flag was evaluated: why it served what it served.
    DISABLED = "disabled"
    RULE_MATCH = "rule_match"
    FALLTHROUGH = "fallthrough"
    # The default from the calling code was returned instead.
    NOT_READY = "not_ready"
    FLAG_NOT_FOUND = "flag_not_found"
    WRONG_TYPE = "wrong_type"
    INVALID_CONTEXT = "invalid_context"


@dataclass(frozen=True, slots=True)
class FlagDetail[T]:
    value: T
    # None whenever the value is the caller's default.
    variant: str | None
    reason: Reason
    rule_id: str | None = None
    ruleset_version: int | None = None


# What both clients offer: answers from the rules held in memory, never a network call. None of
# these raise. When the flag can't be evaluated, for whatever reason, the caller's default is
# returned and the detail says why, so a missing flag never takes a request down with it.
class FlagReader:
    def __init__(self, store: RulesetStore) -> None:
        self._store = store
        self._warned: set[tuple[str, Reason]] = set()

    @property
    def is_ready(self) -> bool:
        return self._store.ruleset is not None

    @property
    def ruleset_version(self) -> int | None:
        ruleset = self._store.ruleset
        return ruleset.version if ruleset is not None else None

    def bool_value(self, flag_key: str, context: EvaluationContext | str, *, default: bool) -> bool:
        return self.bool_detail(flag_key, context, default=default).value

    def bool_detail(
        self, flag_key: str, context: EvaluationContext | str, *, default: bool
    ) -> FlagDetail[bool]:
        return self._detail(flag_key, context, default, _is_bool)

    def str_value(self, flag_key: str, context: EvaluationContext | str, *, default: str) -> str:
        return self.str_detail(flag_key, context, default=default).value

    def str_detail(
        self, flag_key: str, context: EvaluationContext | str, *, default: str
    ) -> FlagDetail[str]:
        return self._detail(flag_key, context, default, _is_str)

    def number_value(
        self, flag_key: str, context: EvaluationContext | str, *, default: float
    ) -> float:
        return self.number_detail(flag_key, context, default=default).value

    def number_detail(
        self, flag_key: str, context: EvaluationContext | str, *, default: float
    ) -> FlagDetail[float]:
        return self._detail(flag_key, context, default, _is_number)

    # A copy: the value lives in the shared ruleset, and a caller that changed it in place would
    # change it for every later evaluation in the process.
    def json_value(
        self, flag_key: str, context: EvaluationContext | str, *, default: JSONValue
    ) -> JSONValue:
        return self.json_detail(flag_key, context, default=default).value

    def json_detail(
        self, flag_key: str, context: EvaluationContext | str, *, default: JSONValue
    ) -> FlagDetail[JSONValue]:
        detail = self._detail(flag_key, context, default, _is_json)
        if detail.variant is None:
            return detail
        return FlagDetail(
            copy.deepcopy(detail.value),
            detail.variant,
            detail.reason,
            detail.rule_id,
            detail.ruleset_version,
        )

    def _detail[T](
        self,
        flag_key: str,
        context: EvaluationContext | str,
        default: T,
        accepts: Callable[[object], TypeGuard[T]],
    ) -> FlagDetail[T]:
        ruleset = self._store.ruleset
        if ruleset is None:
            return FlagDetail(default, None, Reason.NOT_READY)
        try:
            resolved = (
                context if isinstance(context, EvaluationContext) else EvaluationContext(context)
            )
        except InvalidContextError:
            return self._fall_back(flag_key, default, Reason.INVALID_CONTEXT, ruleset.version)
        evaluation = ruleset.evaluate(flag_key, resolved)
        if evaluation is None:
            return self._fall_back(flag_key, default, Reason.FLAG_NOT_FOUND, ruleset.version)
        if not accepts(evaluation.value):
            return self._fall_back(flag_key, default, Reason.WRONG_TYPE, ruleset.version)
        return FlagDetail(
            evaluation.value,
            evaluation.variant.key,
            Reason(evaluation.reason.value),
            evaluation.rule_id,
            ruleset.version,
        )

    # Logged once per flag and problem: a hot code path asking for a missing flag would
    # otherwise write a warning per request.
    def _fall_back[T](
        self, flag_key: str, default: T, reason: Reason, version: int
    ) -> FlagDetail[T]:
        if (flag_key, reason) not in self._warned:
            self._warned.add((flag_key, reason))
            logger.warning(
                "flag %r served the default because of %s",
                flag_key,
                reason.value,
                extra={"flag": flag_key, "reason": reason.value, "ruleset_version": version},
            )
        return FlagDetail(default, None, reason, None, version)


def _is_bool(value: object) -> TypeGuard[bool]:
    return isinstance(value, bool)


def _is_str(value: object) -> TypeGuard[str]:
    return isinstance(value, str)


def _is_number(value: object) -> TypeGuard[float]:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _is_json(value: object) -> TypeGuard[JSONValue]:
    return FlagKind.JSON.accepts(value)
