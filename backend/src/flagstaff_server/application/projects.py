from uuid import uuid4

from flagstaff_server.application.audit import audit_entry
from flagstaff_server.application.lookups import require_project
from flagstaff_server.application.ports import Clock, UnitOfWork
from flagstaff_server.domain.audit import Actor, AuditAction
from flagstaff_server.domain.errors import EnvironmentKeyTakenError, ProjectKeyTakenError
from flagstaff_server.domain.ids import EnvironmentId, ProjectId
from flagstaff_server.domain.projects import STANDARD_ENVIRONMENTS, Environment, Project
from flagstaff_server.domain.values import Name, Slug


class ProjectService:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    async def create_project(self, actor: Actor, *, key: Slug, name: Name) -> Project:
        now = self._clock.now()
        project = Project(id=ProjectId(uuid4()), key=key, name=name, created_at=now)
        environments = [
            Environment(
                id=EnvironmentId(uuid4()),
                project_id=project.id,
                key=environment_key,
                name=environment_name,
                created_at=now,
            )
            for environment_key, environment_name in STANDARD_ENVIRONMENTS
        ]
        async with self._uow as uow:
            if await uow.projects.get_by_key(key) is not None:
                raise ProjectKeyTakenError(key)
            await uow.projects.add(project)
            for environment in environments:
                await uow.environments.add(environment)
            await uow.audit.add(
                audit_entry(
                    AuditAction.PROJECT_CREATED,
                    actor=actor,
                    at=now,
                    subject=str(key),
                    project_id=project.id,
                    changes={
                        "name": str(name),
                        "environments": [str(environment.key) for environment in environments],
                    },
                )
            )
            await uow.commit()
        return project

    async def add_environment(
        self, actor: Actor, project_key: Slug, *, key: Slug, name: Name
    ) -> Environment:
        now = self._clock.now()
        async with self._uow as uow:
            project = await require_project(uow, project_key)
            if await uow.environments.get_by_key(project.id, key) is not None:
                raise EnvironmentKeyTakenError(project_key, key)
            environment = Environment(
                id=EnvironmentId(uuid4()), project_id=project.id, key=key, name=name, created_at=now
            )
            await uow.environments.add(environment)
            await uow.audit.add(
                audit_entry(
                    AuditAction.ENVIRONMENT_CREATED,
                    actor=actor,
                    at=now,
                    subject=str(key),
                    project_id=project.id,
                    environment_id=environment.id,
                    changes={"name": str(name)},
                )
            )
            await uow.commit()
        return environment

    async def get_project(self, key: Slug) -> Project:
        async with self._uow as uow:
            return await require_project(uow, key)

    async def list_projects(self) -> list[Project]:
        async with self._uow as uow:
            return await uow.projects.list()

    async def list_environments(self, project_key: Slug) -> list[Environment]:
        async with self._uow as uow:
            project = await require_project(uow, project_key)
            return await uow.environments.list_for_project(project.id)
