from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

from flagstaff.engine.errors import InvalidFlagError
from flagstaff.engine.evaluation import Evaluation, EvaluationReason
from flagstaff.engine.keys import require_key

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from flagstaff.engine.conditions import Condition
    from flagstaff.engine.context import EvaluationContext
    from flagstaff.engine.serving import Serve
    from flagstaff.engine.variants import FlagKind, Variant


@dataclass(frozen=True, slots=True, kw_only=True)
class Rule:
    id: str
    conditions: tuple[Condition, ...]
    serve: Serve

    def __post_init__(self) -> None:
        require_key("rule", self.id)
        # Matching everyone is what the flag's fallthrough is for; a rule that does it would
        # silently shadow every rule below it.
        if not self.conditions:
            raise InvalidFlagError(f"rule {self.id!r} needs at least one condition")

    def matches(self, context: EvaluationContext) -> bool:
        return all(condition.matches(context) for condition in self.conditions)


# One flag as configured in one environment: everything needed to evaluate it, nothing else.
@dataclass(frozen=True, slots=True, kw_only=True)
class Flag:
    key: str
    kind: FlagKind
    variants: tuple[Variant, ...]
    enabled: bool
    off_variant: str
    fallthrough: Serve
    rules: tuple[Rule, ...] = ()
    _variants_by_key: Mapping[str, Variant] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        require_key("flag", self.key)
        self._check_variants()
        known = {variant.key: variant for variant in self.variants}
        self._require_known(known, {self.off_variant}, "the off variant")
        self._require_known(known, self.fallthrough.variant_keys, "the fallthrough")
        self._check_rules(known)
        object.__setattr__(self, "_variants_by_key", MappingProxyType(known))

    def evaluate(self, context: EvaluationContext) -> Evaluation:
        if not self.enabled:
            return self._serve(self.off_variant, EvaluationReason.DISABLED)
        for rule in self.rules:
            if rule.matches(context):
                variant_key = rule.serve.variant_for(self.key, context)
                return self._serve(variant_key, EvaluationReason.RULE_MATCH, rule_id=rule.id)
        variant_key = self.fallthrough.variant_for(self.key, context)
        return self._serve(variant_key, EvaluationReason.FALLTHROUGH)

    def _serve(
        self, variant_key: str, reason: EvaluationReason, *, rule_id: str | None = None
    ) -> Evaluation:
        return Evaluation(
            flag_key=self.key,
            variant=self._variants_by_key[variant_key],
            reason=reason,
            rule_id=rule_id,
        )

    def _check_variants(self) -> None:
        if not self.variants:
            raise InvalidFlagError(f"flag {self.key!r} needs at least one variant")
        repeated = _repeated(variant.key for variant in self.variants)
        if repeated:
            raise InvalidFlagError(f"flag {self.key!r} defines variants more than once: {repeated}")
        for variant in self.variants:
            if not self.kind.accepts(variant.value):
                raise InvalidFlagError(
                    f"flag {self.key!r} is a {self.kind} flag, "
                    f"but variant {variant.key!r} is {variant.value!r}"
                )

    def _check_rules(self, known: Mapping[str, Variant]) -> None:
        repeated = _repeated(rule.id for rule in self.rules)
        if repeated:
            raise InvalidFlagError(f"flag {self.key!r} has rule ids more than once: {repeated}")
        for rule in self.rules:
            self._require_known(known, rule.serve.variant_keys, f"rule {rule.id!r}")

    def _require_known(
        self, known: Mapping[str, Variant], variant_keys: Iterable[str], used_by: str
    ) -> None:
        unknown = sorted(set(variant_keys) - known.keys())
        if unknown:
            raise InvalidFlagError(
                f"{used_by} of flag {self.key!r} serves variants it doesn't define: {unknown}"
            )


def _repeated(keys: Iterable[str]) -> list[str]:
    return sorted(key for key, count in Counter(keys).items() if count > 1)
