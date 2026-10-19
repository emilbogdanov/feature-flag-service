import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from flagstaff.engine.conditions import AttributeCondition, Operator, UserListCondition
from flagstaff.engine.flag import Rule
from flagstaff.engine.serving import FixedVariant, Rollout, WeightedVariant
from flagstaff.engine.variants import FlagKind, Variant
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from flagstaff_server.application.errors import StaleFlagError
from flagstaff_server.domain.errors import FlagKeyTakenError
from flagstaff_server.domain.flags import Flag, Targeting
from flagstaff_server.domain.ids import FlagId
from flagstaff_server.domain.projects import Environment
from flagstaff_server.domain.values import Description, Name
from flagstaff_server.infrastructure.db.flags import SqlFlagRepository
from tests.integration.storefront import CREATED_AT, Storefront, store_storefront

LATER = CREATED_AT + timedelta(hours=1)
EU_PRO = Targeting(
    enabled=True,
    off_variant="off",
    fallthrough=FixedVariant("off"),
    rules=(
        Rule(
            id="beta-testers",
            conditions=(UserListCondition(frozenset({"user-7", "user-1042"})),),
            serve=FixedVariant("on"),
        ),
        Rule(
            id="eu-pro",
            conditions=(
                AttributeCondition(attribute="country", operator=Operator.IN, values=("BG", "DE")),
                AttributeCondition(attribute="plan", operator=Operator.IN, values=("pro",)),
            ),
            serve=Rollout((WeightedVariant("on", 25_000), WeightedVariant("off", 75_000))),
        ),
    ),
)


@pytest.fixture
async def storefront(session_factory: async_sessionmaker[AsyncSession]) -> Storefront:
    return await store_storefront(session_factory)


def new_flag(storefront: Storefront, key: str = "new-checkout") -> Flag:
    return Flag.create(
        flag_id=FlagId(uuid4()),
        project_id=storefront.project.id,
        key=key,
        name=Name("New checkout"),
        description=Description("Two-step checkout with saved cards"),
        kind=FlagKind.BOOLEAN,
        variants=(Variant("on", value=True), Variant("off", value=False)),
        off_variant="off",
        on_variant="on",
        at=CREATED_AT,
    )


async def stored(
    session_factory: async_sessionmaker[AsyncSession], storefront: Storefront, key: str
) -> Flag:
    async with session_factory() as session:
        flag = await SqlFlagRepository(session).get(storefront.project.id, key)
    assert flag is not None
    return flag


async def test_a_flag_comes_back_exactly_as_it_was_saved(
    session_factory: async_sessionmaker[AsyncSession], storefront: Storefront
) -> None:
    flag = new_flag(storefront)
    flag.change_targeting(storefront.prod.id, EU_PRO, at=LATER)
    flag.enable(storefront.dev.id, at=LATER)
    async with session_factory() as session:
        await SqlFlagRepository(session).add(flag)
        await session.commit()

    loaded = await stored(session_factory, storefront, "new-checkout")

    assert (loaded.id, loaded.key, loaded.kind, loaded.version) == (
        flag.id,
        "new-checkout",
        FlagKind.BOOLEAN,
        1,
    )
    assert (loaded.name, loaded.description) == (flag.name, flag.description)
    assert loaded.variants == flag.variants
    assert loaded.initial_targeting == flag.initial_targeting
    assert loaded.targeting == {
        storefront.prod.id: EU_PRO,
        storefront.dev.id: flag.targeting_in(storefront.dev.id),
    }
    assert (loaded.created_at, loaded.updated_at, loaded.archived_at) == (CREATED_AT, LATER, None)


async def test_saving_moves_the_version_on_and_keeps_the_changes(
    session_factory: async_sessionmaker[AsyncSession], storefront: Storefront
) -> None:
    async with session_factory() as session:
        await SqlFlagRepository(session).add(new_flag(storefront))
        await session.commit()
    flag = await stored(session_factory, storefront, "new-checkout")

    flag.change_targeting(storefront.prod.id, EU_PRO, at=LATER)
    async with session_factory() as session:
        await SqlFlagRepository(session).update(flag)
        await session.commit()
    flag.disable(storefront.prod.id, at=LATER)
    async with session_factory() as session:
        await SqlFlagRepository(session).update(flag)
        await session.commit()

    loaded = await stored(session_factory, storefront, "new-checkout")
    assert flag.version == loaded.version == 3
    assert loaded.targeting_in(storefront.prod.id).rules == EU_PRO.rules
    assert not loaded.targeting_in(storefront.prod.id).enabled


async def test_a_save_from_a_version_someone_else_moved_on_is_refused(
    session_factory: async_sessionmaker[AsyncSession], storefront: Storefront
) -> None:
    async with session_factory() as session:
        await SqlFlagRepository(session).add(new_flag(storefront))
        await session.commit()
    mine = await stored(session_factory, storefront, "new-checkout")
    theirs = await stored(session_factory, storefront, "new-checkout")
    theirs.enable(storefront.prod.id, at=LATER)
    async with session_factory() as session:
        await SqlFlagRepository(session).update(theirs)
        await session.commit()

    mine.change_targeting(storefront.prod.id, EU_PRO, at=LATER)
    async with session_factory() as session:
        with pytest.raises(StaleFlagError, match="no longer at version 1, it is at 2"):
            await SqlFlagRepository(session).update(mine)

    loaded = await stored(session_factory, storefront, "new-checkout")
    assert loaded.targeting_in(storefront.prod.id).rules == ()


async def test_of_two_saves_racing_from_one_version_exactly_one_wins(
    session_factory: async_sessionmaker[AsyncSession], storefront: Storefront
) -> None:
    async with session_factory() as session:
        await SqlFlagRepository(session).add(new_flag(storefront))
        await session.commit()

    async def save(environment: Environment) -> None:
        flag = await stored(session_factory, storefront, "new-checkout")
        flag.enable(environment.id, at=LATER)
        async with session_factory() as session:
            await SqlFlagRepository(session).update(flag)
            # Holds the row lock while the other save waits on it.
            await asyncio.sleep(0.05)
            await session.commit()

    results = await asyncio.gather(
        save(storefront.dev), save(storefront.prod), return_exceptions=True
    )

    assert sorted(type(result).__name__ for result in results) == ["NoneType", "StaleFlagError"]
    loaded = await stored(session_factory, storefront, "new-checkout")
    assert loaded.version == 2
    enabled = [
        env.key for env in (storefront.dev, storefront.prod) if loaded.targeting_in(env.id).enabled
    ]
    assert len(enabled) == 1


async def test_lists_active_flags_by_key_in_two_queries(
    session_factory: async_sessionmaker[AsyncSession], storefront: Storefront, engine: AsyncEngine
) -> None:
    async with session_factory() as session:
        repository = SqlFlagRepository(session)
        for key in ["search-v2", "new-checkout", "dark-mode", "legacy-cart"]:
            flag = new_flag(storefront, key)
            flag.change_targeting(storefront.prod.id, EU_PRO, at=LATER)
            if key == "legacy-cart":
                flag.archive(at=LATER)
            await repository.add(flag)
        await session.commit()
    statements: list[str] = []
    event.listen(
        engine.sync_engine, "before_cursor_execute", lambda *args: statements.append(args[2])
    )

    async with session_factory() as session:
        flags = await SqlFlagRepository(session).list_active(storefront.project.id)

    assert [flag.key for flag in flags] == ["dark-mode", "new-checkout", "search-v2"]
    assert all(flag.targeting_in(storefront.prod.id) == EU_PRO for flag in flags)
    assert len([s for s in statements if s.lstrip().upper().startswith("SELECT")]) == 2


async def test_flag_keys_are_unique_per_project(
    session_factory: async_sessionmaker[AsyncSession], storefront: Storefront
) -> None:
    async with session_factory() as session:
        repository = SqlFlagRepository(session)
        await repository.add(new_flag(storefront))

        with pytest.raises(
            FlagKeyTakenError, match="'storefront' already has a flag 'new-checkout'"
        ):
            await repository.add(new_flag(storefront))


async def test_an_archived_flag_is_still_found_by_key(
    session_factory: async_sessionmaker[AsyncSession], storefront: Storefront
) -> None:
    flag = new_flag(storefront)
    flag.archive(at=LATER)
    async with session_factory() as session:
        await SqlFlagRepository(session).add(flag)
        await session.commit()

    loaded = await stored(session_factory, storefront, "new-checkout")

    assert loaded.archived_at == LATER
