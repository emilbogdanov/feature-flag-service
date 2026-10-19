# Services address projects, environments and flags by the keys in a URL; these turn a key into
# the thing it names, or into the error the API reports as not found.
from __future__ import annotations

from typing import TYPE_CHECKING

from flagstaff_server.domain.errors import EnvironmentNotFoundError, ProjectNotFoundError

if TYPE_CHECKING:
    from flagstaff_server.application.ports import UnitOfWork
    from flagstaff_server.domain.projects import Environment, Project
    from flagstaff_server.domain.values import Slug


async def require_project(uow: UnitOfWork, key: Slug) -> Project:
    project = await uow.projects.get_by_key(key)
    if project is None:
        raise ProjectNotFoundError(key)
    return project


async def require_environment(uow: UnitOfWork, project: Project, key: Slug) -> Environment:
    environment = await uow.environments.get_by_key(project.id, key)
    if environment is None:
        raise EnvironmentNotFoundError(project.key, key)
    return environment
