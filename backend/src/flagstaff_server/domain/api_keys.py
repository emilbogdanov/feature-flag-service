from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from flagstaff_server.domain.errors import InvalidValueError

if TYPE_CHECKING:
    from datetime import datetime

    from flagstaff_server.domain.ids import ApiKeyId, EnvironmentId
    from flagstaff_server.domain.values import Name


class ApiKeyKind(StrEnum):
    # Manages every project, flag and key. Belongs in an operator's tooling, never in an app.
    ADMIN = "admin"
    # Reads one environment's rules. This is the key a server-side app ships with.
    SDK = "sdk"


class ApiKey:
    def __init__(
        self,
        *,
        key_id: ApiKeyId,
        kind: ApiKeyKind,
        name: Name,
        environment_id: EnvironmentId | None,
        created_at: datetime,
        revoked_at: datetime | None = None,
    ) -> None:
        if (kind is ApiKeyKind.SDK) != (environment_id is not None):
            raise InvalidValueError(
                "an SDK key belongs to exactly one environment, an admin key to none"
            )
        self._id = key_id
        self._kind = kind
        self._name = name
        self._environment_id = environment_id
        self._created_at = created_at
        self._revoked_at = revoked_at

    @classmethod
    def admin(cls, *, key_id: ApiKeyId, name: Name, at: datetime) -> ApiKey:
        return cls(
            key_id=key_id, kind=ApiKeyKind.ADMIN, name=name, environment_id=None, created_at=at
        )

    @classmethod
    def sdk(
        cls, *, key_id: ApiKeyId, name: Name, environment_id: EnvironmentId, at: datetime
    ) -> ApiKey:
        return cls(
            key_id=key_id,
            kind=ApiKeyKind.SDK,
            name=name,
            environment_id=environment_id,
            created_at=at,
        )

    @property
    def id(self) -> ApiKeyId:
        return self._id

    @property
    def kind(self) -> ApiKeyKind:
        return self._kind

    @property
    def name(self) -> Name:
        return self._name

    @property
    def environment_id(self) -> EnvironmentId | None:
        return self._environment_id

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def revoked_at(self) -> datetime | None:
        return self._revoked_at

    @property
    def is_active(self) -> bool:
        return self._revoked_at is None

    @property
    def can_manage(self) -> bool:
        return self.is_active and self._kind is ApiKeyKind.ADMIN

    # Admin keys can read any environment's rules, which is what the dashboard needs to preview
    # an evaluation; an SDK key can read only its own.
    def can_read(self, environment_id: EnvironmentId) -> bool:
        if not self.is_active:
            return False
        return self._kind is ApiKeyKind.ADMIN or self._environment_id == environment_id

    # Returns whether the key was still active, so revoking twice leaves one audit entry.
    def revoke(self, *, at: datetime) -> bool:
        if not self.is_active:
            return False
        self._revoked_at = at
        return True
