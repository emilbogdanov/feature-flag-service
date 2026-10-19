from datetime import UTC, datetime

import pytest

from flagstaff_server.application.api_keys import ApiKeyService
from flagstaff_server.application.authentication import AuthenticatedKeys
from flagstaff_server.application.errors import InvalidApiKeyError
from flagstaff_server.domain.api_keys import ApiKey
from flagstaff_server.domain.audit import Actor
from flagstaff_server.domain.values import Name
from tests.unit.application.fakes import FakeUnitOfWork, FixedClock

NOW = datetime(2026, 10, 19, 9, 30, tzinfo=UTC)
CLI = Actor.command_line()


class CountingKeyService(ApiKeyService):
    lookups = 0

    async def authenticate(self, secret: str) -> ApiKey:
        CountingKeyService.lookups += 1
        return await super().authenticate(secret)


class Ticking:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def service(uow: FakeUnitOfWork) -> CountingKeyService:
    CountingKeyService.lookups = 0
    return CountingKeyService(uow, FixedClock(NOW))


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def ticking() -> Ticking:
    return Ticking()


def remembering(service: ApiKeyService, ticking: Ticking, **options: int) -> AuthenticatedKeys:
    return AuthenticatedKeys(lambda: service, ttl=10.0, clock=ticking, **options)


async def test_looks_a_key_up_once_while_it_is_remembered(
    service: CountingKeyService, ticking: Ticking
) -> None:
    issued = await service.issue_admin_key(CLI, name=Name("Release tooling"))
    keys = remembering(service, ticking)

    first = await keys.authenticate(issued.secret)
    ticking.now += 9.9
    again = await keys.authenticate(issued.secret)

    assert first.id == again.id == issued.key.id
    assert CountingKeyService.lookups == 1


async def test_looks_the_key_up_again_once_its_entry_expires(
    service: CountingKeyService, ticking: Ticking
) -> None:
    issued = await service.issue_admin_key(CLI, name=Name("Release tooling"))
    keys = remembering(service, ticking)
    await keys.authenticate(issued.secret)

    await service.revoke(CLI, issued.key.id)
    ticking.now += 10.0

    with pytest.raises(InvalidApiKeyError):
        await keys.authenticate(issued.secret)


async def test_a_forgotten_key_is_checked_again_straight_away(
    service: CountingKeyService, ticking: Ticking
) -> None:
    issued = await service.issue_admin_key(CLI, name=Name("Release tooling"))
    keys = remembering(service, ticking)
    await keys.authenticate(issued.secret)

    await service.revoke(CLI, issued.key.id)
    keys.forget(issued.key.id)

    with pytest.raises(InvalidApiKeyError):
        await keys.authenticate(issued.secret)


async def test_never_remembers_a_secret_that_failed(
    service: CountingKeyService, ticking: Ticking
) -> None:
    keys = remembering(service, ticking)

    for _ in range(3):
        with pytest.raises(InvalidApiKeyError):
            await keys.authenticate("fs_sdk_not-a-real-key")

    assert CountingKeyService.lookups == 3


async def test_makes_room_by_dropping_the_oldest_entry(
    service: CountingKeyService, ticking: Ticking
) -> None:
    oldest, newer, newest = [
        await service.issue_admin_key(CLI, name=Name(f"Key {n}")) for n in range(3)
    ]
    keys = remembering(service, ticking, max_entries=2)
    for issued in (oldest, newer, newest):
        await keys.authenticate(issued.secret)

    await keys.authenticate(newest.secret)
    await keys.authenticate(oldest.secret)

    assert CountingKeyService.lookups == 4


async def test_remembers_nothing_with_no_time_to_remember_it_for(
    service: CountingKeyService, ticking: Ticking
) -> None:
    issued = await service.issue_admin_key(CLI, name=Name("Release tooling"))
    keys = AuthenticatedKeys(lambda: service, ttl=0, clock=ticking)

    await keys.authenticate(issued.secret)
    await keys.authenticate(issued.secret)

    assert CountingKeyService.lookups == 2
