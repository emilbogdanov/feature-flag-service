import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from flagstaff.engine.ruleset import Ruleset
from flagstaff.engine.variants import FlagKind, Variant
from flagstaff.engine.wire import ruleset_from_document

from flagstaff_server.application.flags import FlagService
from flagstaff_server.application.live import (
    PublishedRuleset,
    RulesetBroadcaster,
    RulesetSubscription,
    StreamClosedError,
)
from flagstaff_server.application.projects import ProjectService
from flagstaff_server.application.rulesets import RulesetService
from flagstaff_server.domain.audit import Actor
from flagstaff_server.domain.ids import EnvironmentId
from flagstaff_server.domain.values import Description, Name, Slug
from tests.unit.application.fakes import FakeUnitOfWork, FixedClock, InMemoryRulesetChanges

NOW = datetime(2026, 10, 19, 9, 30, tzinfo=UTC)
CLI = Actor.command_line()
STOREFRONT = Slug("storefront")


class CountingRulesetService(RulesetService):
    builds = 0

    async def ruleset_for(self, environment_id: EnvironmentId) -> Ruleset:
        CountingRulesetService.builds += 1
        return await super().ruleset_for(environment_id)


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def bus() -> InMemoryRulesetChanges:
    return InMemoryRulesetChanges()


@pytest.fixture
def flags(uow: FakeUnitOfWork, bus: InMemoryRulesetChanges) -> FlagService:
    return FlagService(uow, FixedClock(NOW), bus)


@pytest.fixture
def broadcaster(uow: FakeUnitOfWork, bus: InMemoryRulesetChanges) -> RulesetBroadcaster:
    CountingRulesetService.builds = 0
    return RulesetBroadcaster(
        lambda: CountingRulesetService(uow), bus, resync_interval=3600, feed_retry_delay=0.01
    )


@pytest.fixture
async def running(
    broadcaster: RulesetBroadcaster, bus: InMemoryRulesetChanges
) -> AsyncIterator[None]:
    task = asyncio.create_task(broadcaster.run())
    async with asyncio.timeout(1):
        while bus.listeners == 0:
            await asyncio.sleep(0)
    yield
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.fixture(autouse=True)
async def storefront(uow: FakeUnitOfWork, flags: FlagService) -> None:
    await ProjectService(uow, FixedClock(NOW)).create_project(
        CLI, key=STOREFRONT, name=Name("Storefront")
    )
    await create_flag(flags, "new-checkout")


async def create_flag(flags: FlagService, key: str) -> None:
    await flags.create_flag(
        CLI,
        STOREFRONT,
        key=key,
        name=Name(key),
        description=Description(),
        kind=FlagKind.BOOLEAN,
        variants=(Variant("on", value=True), Variant("off", value=False)),
        off_variant="off",
        on_variant="on",
    )


def environment(uow: FakeUnitOfWork, key: str) -> EnvironmentId:
    [found] = [e.id for e in uow.committed.environments.values() if e.key == Slug(key)]
    return found


async def next_ruleset(subscription: RulesetSubscription) -> Ruleset:
    async with asyncio.timeout(1):
        published = await subscription.next()
    ruleset = ruleset_from_document(json.loads(published.document))
    assert ruleset.version == published.version
    return ruleset


async def until(condition: Callable[[], bool]) -> None:
    async with asyncio.timeout(1):
        while not condition():
            await asyncio.sleep(0.005)


async def nothing_arrives(subscription: RulesetSubscription) -> None:
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.05):
            await subscription.next()


async def test_a_new_stream_starts_with_the_current_rules(
    broadcaster: RulesetBroadcaster, uow: FakeUnitOfWork
) -> None:
    async with broadcaster.subscribe(environment(uow, "prod"), known_version=None) as stream:
        ruleset = await next_ruleset(stream)

    assert ruleset.version == 1
    assert list(ruleset.flags) == ["new-checkout"]


async def test_a_stream_that_already_holds_the_current_rules_waits(
    broadcaster: RulesetBroadcaster, uow: FakeUnitOfWork
) -> None:
    async with broadcaster.subscribe(environment(uow, "prod"), known_version=1) as stream:
        await nothing_arrives(stream)


@pytest.mark.usefixtures("running")
async def test_a_change_reaches_the_streams_of_its_environment_only(
    broadcaster: RulesetBroadcaster, uow: FakeUnitOfWork, flags: FlagService
) -> None:
    prod, dev = environment(uow, "prod"), environment(uow, "dev")
    async with (
        broadcaster.subscribe(prod, known_version=1) as prod_stream,
        broadcaster.subscribe(dev, known_version=1) as dev_stream,
    ):
        await flags.enable(CLI, STOREFRONT, "new-checkout", Slug("prod"))

        ruleset = await next_ruleset(prod_stream)
        await nothing_arrives(dev_stream)

    assert ruleset.version == 2
    assert ruleset.flags["new-checkout"].enabled


@pytest.mark.usefixtures("running")
async def test_builds_each_version_once_however_many_streams_want_it(
    broadcaster: RulesetBroadcaster, uow: FakeUnitOfWork, flags: FlagService
) -> None:
    prod = environment(uow, "prod")
    async with (
        broadcaster.subscribe(prod, known_version=1) as first,
        broadcaster.subscribe(prod, known_version=1) as second,
        broadcaster.subscribe(prod, known_version=1) as third,
    ):
        builds_before = CountingRulesetService.builds
        await flags.enable(CLI, STOREFRONT, "new-checkout", Slug("prod"))

        received = [await next_ruleset(stream) for stream in (first, second, third)]

    assert {ruleset.version for ruleset in received} == {2}
    assert CountingRulesetService.builds == builds_before + 1


async def test_a_slow_stream_skips_straight_to_the_newest_version(
    broadcaster: RulesetBroadcaster, uow: FakeUnitOfWork, flags: FlagService
) -> None:
    prod = environment(uow, "prod")
    async with broadcaster.subscribe(prod, known_version=1) as stream:
        await flags.enable(CLI, STOREFRONT, "new-checkout", Slug("prod"))
        await flags.disable(CLI, STOREFRONT, "new-checkout", Slug("prod"))
        await broadcaster.resync()

        ruleset = await next_ruleset(stream)
        await nothing_arrives(stream)

    assert ruleset.version == 3


async def test_a_resync_catches_a_change_whose_announcement_was_lost(
    broadcaster: RulesetBroadcaster, uow: FakeUnitOfWork
) -> None:
    unheard = FlagService(uow, FixedClock(NOW), InMemoryRulesetChanges())
    prod = environment(uow, "prod")
    async with broadcaster.subscribe(prod, known_version=1) as stream:
        await unheard.enable(CLI, STOREFRONT, "new-checkout", Slug("prod"))
        await nothing_arrives(stream)

        await broadcaster.resync()

        assert (await next_ruleset(stream)).version == 2


@pytest.mark.usefixtures("running")
async def test_resubscribes_after_losing_the_feed(
    broadcaster: RulesetBroadcaster,
    uow: FakeUnitOfWork,
    flags: FlagService,
    bus: InMemoryRulesetChanges,
) -> None:
    prod = environment(uow, "prod")
    async with broadcaster.subscribe(prod, known_version=1) as stream:
        bus.cut()
        async with asyncio.timeout(1):
            while bus.subscriptions_made < 2:
                await asyncio.sleep(0.005)

        await flags.enable(CLI, STOREFRONT, "new-checkout", Slug("prod"))

        assert (await next_ruleset(stream)).version == 2


async def test_warns_once_per_feed_outage_rather_than_on_every_retry(
    broadcaster: RulesetBroadcaster,
    bus: InMemoryRulesetChanges,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="flagstaff_server.application.live")
    bus.available = False
    following = asyncio.create_task(broadcaster.run())
    try:
        await until(lambda: len(caplog.records) >= 4)
        bus.available = True
        await until(lambda: bus.listeners == 1)
        bus.cut()
        await until(lambda: bus.subscriptions_made == 2)
    finally:
        following.cancel()
        with suppress(asyncio.CancelledError):
            await following

    assert [
        (record.getMessage(), record.__dict__["error"])
        for record in caplog.records
        if record.levelno == logging.WARNING
    ] == [
        (
            "cannot subscribe to the ruleset change feed; retrying",
            "the in-memory feed is switched off",
        ),
        ("lost the ruleset change feed; resubscribing", "the in-memory feed was cut"),
    ]


async def test_closing_ends_every_stream(
    broadcaster: RulesetBroadcaster, uow: FakeUnitOfWork
) -> None:
    async with broadcaster.subscribe(environment(uow, "prod"), known_version=1) as stream:
        broadcaster.close()

        with pytest.raises(StreamClosedError):
            await stream.next()


async def test_forgets_an_environment_once_its_last_stream_leaves(
    broadcaster: RulesetBroadcaster, uow: FakeUnitOfWork
) -> None:
    prod = environment(uow, "prod")
    async with (
        broadcaster.subscribe(prod, known_version=None),
        broadcaster.subscribe(prod, known_version=None),
    ):
        assert broadcaster.stream_count == 2

    assert broadcaster.stream_count == 0
    async with broadcaster.subscribe(prod, known_version=None) as stream:
        assert (await next_ruleset(stream)).version == 1


async def test_a_stream_is_never_offered_a_version_it_already_has() -> None:
    subscription = RulesetSubscription(EnvironmentId(uuid4()), known_version=5)

    subscription.offer(PublishedRuleset(4, "{}"))
    subscription.offer(PublishedRuleset(5, "{}"))

    await nothing_arrives(subscription)
