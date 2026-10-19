from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, JsonValue

from flagstaff_server.application.audit import AuditPage
from flagstaff_server.domain.audit import AuditAction, AuditEntry


class ActorResponse(BaseModel):
    api_key_id: UUID | None = Field(description="None for changes made with the server's CLI.")
    name: str


class AuditEntryResponse(BaseModel):
    id: UUID
    action: AuditAction
    actor: ActorResponse
    at: datetime
    project: str | None
    environment: str | None
    subject: str
    changes: dict[str, JsonValue]

    @classmethod
    def of(cls, entry: AuditEntry, page: AuditPage) -> Self:
        project = page.projects.get(entry.project_id) if entry.project_id else None
        environment = page.environments.get(entry.environment_id) if entry.environment_id else None
        return cls(
            id=entry.id,
            action=entry.action,
            actor=ActorResponse(api_key_id=entry.actor.api_key_id, name=entry.actor.name),
            at=entry.at,
            project=str(project.key) if project else None,
            environment=str(environment.key) if environment else None,
            subject=entry.subject,
            changes=dict(entry.changes),
        )


class AuditPageResponse(BaseModel):
    entries: list[AuditEntryResponse]
    next_cursor: str | None = Field(
        description="Pass as cursor for the next page; null on the last."
    )
