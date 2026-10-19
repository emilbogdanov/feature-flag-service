# A project with the standard three environments, stored the way ProjectService stores one.
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from flagstaff_server.domain.ids import EnvironmentId, ProjectId
from flagstaff_server.domain.projects import STANDARD_ENVIRONMENTS, Environment, Project
from flagstaff_server.domain.values import Name, Slug
from flagstaff_server.infrastructure.db.projects import (
    SqlEnvironmentRepository,
    SqlProjectRepository,
)

CREATED_AT = datetime(2026, 10, 19, 9, 30, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class Storefront:
    project: Project
    dev: Environment
    staging: Environment
    prod: Environment


async def store_storefront(sessions: async_sessionmaker[AsyncSession]) -> Storefront:
    project = Project(
        id=ProjectId(uuid4()),
        key=Slug("storefront"),
        name=Name("Storefront"),
        created_at=CREATED_AT,
    )
    dev, staging, prod = (
        Environment(
            id=EnvironmentId(uuid4()),
            project_id=project.id,
            key=key,
            name=name,
            created_at=CREATED_AT,
        )
        for key, name in STANDARD_ENVIRONMENTS
    )
    async with sessions() as session:
        await SqlProjectRepository(session).add(project)
        for environment in (dev, staging, prod):
            await SqlEnvironmentRepository(session).add(environment)
        await session.commit()
    return Storefront(project, dev, staging, prod)
