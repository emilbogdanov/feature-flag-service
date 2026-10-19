from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from flagstaff_server.domain.values import Name, Slug

if TYPE_CHECKING:
    from datetime import datetime

    from flagstaff_server.domain.ids import EnvironmentId, ProjectId


@dataclass(frozen=True, slots=True, kw_only=True)
class Project:
    id: ProjectId
    key: Slug
    name: Name
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class Environment:
    id: EnvironmentId
    project_id: ProjectId
    key: Slug
    name: Name
    created_at: datetime
    # Goes up by one with every change that alters what an SDK in this environment evaluates,
    # so an SDK can tell from one number whether the rules it holds are current.
    ruleset_version: int = 0


# Every new project starts with these; more can be added to a project later.
STANDARD_ENVIRONMENTS: Final = (
    (Slug("dev"), Name("Development")),
    (Slug("staging"), Name("Staging")),
    (Slug("prod"), Name("Production")),
)
