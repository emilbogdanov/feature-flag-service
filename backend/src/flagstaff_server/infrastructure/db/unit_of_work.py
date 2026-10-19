from dataclasses import dataclass
from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from flagstaff_server.infrastructure.db.api_keys import SqlApiKeyRepository
from flagstaff_server.infrastructure.db.audit import SqlAuditLog
from flagstaff_server.infrastructure.db.flags import SqlFlagRepository
from flagstaff_server.infrastructure.db.projects import (
    SqlEnvironmentRepository,
    SqlProjectRepository,
)


@dataclass(frozen=True, slots=True)
class _Transaction:
    session: AsyncSession
    projects: SqlProjectRepository
    environments: SqlEnvironmentRepository
    flags: SqlFlagRepository
    api_keys: SqlApiKeyRepository
    audit: SqlAuditLog


class SqlUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._transaction: _Transaction | None = None

    @property
    def projects(self) -> SqlProjectRepository:
        return self._active().projects

    @property
    def environments(self) -> SqlEnvironmentRepository:
        return self._active().environments

    @property
    def flags(self) -> SqlFlagRepository:
        return self._active().flags

    @property
    def api_keys(self) -> SqlApiKeyRepository:
        return self._active().api_keys

    @property
    def audit(self) -> SqlAuditLog:
        return self._active().audit

    async def __aenter__(self) -> Self:
        if self._transaction is not None:
            raise RuntimeError("unit of work is already in use; blocks can't be nested")
        session = self._session_factory()
        self._transaction = _Transaction(
            session=session,
            projects=SqlProjectRepository(session),
            environments=SqlEnvironmentRepository(session),
            flags=SqlFlagRepository(session),
            api_keys=SqlApiKeyRepository(session),
            audit=SqlAuditLog(session),
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        transaction, self._transaction = self._active(), None
        # Closing rolls back whatever was not committed and releases the row locks.
        await transaction.session.close()

    async def commit(self) -> None:
        await self._active().session.commit()

    def _active(self) -> _Transaction:
        if self._transaction is None:
            raise RuntimeError("unit of work used outside 'async with'")
        return self._transaction
