from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, slots=True)
class Summary:
    count: int
    p50: float
    p95: float
    p99: float
    max: float

    @classmethod
    def of(cls, samples: Sequence[float]) -> Summary:
        if not samples:
            raise ValueError("there are no samples to summarise")
        ordered = sorted(samples)
        return cls(
            count=len(ordered),
            p50=_nearest_rank(ordered, 0.50),
            p95=_nearest_rank(ordered, 0.95),
            p99=_nearest_rank(ordered, 0.99),
            max=ordered[-1],
        )


# Nearest rank: always a value that was actually measured, never one interpolated between two.
def _nearest_rank(ordered: Sequence[float], quantile: float) -> float:
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]
