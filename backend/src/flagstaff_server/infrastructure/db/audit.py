from __future__ import annotations

from typing import TYPE_CHECKING

from flagstaff_server.infrastructure.db.tables import AuditEntryRow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from flagstaff_server.domain.audit import AuditEntry


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
