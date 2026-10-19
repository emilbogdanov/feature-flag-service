from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from flagstaff_server.application.api_keys import hash_secret

if TYPE_CHECKING:
    from collections.abc import Callable

    from flagstaff_server.application.api_keys import ApiKeyService
    from flagstaff_server.domain.api_keys import ApiKey
    from flagstaff_server.domain.ids import ApiKeyId

# Enough for every SDK in a large deployment; past it the oldest entries make room.
DEFAULT_MAX_ENTRIES: Final = 10_000


@dataclass(frozen=True, slots=True)
class _Entry:
    key: ApiKey
    expires_at: float


# Every SDK request presents its key, and looking one up costs a database session, which is
# most of what answering a poll for unchanged rules costs. A key is remembered for ttl seconds
# once it has authenticated: revoked through this instance it stops at once, revoked through
# another it keeps working here until its entry expires. Secrets that fail are never remembered.
class AuthenticatedKeys:
    def __init__(
        self,
        keys: Callable[[], ApiKeyService],
        *,
        ttl: float,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._keys = keys
        self._ttl = ttl
        self._max_entries = max_entries
        self._clock = clock
        # By secret hash, in the order they were added, so the oldest is the first to go.
        self._entries: dict[str, _Entry] = {}

    async def authenticate(self, secret: str) -> ApiKey:
        secret_hash = hash_secret(secret)
        now = self._clock()
        entry = self._entries.get(secret_hash)
        if entry is not None and entry.expires_at > now:
            return entry.key
        key = await self._keys().authenticate(secret)
        if self._ttl > 0:
            self._entries.pop(secret_hash, None)
            if len(self._entries) >= self._max_entries:
                del self._entries[next(iter(self._entries))]
            self._entries[secret_hash] = _Entry(key, now + self._ttl)
        return key

    def forget(self, key_id: ApiKeyId) -> None:
        for secret_hash in [h for h, entry in self._entries.items() if entry.key.id == key_id]:
            del self._entries[secret_hash]
