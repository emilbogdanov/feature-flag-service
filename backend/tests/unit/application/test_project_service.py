from datetime import UTC, datetime

import pytest

from flagstaff_server.application.projects import ProjectService
from flagstaff_server.domain.audit import Actor, AuditAction
from flagstaff_server.domain.errors import (
    EnvironmentKeyTakenError,
    ProjectKeyTakenError,
    ProjectNotFoundError,
)
from flagstaff_server.domain.values import Name, Slug
from tests.unit.application.fakes import FakeUnitOfWork, FixedClock

NOW = datetime(2026, 10, 19, 9, 30, tzinfo=UTC)
ACTOR = Actor.command_line()
STOREFRONT = Slug("storefront")


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def service(uow: FakeUnitOfWork) -> ProjectService:
    return ProjectService(uow, FixedClock(NOW))


async def test_a_new_project_gets_dev_staging_and_prod(service: ProjectService) -> None:
    project = await service.create_project(ACTOR, key=STOREFRONT, name=Name("Storefront"))

    environments = await service.list_environments(STOREFRONT)

    assert await service.get_project(STOREFRONT) == project
    assert [(str(e.key), str(e.name)) for e in environments] == [
        ("dev", "Development"),
        ("staging", "Staging"),
        ("prod", "Production"),
    ]
    assert all(e.project_id == project.id and e.ruleset_version == 0 for e in environments)


async def test_creating_a_project_is_audited(service: ProjectService, uow: FakeUnitOfWork) -> None:
    project = await service.create_project(ACTOR, key=STOREFRONT, name=Name("Storefront"))

    [entry] = uow.committed.audit
    assert entry.action is AuditAction.PROJECT_CREATED
    assert entry.actor == ACTOR
    assert entry.at == NOW
    assert entry.project_id == project.id
    assert entry.subject == "storefront"
    assert entry.changes == {"name": "Storefront", "environments": ["dev", "staging", "prod"]}


async def test_project_keys_are_unique(service: ProjectService, uow: FakeUnitOfWork) -> None:
    await service.create_project(ACTOR, key=STOREFRONT, name=Name("Storefront"))

    with pytest.raises(ProjectKeyTakenError, match="storefront"):
        await service.create_project(ACTOR, key=STOREFRONT, name=Name("Storefront again"))

    assert len(uow.committed.projects) == 1
    assert len(uow.committed.environments) == 3


async def test_projects_are_listed_by_key(service: ProjectService) -> None:
    for key in ["storefront", "back-office", "mobile-app"]:
        await service.create_project(ACTOR, key=Slug(key), name=Name(key.title()))

    projects = await service.list_projects()

    assert [str(project.key) for project in projects] == ["back-office", "mobile-app", "storefront"]


async def test_adds_an_environment_to_a_project(
    service: ProjectService, uow: FakeUnitOfWork
) -> None:
    await service.create_project(ACTOR, key=STOREFRONT, name=Name("Storefront"))

    environment = await service.add_environment(
        ACTOR, STOREFRONT, key=Slug("eu-canary"), name=Name("EU canary")
    )

    assert (await service.list_environments(STOREFRONT))[-1] == environment
    assert uow.committed.audit[-1].action is AuditAction.ENVIRONMENT_CREATED
    assert uow.committed.audit[-1].environment_id == environment.id


async def test_environment_keys_are_unique_within_a_project(service: ProjectService) -> None:
    await service.create_project(ACTOR, key=STOREFRONT, name=Name("Storefront"))
    await service.create_project(ACTOR, key=Slug("back-office"), name=Name("Back office"))

    with pytest.raises(EnvironmentKeyTakenError, match="'storefront' already has an environment"):
        await service.add_environment(ACTOR, STOREFRONT, key=Slug("prod"), name=Name("Prod 2"))
    other = await service.add_environment(
        ACTOR, Slug("back-office"), key=Slug("eu-canary"), name=Name("EU canary")
    )
    assert other.key == Slug("eu-canary")


async def test_unknown_projects_are_reported_by_key(service: ProjectService) -> None:
    with pytest.raises(ProjectNotFoundError, match="'storefront'"):
        await service.list_environments(STOREFRONT)
    with pytest.raises(ProjectNotFoundError):
        await service.add_environment(ACTOR, STOREFRONT, key=Slug("qa"), name=Name("QA"))
