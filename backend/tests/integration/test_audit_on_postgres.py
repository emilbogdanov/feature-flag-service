from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from flagstaff_server.application.audit import AuditCursor
from flagstaff_server.domain.audit import Actor, AuditAction, AuditEntry
from flagstaff_server.domain.ids import AuditEntryId, ProjectId
from flagstaff_server.infrastructure.db.audit import SqlAuditLog
from tests.integration.storefront import CREATED_AT

STOREFRONT = ProjectId(uuid4())
BACK_OFFICE = ProjectId(uuid4())


def entry(minute: int, project_id: ProjectId | None, entry_id: UUID | None = None) -> AuditEntry:
    return AuditEntry(
        id=AuditEntryId(entry_id or uuid4()),
        action=AuditAction.FLAG_ENABLED,
        actor=Actor.command_line(),
        at=CREATED_AT + timedelta(minutes=minute),
        project_id=project_id,
        environment_id=None,
        subject=f"flag-{minute}",
    )


@pytest.fixture
async def log(session_factory: async_sessionmaker[AsyncSession]) -> list[AuditEntry]:
    entries = [entry(minute, STOREFRONT if minute % 2 else BACK_OFFICE) for minute in range(10)]
    # Three more in the same minute, told apart only by id.
    entries += [entry(5, STOREFRONT, UUID(int=n)) for n in (1, 2, 3)]
    async with session_factory() as session:
        for audit_entry in entries:
            await SqlAuditLog(session).add(audit_entry)
        await session.commit()
    return entries


def newest_first(entries: list[AuditEntry]) -> list[AuditEntryId]:
    return [e.id for e in sorted(entries, key=lambda e: (e.at, e.id), reverse=True)]


async def page_through(
    session: AsyncSession, project_id: ProjectId | None, size: int
) -> list[AuditEntryId]:
    seen: list[AuditEntryId] = []
    cursor = None
    while page := await SqlAuditLog(session).page(project_id=project_id, after=cursor, limit=size):
        seen += [audit_entry.id for audit_entry in page]
        cursor = AuditCursor(page[-1].at, page[-1].id)
    return seen


async def test_pages_through_the_whole_log_newest_first(
    session_factory: async_sessionmaker[AsyncSession], log: list[AuditEntry]
) -> None:
    async with session_factory() as session:
        seen = await page_through(session, None, size=4)

    assert seen == newest_first(log)


async def test_pages_through_one_project(
    session_factory: async_sessionmaker[AsyncSession], log: list[AuditEntry]
) -> None:
    async with session_factory() as session:
        seen = await page_through(session, STOREFRONT, size=2)

    assert seen == newest_first([e for e in log if e.project_id == STOREFRONT])


async def test_entries_come_back_as_they_were_written(
    session_factory: async_sessionmaker[AsyncSession], log: list[AuditEntry]
) -> None:
    async with session_factory() as session:
        [newest] = await SqlAuditLog(session).page(project_id=None, after=None, limit=1)

    assert newest == max(log, key=lambda e: (e.at, e.id))


_PAGE_QUERIES = {
    "ix_audit_entries_at_id": (
        "EXPLAIN SELECT * FROM audit_entries ORDER BY at DESC, id DESC LIMIT 50"
    ),
    "ix_audit_entries_project_id_at_id": (
        "EXPLAIN SELECT * FROM audit_entries WHERE project_id = :project"
        " ORDER BY at DESC, id DESC LIMIT 50"
    ),
}


@pytest.mark.parametrize(("index", "query"), list(_PAGE_QUERIES.items()))
async def test_each_way_of_paging_reads_its_index(
    session_factory: async_sessionmaker[AsyncSession], index: str, query: str
) -> None:
    async with session_factory() as session:
        # A handful of rows is cheaper to scan than to look up, so the planner is told not to;
        # the question here is only whether the index can serve the query at all.
        await session.execute(text("SET LOCAL enable_seqscan = off"))
        plan = await session.scalars(text(query), {"project": STOREFRONT})

        assert any(index in line for line in plan)
