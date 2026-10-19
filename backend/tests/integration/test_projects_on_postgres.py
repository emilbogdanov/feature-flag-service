import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from flagstaff_server.domain.errors import EnvironmentKeyTakenError, ProjectKeyTakenError
from flagstaff_server.domain.ids import EnvironmentId, ProjectId
from flagstaff_server.domain.projects import STANDARD_ENVIRONMENTS, Environment, Project
from flagstaff_server.domain.values import Name, Slug
from flagstaff_server.infrastructure.db.projects import (
    SqlEnvironmentRepository,
    SqlProjectRepository,
)

CREATED_AT = datetime(2026, 10, 19, 9, 30, tzinfo=UTC)


def project(key: str = "storefront") -> Project:
    return Project(
        id=ProjectId(uuid4()), key=Slug(key), name=Name(key.title()), created_at=CREATED_AT
    )


def environment(owner: Project, key: str, name: str = "Production") -> Environment:
    return Environment(
        id=EnvironmentId(uuid4()),
        project_id=owner.id,
        key=Slug(key),
        name=Name(name),
        created_at=CREATED_AT,
    )


async def test_stores_and_lists_projects_by_key(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        projects = SqlProjectRepository(session)
        for key in ["storefront", "back-office", "mobile-app"]:
            await projects.add(project(key))
        await session.commit()

    async with session_factory() as session:
        projects = SqlProjectRepository(session)
        listed = await projects.list()
        found = await projects.get_by_key(Slug("storefront"))
        missing = await projects.get_by_key(Slug("billing"))

    assert [str(p.key) for p in listed] == ["back-office", "mobile-app", "storefront"]
    assert found is not None
    assert (found.name, found.created_at) == (Name("Storefront"), CREATED_AT)
    assert missing is None


async def test_two_creates_racing_for_one_key_leave_one_project(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def create() -> None:
        async with session_factory() as session:
            await SqlProjectRepository(session).add(project())
            await asyncio.sleep(0.05)
            await session.commit()

    results = await asyncio.gather(create(), create(), return_exceptions=True)

    assert sorted(type(result).__name__ for result in results) == [
        "NoneType",
        "ProjectKeyTakenError",
    ]
    async with session_factory() as session:
        assert len(await SqlProjectRepository(session).list()) == 1


async def test_environments_keep_the_order_they_were_created_in(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner = project()
    async with session_factory() as session:
        await SqlProjectRepository(session).add(owner)
        environments = SqlEnvironmentRepository(session)
        for key, name in STANDARD_ENVIRONMENTS:
            await environments.add(environment(owner, str(key), str(name)))
        await environments.add(environment(owner, "eu-canary", "EU canary"))
        await session.commit()

    async with session_factory() as session:
        listed = await SqlEnvironmentRepository(session).list_for_project(owner.id)

    assert [str(e.key) for e in listed] == ["dev", "staging", "prod", "eu-canary"]


async def test_environment_keys_are_unique_per_project(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    storefront, back_office = project("storefront"), project("back-office")
    async with session_factory() as session:
        projects, environments = SqlProjectRepository(session), SqlEnvironmentRepository(session)
        await projects.add(storefront)
        await projects.add(back_office)
        await environments.add(environment(storefront, "prod"))
        await environments.add(environment(back_office, "prod"))

        with pytest.raises(EnvironmentKeyTakenError, match="'storefront' already has"):
            await environments.add(environment(storefront, "prod"))


async def test_duplicate_project_keys_are_refused(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        projects = SqlProjectRepository(session)
        await projects.add(project())

        with pytest.raises(ProjectKeyTakenError):
            await projects.add(project())


async def test_concurrent_bumps_each_move_the_ruleset_version_on(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner = project()
    prod, dev = environment(owner, "prod"), environment(owner, "dev", "Development")
    async with session_factory() as session:
        await SqlProjectRepository(session).add(owner)
        await SqlEnvironmentRepository(session).add(prod)
        await SqlEnvironmentRepository(session).add(dev)
        await session.commit()

    async def bump() -> None:
        async with session_factory() as session:
            await SqlEnvironmentRepository(session).bump_ruleset_versions([prod.id])
            await session.commit()

    await asyncio.gather(*(bump() for _ in range(20)))

    async with session_factory() as session:
        environments = SqlEnvironmentRepository(session)
        stored_prod, stored_dev = await environments.get(prod.id), await environments.get(dev.id)
    assert stored_prod is not None
    assert stored_dev is not None
    assert (stored_prod.ruleset_version, stored_dev.ruleset_version) == (20, 0)


async def test_a_bump_shows_up_in_the_same_transaction(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner = project()
    prod = environment(owner, "prod")
    async with session_factory() as session:
        await SqlProjectRepository(session).add(owner)
        environments = SqlEnvironmentRepository(session)
        await environments.add(prod)
        assert (await environments.get(prod.id)) is not None

        assert await environments.bump_ruleset_versions([prod.id]) == {prod.id: 1}

        stored = await environments.get_by_key(owner.id, Slug("prod"))
        assert stored is not None
        assert stored.ruleset_version == 1
