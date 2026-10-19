from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flagstaff.engine.variants import JSONValue, Variant


class EvaluationReason(StrEnum):
    DISABLED = "disabled"
    RULE_MATCH = "rule_match"
    FALLTHROUGH = "fallthrough"


@dataclass(frozen=True, slots=True, kw_only=True)
class Evaluation:
    flag_key: str
    variant: Variant
    reason: EvaluationReason
    # Set only for RULE_MATCH, so "why did I get this?" can point at the rule.
    rule_id: str | None = None

    @property
    def value(self) -> JSONValue:
        return self.variant.value
