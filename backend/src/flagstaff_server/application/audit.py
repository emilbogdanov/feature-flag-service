from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from uuid import uuid4

from flagstaff_server.application.lookups import require_project
from flagstaff_server.domain.audit import AuditEntry
from flagstaff_server.domain.ids import AuditEntryId

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from flagstaff.engine.variants import JSONValue

    from flagstaff_server.application.ports import UnitOfWork
    from flagstaff_server.domain.audit import Actor, AuditAction
    from flagstaff_server.domain.ids import EnvironmentId, ProjectId
    from flagstaff_server.domain.values import Slug

MAX_PAGE_SIZE: Final = 100


# Where a page of the log ended. Entries are ordered by time with the id breaking ties, so the
# next page starts strictly after this pair even when many entries share a timestamp.
@dataclass(frozen=True, slots=True)
class AuditCursor:
    at: datetime
    entry_id: AuditEntryId


@dataclass(frozen=True, slots=True)
class AuditPage:
    entries: list[AuditEntry]
    # None on the last page.
    next_cursor: AuditCursor | None


class AuditService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    # Newest first. Without a project it pages through everything, including key changes,
    # which belong to no project.
    async def list_entries(
        self, *, project_key: Slug | None = None, after: AuditCursor | None = None, limit: int
    ) -> AuditPage:
        if not 1 <= limit <= MAX_PAGE_SIZE:
            raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}, not {limit}")
        async with self._uow as uow:
            project_id = (await require_project(uow, project_key)).id if project_key else None
            # One extra entry says whether another page exists without a COUNT query.
            entries = await uow.audit.page(project_id=project_id, after=after, limit=limit + 1)
        if len(entries) <= limit:
            return AuditPage(entries, next_cursor=None)
        last = entries[limit - 1]
        return AuditPage(entries[:limit], next_cursor=AuditCursor(last.at, last.id))


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
