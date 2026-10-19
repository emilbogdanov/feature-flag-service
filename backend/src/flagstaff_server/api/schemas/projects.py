from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field

from flagstaff_server.api.schemas.common import Request
from flagstaff_server.domain.projects import Environment, Project

_KEY_DESCRIPTION = "Lowercase letters, digits and hyphens. Fixed once created."


class CreateProject(Request):
    key: str = Field(description=_KEY_DESCRIPTION)
    name: str


class ProjectResponse(BaseModel):
    key: str
    name: str
    created_at: datetime

    @classmethod
    def of(cls, project: Project) -> Self:
        return cls(key=str(project.key), name=str(project.name), created_at=project.created_at)


class CreateEnvironment(Request):
    key: str = Field(description=_KEY_DESCRIPTION)
    name: str


class EnvironmentResponse(BaseModel):
    key: str
    name: str
    created_at: datetime
    ruleset_version: int = Field(
        description="Moves on with every change to what SDKs in this environment evaluate."
    )

    @classmethod
    def of(cls, environment: Environment) -> Self:
        return cls(
            key=str(environment.key),
            name=str(environment.name),
            created_at=environment.created_at,
            ruleset_version=environment.ruleset_version,
        )
