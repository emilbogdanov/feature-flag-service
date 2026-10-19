from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flagstaff_server.domain.values import Slug


# The API maps each DomainError subclass to an HTTP status in a single place, so the domain
# never needs to know about HTTP.
class DomainError(Exception):
    pass


class InvalidValueError(DomainError):
    pass


class ProjectNotFoundError(DomainError):
    def __init__(self, key: Slug) -> None:
        super().__init__(f"project {str(key)!r} does not exist")
        self.key = key


class ProjectKeyTakenError(DomainError):
    def __init__(self, key: Slug) -> None:
        super().__init__(f"a project with key {str(key)!r} already exists")
        self.key = key


class EnvironmentNotFoundError(DomainError):
    def __init__(self, project_key: Slug, key: Slug) -> None:
        super().__init__(f"project {str(project_key)!r} has no environment {str(key)!r}")
        self.project_key = project_key
        self.key = key


class EnvironmentKeyTakenError(DomainError):
    def __init__(self, project_key: Slug, key: Slug) -> None:
        super().__init__(f"project {str(project_key)!r} already has an environment {str(key)!r}")
        self.project_key = project_key
        self.key = key
