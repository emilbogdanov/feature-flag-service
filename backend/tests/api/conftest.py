from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from flagstaff_server.api.app import create_app
from flagstaff_server.api.container import Container
from flagstaff_server.application.api_keys import ApiKeyService
from flagstaff_server.application.projects import ProjectService
from flagstaff_server.domain.audit import Actor
from flagstaff_server.domain.values import Name, Slug
from tests.unit.application.fakes import FakeUnitOfWork, FixedClock

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
async def http(uow: FakeUnitOfWork, clock: FixedClock) -> AsyncIterator[AsyncClient]:
    # One shared fake stands in for the database across requests.
    container = Container(uow_factory=lambda: uow, clock=clock)
    transport = ASGITransport(app=create_app(container))
    async with AsyncClient(transport=transport, base_url="http://flagstaff.test") as client:
        yield client


def bearer(secret: str) -> Headers:
    return {"Authorization": f"Bearer {secret}"}


@pytest.fixture
async def as_admin(uow: FakeUnitOfWork, clock: FixedClock) -> Headers:
    issued = await ApiKeyService(uow, clock).issue_admin_key(CLI, name=Name("Release tooling"))
    return bearer(issued.secret)


# A storefront project, created the way the CLI would, with an SDK key for its prod environment.
@pytest.fixture
async def as_prod_sdk(uow: FakeUnitOfWork, clock: FixedClock) -> Headers:
    await ProjectService(uow, clock).create_project(
        CLI, key=Slug("storefront"), name=Name("Storefront")
    )
    issued = await ApiKeyService(uow, clock).issue_sdk_key(
        CLI, Slug("storefront"), Slug("prod"), name=Name("checkout-api")
    )
    return bearer(issued.secret)
