from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from flagstaff_server.api.app import create_app
from flagstaff_server.api.container import Container
from flagstaff_server.application.api_keys import ApiKeyService
from flagstaff_server.application.live import RulesetBroadcaster
from flagstaff_server.application.projects import ProjectService
from flagstaff_server.application.rulesets import RulesetService
from flagstaff_server.domain.audit import Actor
from flagstaff_server.domain.values import Name, Slug
from tests.unit.application.fakes import FakeUnitOfWork, FixedClock, InMemoryRulesetChanges

type Headers = dict[str, str]

NOW = datetime(2026, 10, 19, 9, 30, tzinfo=UTC)
CLI = Actor.command_line()


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture
def container(uow: FakeUnitOfWork, clock: FixedClock) -> Container:
    # One shared fake stands in for the database across requests.
    changes = InMemoryRulesetChanges()
    broadcaster = RulesetBroadcaster(
        lambda: RulesetService(uow), changes, resync_interval=3600, feed_retry_delay=0.01
    )
    return Container(
        uow_factory=lambda: uow,
        clock=clock,
        ruleset_changes=changes,
        broadcaster=broadcaster,
        stream_heartbeat_seconds=0.2,
    )


@pytest.fixture
async def http(container: Container) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=create_app(container))
    async with AsyncClient(transport=transport, base_url="http://flagstaff.test") as client:
        yield client


def bearer(secret: str) -> Headers:
    return {"Authorization": f"Bearer {secret}"}


@pytest.fixture
async def as_admin(uow: FakeUnitOfWork, clock: FixedClock) -> Headers:
    issued = await ApiKeyService(uow, clock).issue_admin_key(CLI, name=Name("Release tooling"))
    return bearer(issued.secret)


async def sdk_key_for(uow: FakeUnitOfWork, clock: FixedClock, environment: str = "prod") -> Headers:
    issued = await ApiKeyService(uow, clock).issue_sdk_key(
        CLI, Slug("storefront"), Slug(environment), name=Name(f"checkout-api ({environment})")
    )
    return bearer(issued.secret)


# A storefront project, created the way the CLI would, with an SDK key for its prod environment.
@pytest.fixture
async def as_prod_sdk(uow: FakeUnitOfWork, clock: FixedClock) -> Headers:
    await ProjectService(uow, clock).create_project(
        CLI, key=Slug("storefront"), name=Name("Storefront")
    )
    return await sdk_key_for(uow, clock)
