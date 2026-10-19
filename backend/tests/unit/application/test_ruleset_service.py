from datetime import UTC, datetime

import pytest
from flagstaff.engine.context import EvaluationContext
from flagstaff.engine.ruleset import Ruleset
from flagstaff.engine.variants import FlagKind, Variant

from flagstaff_server.application.flags import FlagService
from flagstaff_server.application.projects import ProjectService
from flagstaff_server.application.rulesets import RulesetService
from flagstaff_server.domain.audit import Actor
from flagstaff_server.domain.errors import EnvironmentNotFoundError
from flagstaff_server.domain.values import Description, Name, Slug
from tests.unit.application.fakes import FakeUnitOfWork, FixedClock, InMemoryRulesetChanges

NOW = datetime(2026, 10, 19, 9, 30, tzinfo=UTC)
CLI = Actor.command_line()
STOREFRONT = Slug("storefront")
PROD = Slug("prod")


def served(ruleset: Ruleset, flag_key: str) -> object:
    evaluation = ruleset.evaluate(flag_key, EvaluationContext("user-1042"))
    assert evaluation is not None
    return evaluation.value


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def flags(uow: FakeUnitOfWork) -> FlagService:
    return FlagService(uow, FixedClock(NOW), InMemoryRulesetChanges())


@pytest.fixture
def service(uow: FakeUnitOfWork) -> RulesetService:
    return RulesetService(uow)


@pytest.fixture(autouse=True)
async def storefront(uow: FakeUnitOfWork, flags: FlagService) -> None:
    await ProjectService(uow, FixedClock(NOW)).create_project(
        CLI, key=STOREFRONT, name=Name("Storefront")
    )
    for key in ["new-checkout", "search-v2"]:
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


async def test_holds_every_active_flag_as_the_environment_evaluates_it(
    service: RulesetService, flags: FlagService
) -> None:
    await flags.enable(CLI, STOREFRONT, "new-checkout", PROD)

    ruleset = await service.ruleset_in(STOREFRONT, PROD)

    assert sorted(ruleset.flags) == ["new-checkout", "search-v2"]
    assert served(ruleset, "new-checkout") is True
    assert served(ruleset, "search-v2") is False


async def test_goes_out_under_the_environments_current_version(
    service: RulesetService, flags: FlagService
) -> None:
    before = await service.ruleset_in(STOREFRONT, PROD)

    await flags.enable(CLI, STOREFRONT, "new-checkout", PROD)

    assert (await service.ruleset_in(STOREFRONT, PROD)).version == before.version + 1
    assert (await service.ruleset_in(STOREFRONT, Slug("dev"))).version == before.version


async def test_leaves_archived_flags_out(service: RulesetService, flags: FlagService) -> None:
    await flags.archive(CLI, STOREFRONT, "search-v2")

    assert list((await service.ruleset_in(STOREFRONT, PROD)).flags) == ["new-checkout"]


async def test_an_sdk_key_reads_its_environment_by_id(
    service: RulesetService, uow: FakeUnitOfWork
) -> None:
    [prod] = [e for e in uow.committed.environments.values() if e.key == PROD]

    assert await service.ruleset_for(prod.id) == await service.ruleset_in(STOREFRONT, PROD)


async def test_unknown_environments_are_reported(service: RulesetService) -> None:
    with pytest.raises(EnvironmentNotFoundError):
        await service.ruleset_in(STOREFRONT, Slug("qa"))
