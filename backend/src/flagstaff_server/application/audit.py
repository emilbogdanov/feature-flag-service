from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from flagstaff_server.domain.audit import AuditEntry
from flagstaff_server.domain.ids import AuditEntryId

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from flagstaff.engine.variants import JSONValue

    from flagstaff_server.domain.audit import Actor, AuditAction
    from flagstaff_server.domain.ids import EnvironmentId, ProjectId


def audit_entry(
    action: AuditAction,
    *,
    actor: Actor,
    at: datetime,
    subject: str,
    project_id: ProjectId | None = None,
    environment_id: EnvironmentId | None = None,
    changes: Mapping[str, JSONValue] | None = None,
) -> AuditEntry:
    return AuditEntry(
        id=AuditEntryId(uuid4()),
        action=action,
        actor=actor,
        at=at,
        project_id=project_id,
        environment_id=environment_id,
        subject=subject,
        changes=dict(changes or {}),
    )
