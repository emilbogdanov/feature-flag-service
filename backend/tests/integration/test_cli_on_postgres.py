import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from flagstaff_server.application.api_keys import ApiKeyService
from flagstaff_server.application.audit import AuditService
from flagstaff_server.cli import main
from flagstaff_server.domain.audit import AuditAction
from flagstaff_server.infrastructure.clock import SystemClock
from flagstaff_server.infrastructure.db.unit_of_work import SqlUnitOfWork


async def test_issues_an_admin_key_that_the_api_accepts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    database_url: str,
    redis_url: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    monkeypatch.setenv("FLAGSTAFF_DATABASE_URL", database_url)
    monkeypatch.setenv("FLAGSTAFF_REDIS_URL", redis_url)

    # main runs its own event loop, so it can't share the test's.
    assert await asyncio.to_thread(main, ["create-admin-key", "--name", "Release tooling"]) == 0

    secret = capsys.readouterr().out.strip()
    key = await ApiKeyService(SqlUnitOfWork(session_factory), SystemClock()).authenticate(secret)
    assert key.can_manage
    [entry] = (await AuditService(SqlUnitOfWork(session_factory)).list_entries(limit=10)).entries
    assert (entry.action, entry.actor.name) == (AuditAction.API_KEY_ISSUED, "command line")
