from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from flagstaff_server.api.schemas.common import Request
from flagstaff_server.application.api_keys import IssuedApiKey, ScopedApiKey
from flagstaff_server.domain.api_keys import ApiKeyKind


class IssueApiKey(Request):
    kind: ApiKeyKind
    name: str = Field(description="Who or what uses the key, such as checkout-api.")
    project: str | None = Field(default=None, description="For an SDK key only.")
    environment: str | None = Field(default=None, description="For an SDK key only.")


class ApiKeyResponse(BaseModel):
    id: UUID
    kind: ApiKeyKind
    name: str
    project: str | None
    environment: str | None
    created_at: datetime
    revoked_at: datetime | None

    @classmethod
    def of(cls, scoped: ScopedApiKey) -> Self:
        key = scoped.key
        return cls(
            id=key.id,
            kind=key.kind,
            name=str(key.name),
            project=str(scoped.project.key) if scoped.project else None,
            environment=str(scoped.environment.key) if scoped.environment else None,
            created_at=key.created_at,
            revoked_at=key.revoked_at,
        )


class IssuedApiKeyResponse(ApiKeyResponse):
    secret: str = Field(description="Shown this once; only a hash of it is stored.")

    @classmethod
    def issued(cls, issued: IssuedApiKey) -> Self:
        return cls(**ApiKeyResponse.of(issued.scoped).model_dump(), secret=issued.secret)
