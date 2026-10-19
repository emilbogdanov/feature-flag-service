import random
from collections.abc import Callable


# Exponential with full jitter: after a server restart thousands of SDKs reconnect, and a
# random wait anywhere up to the ceiling spreads them out instead of letting them arrive in
# synchronised waves.
class Backoff:
    def __init__(
        self,
        *,
        base_seconds: float = 0.5,
        max_seconds: float = 30.0,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._base = base_seconds
        self._max = max_seconds
        self._jitter = jitter
        self._attempt = 0

    def next_delay(self) -> float:
        ceiling = min(self._max, self._base * 2.0**self._attempt)
        self._attempt = min(self._attempt + 1, 32)
        return self._jitter() * ceiling

    def reset(self) -> None:
        self._attempt = 0
