from collections.abc import Callable, Collection
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from types import TracebackType
from typing import Self

from flagstaff_server.domain.audit import AuditEntry
from flagstaff_server.domain.errors import EnvironmentKeyTakenError, ProjectKeyTakenError
from flagstaff_server.domain.ids import EnvironmentId, ProjectId
from flagstaff_server.domain.projects import Environment, Project
from flagstaff_server.domain.values import Slug


@dataclass
class ServerState:
    projects: dict[ProjectId, Project] = field(default_factory=dict)
    environments: dict[EnvironmentId, Environment] = field(default_factory=dict)
    audit: list[AuditEntry] = field(default_factory=list)


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


class InMemoryProjectRepository:
    def __init__(self, state: ServerState) -> None:
        self._state = state

    async def add(self, project: Project) -> None:
        if any(stored.key == project.key for stored in self._state.projects.values()):
            raise ProjectKeyTakenError(project.key)
        self._state.projects[project.id] = project

    async def get_by_key(self, key: Slug) -> Project | None:
        return next((p for p in self._state.projects.values() if p.key == key), None)

    async def list(self) -> list[Project]:
        return sorted(self._state.projects.values(), key=lambda project: project.key.value)


class InMemoryEnvironmentRepository:
    def __init__(self, state: ServerState) -> None:
        self._state = state

    async def add(self, environment: Environment) -> None:
        if await self.get_by_key(environment.project_id, environment.key) is not None:
            project = self._state.projects[environment.project_id]
            raise EnvironmentKeyTakenError(project.key, environment.key)
        self._state.environments[environment.id] = environment

    async def get_by_key(self, project_id: ProjectId, key: Slug) -> Environment | None:
        return next(
            (
                environment
                for environment in self._state.environments.values()
                if environment.project_id == project_id and environment.key == key
            ),
            None,
        )

    async def list_for_project(self, project_id: ProjectId) -> list[Environment]:
        return [e for e in self._state.environments.values() if e.project_id == project_id]

    async def bump_ruleset_versions(self, environment_ids: Collection[EnvironmentId]) -> None:
        for environment_id in environment_ids:
            environment = self._state.environments[environment_id]
            self._state.environments[environment_id] = replace(
                environment, ruleset_version=environment.ruleset_version + 1
            )


class InMemoryAuditLog:
    def __init__(self, state: ServerState) -> None:
        self._state = state

    async def add(self, entry: AuditEntry) -> None:
        self._state.audit.append(entry)


# Each block works on a private copy of the committed state, so leaving it without commit()
# throws its changes away, as a rolled-back transaction would.
class FakeUnitOfWork:
    def __init__(self) -> None:
        self.committed = ServerState()
        self.commits = 0
        # Runs once, right before the next commit, against the committed state: stands in for
        # a concurrent transaction that commits while this block is still running.
        self.before_next_commit: Callable[[ServerState], object] | None = None
        self._working: ServerState | None = None

    @property
    def projects(self) -> InMemoryProjectRepository:
        return InMemoryProjectRepository(self._state())

    @property
    def environments(self) -> InMemoryEnvironmentRepository:
        return InMemoryEnvironmentRepository(self._state())

    @property
    def audit(self) -> InMemoryAuditLog:
        return InMemoryAuditLog(self._state())

    async def __aenter__(self) -> Self:
        assert self._working is None, "unit of work entered twice"
        self._working = deepcopy(self.committed)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._working = None

    async def commit(self) -> None:
        working = self._state()
        if self.before_next_commit is not None:
            self.before_next_commit(self.committed)
            self.before_next_commit = None
        self.committed = deepcopy(working)
        self.commits += 1

    def _state(self) -> ServerState:
        assert self._working is not None, "repository used outside a unit of work"
        return self._working
