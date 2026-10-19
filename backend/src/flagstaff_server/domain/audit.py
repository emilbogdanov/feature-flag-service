from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from flagstaff.engine.variants import JSONValue

    from flagstaff_server.domain.api_keys import ApiKey
    from flagstaff_server.domain.ids import ApiKeyId, AuditEntryId, EnvironmentId, ProjectId


class AuditAction(StrEnum):
    PROJECT_CREATED = "project.created"
    ENVIRONMENT_CREATED = "environment.created"
    FLAG_CREATED = "flag.created"
    FLAG_DETAILS_CHANGED = "flag.details_changed"
    FLAG_VARIANTS_CHANGED = "flag.variants_changed"
    FLAG_TARGETING_CHANGED = "flag.targeting_changed"
    FLAG_ENABLED = "flag.enabled"
    FLAG_DISABLED = "flag.disabled"
    FLAG_ARCHIVED = "flag.archived"
    API_KEY_ISSUED = "api_key.issued"
    API_KEY_REVOKED = "api_key.revoked"


# Who made a change. The key's name is copied in, so the entry still says who it was after the
# key is revoked or renamed.
@dataclass(frozen=True, slots=True)
class Actor:
    api_key_id: ApiKeyId | None
    name: str

    @classmethod
    def of(cls, key: ApiKey) -> Actor:
        return cls(key.id, str(key.name))

    # For changes made with the server's own CLI, such as the first admin key, which no key
    # could have made.
    @classmethod
    def command_line(cls) -> Actor:
        return cls(None, "command line")


@dataclass(frozen=True, slots=True, kw_only=True)
class AuditEntry:
    id: AuditEntryId
    action: AuditAction
    actor: Actor
    at: datetime
    project_id: ProjectId | None
    environment_id: EnvironmentId | None
    # What the action was done to, in the words a person would search for: a flag key, an
    # environment key, a key's name.
    subject: str
    # Before and after values of whatever the action changed, as JSON.
    changes: Mapping[str, JSONValue] = field(default_factory=dict)
