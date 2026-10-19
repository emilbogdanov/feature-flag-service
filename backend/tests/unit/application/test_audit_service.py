from datetime import UTC, datetime, timedelta

import pytest

from flagstaff_server.application.api_keys import ApiKeyService
from flagstaff_server.application.audit import AuditService
from flagstaff_server.application.projects import ProjectService
from flagstaff_server.domain.audit import Actor, AuditAction
from flagstaff_server.domain.errors import ProjectNotFoundError
from flagstaff_server.domain.values import Name, Slug
from tests.unit.application.fakes import FakeUnitOfWork, FixedClock

NOW = datetime(2026, 10, 19, 9, 30, tzinfo=UTC)
CLI = Actor.command_line()


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture
def service(uow: FakeUnitOfWork) -> AuditService:
    return AuditService(uow)


@pytest.fixture(autouse=True)
async def history(uow: FakeUnitOfWork, clock: FixedClock) -> None:
    projects = ProjectService(uow, clock)
    await projects.create_project(CLI, key=Slug("storefront"), name=Name("Storefront"))
    clock.advance(timedelta(minutes=1))
    await projects.create_project(CLI, key=Slug("back-office"), name=Name("Back office"))
    clock.advance(timedelta(minutes=1))
    for name in ["eu-canary", "us-canary", "apac-canary"]:
        await projects.add_environment(CLI, Slug("storefront"), key=Slug(name), name=Name(name))
    # Same instant as the last environment: the id has to break the tie.
    await ApiKeyService(uow, clock).issue_admin_key(CLI, name=Name("Release tooling"))


async def test_pages_through_everything_newest_first(service: AuditService) -> None:
    subjects: list[str] = []
    cursor = None
    while True:
        page = await service.list_entries(after=cursor, limit=2)
        subjects += [entry.subject for entry in page.entries]
        if page.next_cursor is None:
            break
        cursor = page.next_cursor

    assert len(subjects) == 6
    assert subjects[-2:] == ["back-office", "storefront"]
    assert set(subjects[:4]) == {"eu-canary", "us-canary", "apac-canary", "Release tooling"}


async def test_filters_by_project(service: AuditService) -> None:
    page = await service.list_entries(project_key=Slug("storefront"), limit=10)

    assert [entry.action for entry in page.entries][-1] is AuditAction.PROJECT_CREATED
    assert {entry.subject for entry in page.entries} == {
        "storefront",
        "eu-canary",
        "us-canary",
        "apac-canary",
    }
    assert page.next_cursor is None


async def test_a_full_last_page_has_no_next_cursor(service: AuditService) -> None:
    page = await service.list_entries(limit=6)

    assert len(page.entries) == 6
    assert page.next_cursor is None


async def test_needs_an_existing_project(service: AuditService) -> None:
    with pytest.raises(ProjectNotFoundError):
        await service.list_entries(project_key=Slug("billing"), limit=10)


@pytest.mark.parametrize("limit", [0, 101])
async def test_page_size_is_bounded(service: AuditService, limit: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 100"):
        await service.list_entries(limit=limit)
