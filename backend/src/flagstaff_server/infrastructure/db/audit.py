from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select, tuple_

from flagstaff_server.domain.audit import Actor, AuditEntry
from flagstaff_server.domain.ids import ApiKeyId, AuditEntryId, EnvironmentId, ProjectId
from flagstaff_server.infrastructure.db.tables import AuditEntryRow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from flagstaff_server.application.audit import AuditCursor


class SqlAuditLog:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entry: AuditEntry) -> None:
        self._session.add(
            AuditEntryRow(
                id=entry.id,
                action=entry.action,
                actor_key_id=entry.actor.api_key_id,
                actor_name=entry.actor.name,
                at=entry.at,
                project_id=entry.project_id,
                environment_id=entry.environment_id,
                subject=entry.subject,
                changes=dict(entry.changes),
            )
        )

    async def page(
        self, *, project_id: ProjectId | None, after: AuditCursor | None, limit: int
    ) -> list[AuditEntry]:
        statement = (
            select(AuditEntryRow)
            .order_by(AuditEntryRow.at.desc(), AuditEntryRow.id.desc())
            .limit(limit)
        )
        if project_id is not None:
            statement = statement.where(AuditEntryRow.project_id == project_id)
        if after is not None:
            # A row comparison, so the index range starts at the cursor instead of the query
            # filtering rows one by one.
            statement = statement.where(
                tuple_(AuditEntryRow.at, AuditEntryRow.id) < tuple_(after.at, after.entry_id)
            )
        return [_to_entry(row) for row in await self._session.scalars(statement)]


def _to_entry(row: AuditEntryRow) -> AuditEntry:
    return AuditEntry(
        id=AuditEntryId(row.id),
        action=row.action,
        actor=Actor(
            ApiKeyId(row.actor_key_id) if row.actor_key_id else None,
            row.actor_name,
        ),
        at=row.at,
        project_id=ProjectId(row.project_id) if row.project_id else None,
        environment_id=EnvironmentId(row.environment_id) if row.environment_id else None,
        subject=row.subject,
        changes=row.changes,
    )
