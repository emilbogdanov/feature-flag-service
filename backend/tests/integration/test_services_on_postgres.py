from datetime import UTC, datetime

import pytest
from flagstaff.engine.conditions import UserListCondition
from flagstaff.engine.context import EvaluationContext
from flagstaff.engine.flag import Rule
from flagstaff.engine.serving import FixedVariant
from flagstaff.engine.variants import FlagKind, Variant
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from flagstaff_server.application.api_keys import ApiKeyService
from flagstaff_server.application.flags import FlagService
from flagstaff_server.application.projects import ProjectService
from flagstaff_server.domain.audit import Actor, AuditAction
from flagstaff_server.domain.errors import ProjectKeyTakenError
from flagstaff_server.domain.flags import Targeting
from flagstaff_server.domain.values import Description, Name, Slug
from flagstaff_server.infrastructure.db.tables import AuditEntryRow
from flagstaff_server.infrastructure.db.unit_of_work import SqlUnitOfWork
from tests.unit.application.fakes import FixedClock

NOW = datetime(2026, 10, 19, 9, 30, tzinfo=UTC)
CLI = Actor.command_line()
STOREFRONT = Slug("storefront")
PROD = Slug("prod")


@pytest.fixture
def uow(session_factory: async_sessionmaker[AsyncSession]) -> SqlUnitOfWork:
    return SqlUnitOfWork(session_factory)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


async def test_a_flag_goes_from_created_to_targeted_in_prod(
    uow: SqlUnitOfWork, clock: FixedClock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await ProjectService(uow, clock).create_project(CLI, key=STOREFRONT, name=Name("Storefront"))
    flags = FlagService(uow, clock)
    await flags.create_flag(
        CLI,
        STOREFRONT,
        key="new-checkout",
        name=Name("New checkout"),
        description=Description("Two-step checkout with saved cards"),
        kind=FlagKind.BOOLEAN,
        variants=(Variant("on", value=True), Variant("off", value=False)),
        off_variant="off",
        on_variant="on",
    )
    targeting = Targeting(
        enabled=True,
        off_variant="off",
        fallthrough=FixedVariant("off"),
        rules=(
            Rule(
                id="beta-testers",
                conditions=(UserListCondition(frozenset({"user-7"})),),
                serve=FixedVariant("on"),
            ),
        ),
    )

    await flags.change_targeting(
        CLI, STOREFRONT, "new-checkout", PROD, targeting=targeting, expected_version=1
    )

    flag = await flags.get_flag(STOREFRONT, "new-checkout")
    environments = {
        str(e.key): e for e in await ProjectService(uow, clock).list_environments(STOREFRONT)
    }
    compiled = flag.compile_for(environments["prod"].id)
    assert flag.version == 2
    assert compiled.evaluate(EvaluationContext("user-7")).value is True
    assert compiled.evaluate(EvaluationContext("user-8")).value is False
    assert {key: e.ruleset_version for key, e in environments.items()} == {
        "dev": 1,
        "staging": 1,
        "prod": 2,
    }
    async with session_factory() as session:
        actions = (
            await session.scalars(select(AuditEntryRow.action).order_by(AuditEntryRow.at))
        ).all()
    assert sorted(actions) == sorted(
        [AuditAction.PROJECT_CREATED, AuditAction.FLAG_CREATED, AuditAction.FLAG_TARGETING_CHANGED]
    )


async def test_a_refused_change_leaves_nothing_behind(
    uow: SqlUnitOfWork, clock: FixedClock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    projects = ProjectService(uow, clock)
    await projects.create_project(CLI, key=STOREFRONT, name=Name("Storefront"))

    with pytest.raises(ProjectKeyTakenError):
        await projects.create_project(CLI, key=STOREFRONT, name=Name("Storefront again"))

    assert [str(e.key) for e in await projects.list_environments(STOREFRONT)] == [
        "dev",
        "staging",
        "prod",
    ]
    async with session_factory() as session:
        entries = (await session.scalars(select(AuditEntryRow))).all()
    assert len(entries) == 1


async def test_an_issued_key_authenticates_against_postgres(
    uow: SqlUnitOfWork, clock: FixedClock
) -> None:
    await ProjectService(uow, clock).create_project(CLI, key=STOREFRONT, name=Name("Storefront"))
    keys = ApiKeyService(uow, clock)
    issued = await keys.issue_sdk_key(CLI, STOREFRONT, PROD, name=Name("checkout-api"))

    authenticated = await keys.authenticate(issued.secret)
    await keys.revoke(CLI, issued.key.id)

    assert authenticated.id == issued.key.id
    assert [key.revoked_at for key in await keys.list_keys()] == [NOW]
