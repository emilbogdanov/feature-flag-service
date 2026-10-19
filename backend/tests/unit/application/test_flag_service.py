from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from flagstaff.engine.conditions import UserListCondition
from flagstaff.engine.context import EvaluationContext
from flagstaff.engine.flag import Rule
from flagstaff.engine.serving import FixedVariant
from flagstaff.engine.variants import FlagKind, Variant

from flagstaff_server.application.errors import StaleFlagError
from flagstaff_server.application.flags import UNVERSIONED_EDIT_ATTEMPTS, FlagService
from flagstaff_server.application.projects import ProjectService
from flagstaff_server.application.rulesets import RulesetChange
from flagstaff_server.domain.audit import Actor, AuditAction
from flagstaff_server.domain.errors import (
    ArchivedFlagError,
    EnvironmentNotFoundError,
    FlagKeyTakenError,
    FlagNotFoundError,
    InvalidTargetingError,
    ProjectNotFoundError,
)
from flagstaff_server.domain.flags import Flag, Targeting
from flagstaff_server.domain.values import Description, Name, Slug
from tests.unit.application.fakes import (
    FakeUnitOfWork,
    FixedClock,
    InMemoryRulesetChanges,
    ServerState,
)

NOW = datetime(2026, 10, 19, 9, 30, tzinfo=UTC)
ACTOR = Actor.command_line()
STOREFRONT = Slug("storefront")
PROD = Slug("prod")
DEV = Slug("dev")
ON = Variant("on", value=True)
OFF = Variant("off", value=False)
BETA_TESTERS = Rule(
    id="beta-testers",
    conditions=(UserListCondition(frozenset({"user-7", "user-1042"})),),
    serve=FixedVariant("on"),
)


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture
def changes() -> InMemoryRulesetChanges:
    return InMemoryRulesetChanges()


@pytest.fixture
def service(uow: FakeUnitOfWork, clock: FixedClock, changes: InMemoryRulesetChanges) -> FlagService:
    return FlagService(uow, clock, changes)


@pytest.fixture(autouse=True)
async def storefront(uow: FakeUnitOfWork, clock: FixedClock) -> None:
    await ProjectService(uow, clock).create_project(ACTOR, key=STOREFRONT, name=Name("Storefront"))


async def create_new_checkout(service: FlagService, key: str = "new-checkout") -> Flag:
    return await service.create_flag(
        ACTOR,
        STOREFRONT,
        key=key,
        name=Name("New checkout"),
        description=Description("Two-step checkout with saved cards"),
        kind=FlagKind.BOOLEAN,
        variants=(ON, OFF),
        off_variant="off",
        on_variant="on",
    )


def ruleset_versions(state: ServerState) -> dict[str, int]:
    return {str(e.key): e.ruleset_version for e in state.environments.values()}


def last_entry(uow: FakeUnitOfWork) -> tuple[AuditAction, dict[str, object]]:
    entry = uow.committed.audit[-1]
    return entry.action, dict(entry.changes)


def evaluate(flag: Flag, uow: FakeUnitOfWork, environment: Slug, user_key: str) -> object:
    [environment_id] = [e.id for e in uow.committed.environments.values() if e.key == environment]
    return flag.compile_for(environment_id).evaluate(EvaluationContext(user_key)).value


class TestCreate:
    async def test_stores_the_flag_and_audits_it(
        self, service: FlagService, uow: FakeUnitOfWork
    ) -> None:
        flag = await create_new_checkout(service)

        stored = await service.get_flag(STOREFRONT, "new-checkout")
        assert (stored.id, stored.version, stored.variants) == (flag.id, 1, (ON, OFF))
        action, changes = last_entry(uow)
        assert action is AuditAction.FLAG_CREATED
        assert changes["variants"] == [{"key": "on", "value": True}, {"key": "off", "value": False}]
        assert changes["off_variant"] == "off"

    async def test_reaches_every_environments_ruleset(
        self, service: FlagService, uow: FakeUnitOfWork
    ) -> None:
        await create_new_checkout(service)

        assert ruleset_versions(uow.committed) == {"dev": 1, "staging": 1, "prod": 1}

    async def test_keys_are_unique_within_a_project(
        self, service: FlagService, uow: FakeUnitOfWork
    ) -> None:
        await create_new_checkout(service)

        with pytest.raises(
            FlagKeyTakenError, match="'storefront' already has a flag 'new-checkout'"
        ):
            await create_new_checkout(service)

        assert len(uow.committed.flags) == 1

    async def test_needs_an_existing_project(self, service: FlagService) -> None:
        with pytest.raises(ProjectNotFoundError):
            await service.list_flags(Slug("back-office"))


class TestSwitching:
    async def test_enabling_in_prod_leaves_dev_alone(
        self, service: FlagService, uow: FakeUnitOfWork
    ) -> None:
        await create_new_checkout(service)

        flag = await service.enable(ACTOR, STOREFRONT, "new-checkout", PROD)

        assert flag.version == 2
        assert evaluate(flag, uow, PROD, "user-7") is True
        assert evaluate(flag, uow, DEV, "user-7") is False
        assert ruleset_versions(uow.committed) == {"dev": 1, "staging": 1, "prod": 2}
        assert uow.committed.audit[-1].action is AuditAction.FLAG_ENABLED
        assert uow.committed.audit[-1].environment_id is not None

    async def test_switching_to_the_state_it_is_in_changes_nothing(
        self, service: FlagService, uow: FakeUnitOfWork
    ) -> None:
        await create_new_checkout(service)
        commits = uow.commits

        flag = await service.disable(ACTOR, STOREFRONT, "new-checkout", PROD)

        assert flag.version == 1
        assert uow.commits == commits
        assert uow.committed.audit[-1].action is AuditAction.FLAG_CREATED

    async def test_needs_an_environment_of_the_project(self, service: FlagService) -> None:
        await create_new_checkout(service)

        with pytest.raises(EnvironmentNotFoundError, match="no environment 'qa'"):
            await service.enable(ACTOR, STOREFRONT, "new-checkout", Slug("qa"))

    async def test_needs_an_existing_flag(self, service: FlagService) -> None:
        with pytest.raises(FlagNotFoundError, match="no flag 'dark-mode'"):
            await service.enable(ACTOR, STOREFRONT, "dark-mode", PROD)


class TestTargeting:
    async def test_audits_the_targeting_before_and_after(
        self, service: FlagService, uow: FakeUnitOfWork
    ) -> None:
        created = await create_new_checkout(service)
        targeting = Targeting(
            enabled=True, off_variant="off", fallthrough=FixedVariant("off"), rules=(BETA_TESTERS,)
        )

        flag = await service.change_targeting(
            ACTOR, STOREFRONT, "new-checkout", PROD, targeting=targeting
        )

        assert evaluate(flag, uow, PROD, "user-7") is True
        assert evaluate(flag, uow, PROD, "user-310") is False
        action, changes = last_entry(uow)
        assert action is AuditAction.FLAG_TARGETING_CHANGED
        assert changes["targeting"] == {
            "before": created.initial_targeting.to_document(),
            "after": targeting.to_document(),
        }
        assert ruleset_versions(uow.committed) == {"dev": 1, "staging": 1, "prod": 2}

    async def test_rejected_targeting_saves_nothing(
        self, service: FlagService, uow: FakeUnitOfWork
    ) -> None:
        await create_new_checkout(service)
        before = uow.committed

        with pytest.raises(InvalidTargetingError, match="'holdout'"):
            await service.change_targeting(
                ACTOR,
                STOREFRONT,
                "new-checkout",
                PROD,
                targeting=Targeting(
                    enabled=True, off_variant="off", fallthrough=FixedVariant("holdout")
                ),
            )

        assert uow.committed is before


class TestAnnouncements:
    async def test_a_new_flag_announces_every_environments_new_version(
        self, service: FlagService, changes: InMemoryRulesetChanges
    ) -> None:
        await create_new_checkout(service)

        assert sorted(change.version for change in changes.announced) == [1, 1, 1]

    async def test_a_switch_announces_only_its_environment(
        self, service: FlagService, uow: FakeUnitOfWork, changes: InMemoryRulesetChanges
    ) -> None:
        await create_new_checkout(service)
        changes.announced.clear()

        await service.enable(ACTOR, STOREFRONT, "new-checkout", PROD)

        [prod] = [e for e in uow.committed.environments.values() if e.key == PROD]
        assert changes.announced == [RulesetChange(prod.id, 2)]

    async def test_nothing_is_announced_for_a_change_that_did_not_happen(
        self, service: FlagService, changes: InMemoryRulesetChanges
    ) -> None:
        await create_new_checkout(service)
        changes.announced.clear()

        await service.disable(ACTOR, STOREFRONT, "new-checkout", PROD)
        await service.change_details(
            ACTOR,
            STOREFRONT,
            "new-checkout",
            name=Name("Checkout v2"),
            description=Description(),
        )
        with pytest.raises(InvalidTargetingError):
            await service.change_variants(ACTOR, STOREFRONT, "new-checkout", variants=(ON,))

        assert changes.announced == []

    async def test_a_save_that_lost_a_race_announces_nothing(
        self, service: FlagService, uow: FakeUnitOfWork, changes: InMemoryRulesetChanges
    ) -> None:
        flag = await create_new_checkout(service)
        changes.announced.clear()
        uow.before_next_commit = someone_else_saves(flag)

        with pytest.raises(StaleFlagError):
            await service.enable(ACTOR, STOREFRONT, "new-checkout", PROD, expected_version=1)

        assert changes.announced == []


class TestOptimisticLocking:
    async def test_an_edit_based_on_an_old_version_is_refused(
        self, service: FlagService, uow: FakeUnitOfWork
    ) -> None:
        await create_new_checkout(service)
        await service.enable(ACTOR, STOREFRONT, "new-checkout", DEV)

        with pytest.raises(StaleFlagError, match="no longer at version 1, it is at 2"):
            await service.disable(ACTOR, STOREFRONT, "new-checkout", DEV, expected_version=1)

        assert (
            (await service.get_flag(STOREFRONT, "new-checkout"))
            .targeting_in(next(iter(uow.committed.environments)))
            .enabled
        )

    async def test_an_edit_on_the_current_version_goes_through(self, service: FlagService) -> None:
        await create_new_checkout(service)

        flag = await service.enable(ACTOR, STOREFRONT, "new-checkout", DEV, expected_version=1)

        assert flag.version == 2

    async def test_a_versioned_edit_loses_to_a_concurrent_save(
        self, service: FlagService, uow: FakeUnitOfWork
    ) -> None:
        flag = await create_new_checkout(service)
        uow.before_next_commit = someone_else_saves(flag)

        with pytest.raises(StaleFlagError):
            await service.enable(ACTOR, STOREFRONT, "new-checkout", PROD, expected_version=1)

        assert uow.committed.audit[-1].action is AuditAction.FLAG_CREATED

    async def test_an_unversioned_edit_is_redone_on_top_of_a_concurrent_save(
        self, service: FlagService, uow: FakeUnitOfWork
    ) -> None:
        flag = await create_new_checkout(service)
        uow.before_next_commit = someone_else_saves(flag)

        enabled = await service.enable(ACTOR, STOREFRONT, "new-checkout", PROD)

        assert enabled.version == 3
        assert evaluate(enabled, uow, PROD, "user-7") is True
        assert [entry.action for entry in uow.committed.audit].count(AuditAction.FLAG_ENABLED) == 1

    async def test_an_unversioned_edit_gives_up_on_a_flag_that_keeps_changing(
        self, service: FlagService, uow: FakeUnitOfWork
    ) -> None:
        flag = await create_new_checkout(service)
        save = someone_else_saves(flag)

        def save_again_and_again(state: ServerState) -> None:
            save(state)
            uow.before_next_commit = save_again_and_again

        uow.before_next_commit = save_again_and_again

        with pytest.raises(StaleFlagError):
            await service.enable(ACTOR, STOREFRONT, "new-checkout", PROD)
        assert uow.committed.flags[flag.id].version == 1 + UNVERSIONED_EDIT_ATTEMPTS


def someone_else_saves(flag: Flag) -> Callable[[ServerState], None]:
    def save(state: ServerState) -> None:
        state.flags[flag.id].mark_saved()

    return save


class TestVariants:
    async def test_adding_a_variant_reaches_every_ruleset(
        self, service: FlagService, uow: FakeUnitOfWork
    ) -> None:
        await create_new_checkout(service)
        holdout = Variant("holdout", value=False)

        flag = await service.change_variants(
            ACTOR, STOREFRONT, "new-checkout", variants=(ON, OFF, holdout)
        )

        assert flag.variants == (ON, OFF, holdout)
        assert ruleset_versions(uow.committed) == {"dev": 2, "staging": 2, "prod": 2}
        assert uow.committed.audit[-1].action is AuditAction.FLAG_VARIANTS_CHANGED

    async def test_dropping_a_variant_in_use_is_refused(self, service: FlagService) -> None:
        await create_new_checkout(service)

        with pytest.raises(InvalidTargetingError, match="new environments"):
            await service.change_variants(ACTOR, STOREFRONT, "new-checkout", variants=(ON,))

    async def test_says_which_environment_still_serves_a_dropped_variant(
        self, service: FlagService
    ) -> None:
        await create_new_checkout(service)
        holdout = Variant("holdout", value=False)
        await service.change_variants(
            ACTOR, STOREFRONT, "new-checkout", variants=(ON, OFF, holdout)
        )
        await service.change_targeting(
            ACTOR,
            STOREFRONT,
            "new-checkout",
            PROD,
            targeting=Targeting(
                enabled=True, off_variant="off", fallthrough=FixedVariant("holdout")
            ),
        )

        with pytest.raises(InvalidTargetingError, match=r"^prod: the fallthrough .*\['holdout'\]"):
            await service.change_variants(ACTOR, STOREFRONT, "new-checkout", variants=(ON, OFF))


class TestDetails:
    async def test_audits_only_what_changed_and_leaves_rulesets_alone(
        self, service: FlagService, uow: FakeUnitOfWork, clock: FixedClock
    ) -> None:
        await create_new_checkout(service)
        clock.advance(timedelta(minutes=5))

        flag = await service.change_details(
            ACTOR,
            STOREFRONT,
            "new-checkout",
            name=Name("Checkout v2"),
            description=Description("Two-step checkout with saved cards"),
        )

        assert str(flag.name) == "Checkout v2"
        assert flag.updated_at == NOW + timedelta(minutes=5)
        assert last_entry(uow) == (
            AuditAction.FLAG_DETAILS_CHANGED,
            {"name": {"before": "New checkout", "after": "Checkout v2"}},
        )
        assert ruleset_versions(uow.committed) == {"dev": 1, "staging": 1, "prod": 1}

    async def test_saving_the_same_details_is_not_a_change(
        self, service: FlagService, uow: FakeUnitOfWork
    ) -> None:
        await create_new_checkout(service)
        commits = uow.commits

        flag = await service.change_details(
            ACTOR,
            STOREFRONT,
            "new-checkout",
            name=Name("New checkout"),
            description=Description("Two-step checkout with saved cards"),
        )

        assert flag.version == 1
        assert uow.commits == commits


class TestArchive:
    async def test_an_archived_flag_leaves_the_list_but_keeps_its_key(
        self, service: FlagService, uow: FakeUnitOfWork
    ) -> None:
        await create_new_checkout(service)
        await create_new_checkout(service, key="search-v2")

        await service.archive(ACTOR, STOREFRONT, "new-checkout")

        assert [flag.key for flag in await service.list_flags(STOREFRONT)] == ["search-v2"]
        assert (await service.get_flag(STOREFRONT, "new-checkout")).is_archived
        assert ruleset_versions(uow.committed) == {"dev": 3, "staging": 3, "prod": 3}
        with pytest.raises(FlagKeyTakenError):
            await create_new_checkout(service)

    async def test_an_archived_flag_cannot_be_switched_on(self, service: FlagService) -> None:
        await create_new_checkout(service)
        await service.archive(ACTOR, STOREFRONT, "new-checkout")

        with pytest.raises(ArchivedFlagError):
            await service.enable(ACTOR, STOREFRONT, "new-checkout", PROD)
