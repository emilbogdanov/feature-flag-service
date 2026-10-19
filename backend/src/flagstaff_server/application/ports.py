from collections.abc import Collection
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self

from flagstaff_server.application.audit import AuditCursor
from flagstaff_server.domain.api_keys import ApiKey
from flagstaff_server.domain.audit import AuditEntry
from flagstaff_server.domain.flags import Flag
from flagstaff_server.domain.ids import ApiKeyId, EnvironmentId, ProjectId
from flagstaff_server.domain.projects import Environment, Project
from flagstaff_server.domain.values import Slug


class Clock(Protocol):
    def now(self) -> datetime: ...


class ProjectRepository(Protocol):
    # Raises ProjectKeyTakenError if the key is taken, which a store may only find out at
    # commit, so UnitOfWork.commit() can raise it as well.
    async def add(self, project: Project) -> None: ...

    async def get_by_key(self, key: Slug) -> Project | None: ...

    # Ordered by key.
    async def list(self) -> list[Project]: ...


class EnvironmentRepository(Protocol):
    # Raises EnvironmentKeyTakenError, now or at commit, if the project already has the key.
    async def add(self, environment: Environment) -> None: ...

    async def get(self, environment_id: EnvironmentId) -> Environment | None: ...

    async def get_by_key(self, project_id: ProjectId, key: Slug) -> Environment | None: ...

    # Oldest first, so dev, staging and prod keep the order they were created in.
    async def list_for_project(self, project_id: ProjectId) -> list[Environment]: ...

    # One atomic increment per environment, so two changes committed at once each move the
    # version on instead of both landing on the same number.
    async def bump_ruleset_versions(self, environment_ids: Collection[EnvironmentId]) -> None: ...


class FlagRepository(Protocol):
    # Raises FlagKeyTakenError, now or at commit, if the project already has the key.
    async def add(self, flag: Flag) -> None: ...

    # Archived flags included: their keys stay taken.
    async def get(self, project_id: ProjectId, key: str) -> Flag | None: ...

    # Flags still in use, ordered by key.
    async def list_active(self, project_id: ProjectId) -> list[Flag]: ...

    # Saves only if the stored flag is still at flag.version, then moves flag.version on;
    # raises StaleFlagError if another change got there first.
    async def update(self, flag: Flag) -> None: ...


class ApiKeyRepository(Protocol):
    async def add(self, key: ApiKey, *, secret_hash: str) -> None: ...

    async def find_by_secret_hash(self, secret_hash: str) -> ApiKey | None: ...

    async def get(self, key_id: ApiKeyId) -> ApiKey | None: ...

    # Newest first, revoked keys included.
    async def list(self) -> list[ApiKey]: ...

    async def update(self, key: ApiKey) -> None: ...


class AuditLog(Protocol):
    # Written in the caller's transaction, so an entry exists exactly when its change does.
    async def add(self, entry: AuditEntry) -> None: ...

    # Newest first, ties broken by id descending, starting right after the cursor. With a
    # project id only that project's entries; without one, all of them.
    async def page(
        self, *, project_id: ProjectId | None, after: AuditCursor | None, limit: int
    ) -> list[AuditEntry]: ...


class UnitOfWork(Protocol):
    @property
    def projects(self) -> ProjectRepository: ...

    @property
    def environments(self) -> EnvironmentRepository: ...

    @property
    def flags(self) -> FlagRepository: ...

    @property
    def api_keys(self) -> ApiKeyRepository: ...

    @property
    def audit(self) -> AuditLog: ...

    async def __aenter__(self) -> Self: ...

    # Leaving the block without commit() rolls back.
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...
