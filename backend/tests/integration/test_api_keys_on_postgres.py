from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from flagstaff_server.domain.api_keys import ApiKey, ApiKeyKind
from flagstaff_server.domain.audit import Actor, AuditAction, AuditEntry
from flagstaff_server.domain.ids import ApiKeyId, AuditEntryId
from flagstaff_server.domain.values import Name
from flagstaff_server.infrastructure.db.api_keys import SqlApiKeyRepository
from flagstaff_server.infrastructure.db.audit import SqlAuditLog
from flagstaff_server.infrastructure.db.tables import AuditEntryRow
from tests.integration.storefront import CREATED_AT, Storefront, store_storefront


@pytest.fixture
async def storefront(session_factory: async_sessionmaker[AsyncSession]) -> Storefront:
    return await store_storefront(session_factory)


def sdk_key(storefront: Storefront, name: str = "checkout-api") -> ApiKey:
    return ApiKey.sdk(
        key_id=ApiKeyId(uuid4()),
        name=Name(name),
        environment_id=storefront.prod.id,
        at=CREATED_AT,
    )


async def test_finds_a_key_by_its_secret_hash(
    session_factory: async_sessionmaker[AsyncSession], storefront: Storefront
) -> None:
    key = sdk_key(storefront)
    async with session_factory() as session:
        await SqlApiKeyRepository(session).add(key, secret_hash="a" * 64)
        await session.commit()

    async with session_factory() as session:
        found = await SqlApiKeyRepository(session).find_by_secret_hash("a" * 64)
        missing = await SqlApiKeyRepository(session).find_by_secret_hash("b" * 64)

    assert found is not None
    assert (found.id, found.kind, found.name) == (key.id, ApiKeyKind.SDK, Name("checkout-api"))
    assert (found.environment_id, found.created_at, found.revoked_at) == (
        storefront.prod.id,
        CREATED_AT,
        None,
    )
    assert missing is None


async def test_a_revocation_is_saved(
    session_factory: async_sessionmaker[AsyncSession], storefront: Storefront
) -> None:
    key = sdk_key(storefront)
    async with session_factory() as session:
        await SqlApiKeyRepository(session).add(key, secret_hash="a" * 64)
        await session.commit()

    key.revoke(at=CREATED_AT + timedelta(days=2))
    async with session_factory() as session:
        await SqlApiKeyRepository(session).update(key)
        await session.commit()

    async with session_factory() as session:
        found = await SqlApiKeyRepository(session).get(key.id)
    assert found is not None
    assert found.revoked_at == CREATED_AT + timedelta(days=2)
    assert not found.can_read(storefront.prod.id)


async def test_lists_keys_newest_first(
    session_factory: async_sessionmaker[AsyncSession], storefront: Storefront
) -> None:
    admin = ApiKey.admin(
        key_id=ApiKeyId(uuid4()), name=Name("Release tooling"), at=CREATED_AT + timedelta(hours=1)
    )
    async with session_factory() as session:
        repository = SqlApiKeyRepository(session)
        await repository.add(sdk_key(storefront), secret_hash="a" * 64)
        await repository.add(admin, secret_hash="b" * 64)
        await session.commit()

    async with session_factory() as session:
        keys = await SqlApiKeyRepository(session).list()

    assert [str(key.name) for key in keys] == ["Release tooling", "checkout-api"]
    assert keys[0].environment_id is None


async def test_the_database_refuses_an_sdk_key_without_an_environment(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        with pytest.raises(IntegrityError, match="ck_api_keys_sdk_keys_have_an_environment"):
            await session.execute(
                text(
                    "INSERT INTO api_keys (id, kind, name, secret_hash, created_at)"
                    " VALUES (gen_random_uuid(), 'sdk', 'checkout-api', :hash, now())"
                ),
                {"hash": "c" * 64},
            )


async def test_audit_entries_keep_their_changes_as_json(
    session_factory: async_sessionmaker[AsyncSession], storefront: Storefront
) -> None:
    entry = AuditEntry(
        id=AuditEntryId(uuid4()),
        action=AuditAction.FLAG_ENABLED,
        actor=Actor(ApiKeyId(uuid4()), "Release tooling"),
        at=CREATED_AT,
        project_id=storefront.project.id,
        environment_id=storefront.prod.id,
        subject="new-checkout",
        changes={"name": {"before": "New checkout", "after": "Checkout v2"}, "seats": [5, 10.5]},
    )
    async with session_factory() as session:
        await SqlAuditLog(session).add(entry)
        await session.commit()

    async with session_factory() as session:
        row = await session.scalar(select(AuditEntryRow).where(AuditEntryRow.id == entry.id))

    assert row is not None
    assert (row.action, row.actor_name, row.subject) == (
        AuditAction.FLAG_ENABLED,
        "Release tooling",
        "new-checkout",
    )
    assert row.changes == entry.changes
