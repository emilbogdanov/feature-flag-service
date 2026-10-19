from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flagstaff_server.domain.ids import ApiKeyId


class ApplicationError(Exception):
    pass


# The flag changed since the caller read it. Raised when the caller's version is already behind,
# and by the repository when another change commits first.
class StaleFlagError(ApplicationError):
    def __init__(self, key: str, *, expected: int, actual: int | None = None) -> None:
        found = f", it is at {actual}" if actual is not None else ""
        super().__init__(f"flag {key!r} is no longer at version {expected}{found}")
        self.key = key
        self.expected = expected
        self.actual = actual


# Also raised for a revoked key, so the response doesn't confirm that a leaked key once worked.
class InvalidApiKeyError(ApplicationError):
    def __init__(self) -> None:
        super().__init__("API key is missing, unknown or revoked")


# The key is real and active but not allowed to do this, such as an SDK key on an admin route.
class PermissionDeniedError(ApplicationError):
    pass


class ApiKeyNotFoundError(ApplicationError):
    def __init__(self, key_id: ApiKeyId) -> None:
        super().__init__(f"API key {key_id} does not exist")
        self.key_id = key_id


# The connection that carries ruleset changes between API instances dropped. Raised by the feed
# so its listener can resubscribe; changes missed meanwhile are caught by the next resync.
class ChangeFeedLostError(ApplicationError):
    pass


# The feed couldn't subscribe at all, which is what every attempt sees while Redis is down.
class ChangeFeedUnavailableError(ChangeFeedLostError):
    pass
