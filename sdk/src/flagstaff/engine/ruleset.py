from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

from flagstaff.engine.errors import InvalidFlagError

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from flagstaff.engine.context import EvaluationContext
    from flagstaff.engine.evaluation import Evaluation
    from flagstaff.engine.flag import Flag


# Every flag of one environment as of one ruleset version: what an SDK downloads and evaluates
# against until the server says the version has moved on.
@dataclass(frozen=True, slots=True)
class Ruleset:
    version: int
    flags: Mapping[str, Flag] = field(default_factory=dict, hash=False)

    def __post_init__(self) -> None:
        if self.version < 0:
            raise InvalidFlagError(f"ruleset version {self.version} is negative")
        object.__setattr__(self, "flags", MappingProxyType(dict(self.flags)))

    @classmethod
    def of(cls, version: int, flags: Iterable[Flag]) -> Ruleset:
        flags = list(flags)
        repeated = sorted(key for key, count in Counter(f.key for f in flags).items() if count > 1)
        if repeated:
            raise InvalidFlagError(f"ruleset has flags more than once: {repeated}")
        return cls(version, {flag.key: flag for flag in flags})

    # None for a flag the ruleset doesn't have, so the caller decides what an unknown flag
    # means: an SDK falls back to the default in the code, the server answers 404.
    def evaluate(self, flag_key: str, context: EvaluationContext) -> Evaluation | None:
        flag = self.flags.get(flag_key)
        return flag.evaluate(context) if flag is not None else None
