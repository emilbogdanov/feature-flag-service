from __future__ import annotations

import itertools
import time
from dataclasses import dataclass

from flagstaff import AsyncFlagstaffClient, EvaluationContext

from flagstaff_load.target import FLAG

# A spread of users, so every rule of the load flag gets its share: listed testers, users in
# and out of the rollout's countries and plans, and users no rule matches.
_COUNTRIES = ("BG", "DE", "FR", "US", "JP")
_PLANS = ("pro", "free")


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    calls: int
    seconds: float

    @property
    def calls_per_second(self) -> float:
        return self.calls / self.seconds

    @property
    def microseconds_per_call(self) -> float:
        return self.seconds / self.calls * 1_000_000


# Through the SDK's public API, the way an app asks: the rules are already in memory, so this is
# the whole cost of a flag check. One thread, so the figure is per core.
async def measure_evaluation(base_url: str, sdk_key: str, *, seconds: float) -> EvaluationResult:
    contexts = [
        EvaluationContext(f"user-{n}", {"country": country, "plan": plan})
        for n, (country, plan) in enumerate(itertools.product(_COUNTRIES * 100, _PLANS))
    ]
    async with AsyncFlagstaffClient(sdk_key, base_url=base_url) as flags:
        if not await flags.wait_until_ready(timeout=10):
            raise RuntimeError("the SDK did not receive its rules within 10 seconds")
        calls = 0
        started = time.perf_counter()
        while (elapsed := time.perf_counter() - started) < seconds:
            for context in contexts:
                flags.bool_value(FLAG, context, default=False)
            calls += len(contexts)
    return EvaluationResult(calls=calls, seconds=elapsed)
