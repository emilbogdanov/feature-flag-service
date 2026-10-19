from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from flagstaff_server.application.api_keys import ApiKeyService, hash_secret
from flagstaff_server.application.errors import ApiKeyNotFoundError, InvalidApiKeyError
from flagstaff_server.application.projects import ProjectService
from flagstaff_server.domain.api_keys import ApiKeyKind
from flagstaff_server.domain.audit import Actor, AuditAction
from flagstaff_server.domain.errors import EnvironmentNotFoundError
from flagstaff_server.domain.ids import ApiKeyId
from flagstaff_server.domain.values import Name, Slug
from tests.unit.application.fakes import FakeUnitOfWork, FixedClock

NOW = datetime(2026, 10, 19, 9, 30, tzinfo=UTC)
CLI = Actor.command_line()
STOREFRONT = Slug("storefront")
PROD = Slug("prod")


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture
def service(uow: FakeUnitOfWork, clock: FixedClock) -> ApiKeyService:
    return ApiKeyService(uow, clock)


@pytest.fixture(autouse=True)
async def storefront(uow: FakeUnitOfWork, clock: FixedClock) -> None:
    await ProjectService(uow, clock).create_project(CLI, key=STOREFRONT, name=Name("Storefront"))


async def test_an_issued_secret_authenticates_its_key(service: ApiKeyService) -> None:
    issued = await service.issue_admin_key(CLI, name=Name("Release tooling"))

    assert issued.secret.startswith("fs_admin_")
    assert (await service.authenticate(issued.secret)).id == issued.key.id


async def test_only_a_hash_of_the_secret_is_stored(
    service: ApiKeyService, uow: FakeUnitOfWork
) -> None:
    issued = await service.issue_admin_key(CLI, name=Name("Release tooling"))

    assert list(uow.committed.secret_hashes) == [hash_secret(issued.secret)]


async def test_secrets_are_unique(service: ApiKeyService) -> None:
    secrets = {(await service.issue_admin_key(CLI, name=Name("ci"))).secret for _ in range(20)}

    assert len(secrets) == 20


async def test_an_sdk_key_belongs_to_the_environment_it_was_issued_for(
    service: ApiKeyService, uow: FakeUnitOfWork
) -> None:
    issued = await service.issue_sdk_key(CLI, STOREFRONT, PROD, name=Name("checkout-api"))

    [prod] = [e for e in uow.committed.environments.values() if e.key == PROD]
    assert issued.secret.startswith("fs_sdk_")
    assert issued.key.kind is ApiKeyKind.SDK
    assert issued.key.environment_id == prod.id
    assert uow.committed.audit[-1].environment_id == prod.id
    assert uow.committed.audit[-1].project_id == prod.project_id


async def test_an_sdk_key_needs_an_existing_environment(service: ApiKeyService) -> None:
    with pytest.raises(EnvironmentNotFoundError):
        await service.issue_sdk_key(CLI, STOREFRONT, Slug("qa"), name=Name("checkout-api"))


@pytest.mark.parametrize("secret", ["", "fs_admin_", "fs_sdk_not-a-real-key"])
async def test_unknown_secrets_are_refused(service: ApiKeyService, secret: str) -> None:
    await service.issue_admin_key(CLI, name=Name("Release tooling"))

    with pytest.raises(InvalidApiKeyError):
        await service.authenticate(secret)


async def test_a_revoked_key_stops_working(
    service: ApiKeyService, uow: FakeUnitOfWork, clock: FixedClock
) -> None:
    issued = await service.issue_sdk_key(CLI, STOREFRONT, PROD, name=Name("checkout-api"))
    clock.advance(timedelta(days=3))

    revoked = await service.revoke(CLI, issued.key.id)

    assert revoked.revoked_at == NOW + timedelta(days=3)
    with pytest.raises(InvalidApiKeyError):
        await service.authenticate(issued.secret)
    entry = uow.committed.audit[-1]
    assert (entry.action, entry.subject, entry.at) == (
        AuditAction.API_KEY_REVOKED,
        "checkout-api",
        NOW + timedelta(days=3),
    )


async def test_revoking_twice_is_audited_once(service: ApiKeyService, uow: FakeUnitOfWork) -> None:
    issued = await service.issue_admin_key(CLI, name=Name("Release tooling"))
    await service.revoke(CLI, issued.key.id)

    await service.revoke(CLI, issued.key.id)

    actions = [entry.action for entry in uow.committed.audit]
    assert actions.count(AuditAction.API_KEY_REVOKED) == 1


async def test_revoking_an_unknown_key_is_reported(service: ApiKeyService) -> None:
    with pytest.raises(ApiKeyNotFoundError):
        await service.revoke(CLI, ApiKeyId(uuid4()))


async def test_lists_keys_newest_first(service: ApiKeyService, clock: FixedClock) -> None:
    for name in ["Release tooling", "checkout-api", "search-worker"]:
        await service.issue_admin_key(CLI, name=Name(name))
        clock.advance(timedelta(minutes=1))

    keys = await service.list_keys()

    assert [str(key.name) for key in keys] == ["search-worker", "checkout-api", "Release tooling"]
