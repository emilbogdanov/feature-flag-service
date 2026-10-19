from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from flagstaff.engine.ruleset import Ruleset

from flagstaff_server.application.lookups import require_environment, require_project

if TYPE_CHECKING:
    from collections.abc import Collection

    from flagstaff_server.application.ports import UnitOfWork
    from flagstaff_server.domain.ids import EnvironmentId
    from flagstaff_server.domain.projects import Environment
    from flagstaff_server.domain.values import Slug


# An environment's ruleset moved to a new version. Small on purpose: every API instance reads
# the rules themselves from the database, once, however many of its streams want them.
@dataclass(frozen=True, slots=True)
class RulesetChange:
    environment_id: EnvironmentId
    version: int


class RulesetService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    # For an SDK key, which names its environment by id rather than by URL.
    async def ruleset_for(self, environment_id: EnvironmentId) -> Ruleset:
        async with self._uow as uow:
            environment = await uow.environments.get(environment_id)
            # The key's foreign key guarantees the environment; losing it would be a bug.
            if environment is None:
                raise LookupError(f"environment {environment_id} has disappeared")
            return await self._build(uow, environment)

    # Unknown ids are left out.
    async def current_versions(
        self, environment_ids: Collection[EnvironmentId]
    ) -> dict[EnvironmentId, int]:
        async with self._uow as uow:
            environments = await uow.environments.get_many(environment_ids)
        return {i: environment.ruleset_version for i, environment in environments.items()}

    async def ruleset_in(self, project_key: Slug, environment_key: Slug) -> Ruleset:
        async with self._uow as uow:
            project = await require_project(uow, project_key)
            environment = await require_environment(uow, project, environment_key)
            return await self._build(uow, environment)

    # The environment, and with it the version, is read before the flags. A change committed
    # in between leaves flags newer than the version they go out under, never older, so the
    # worst an SDK does is fetch the same rules once more.
    async def _build(self, uow: UnitOfWork, environment: Environment) -> Ruleset:
        flags = await uow.flags.list_active(environment.project_id)
        return Ruleset.of(
            environment.ruleset_version, [flag.compile_for(environment.id) for flag in flags]
        )
