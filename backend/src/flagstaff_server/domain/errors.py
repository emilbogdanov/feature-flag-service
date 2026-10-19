from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flagstaff_server.domain.ids import EnvironmentId
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


class FlagNotFoundError(DomainError):
    def __init__(self, project_key: Slug, key: str) -> None:
        super().__init__(f"project {str(project_key)!r} has no flag {key!r}")
        self.project_key = project_key
        self.key = key


class FlagKeyTakenError(DomainError):
    def __init__(self, project_key: Slug, key: str) -> None:
        super().__init__(f"project {str(project_key)!r} already has a flag {key!r}")
        self.project_key = project_key
        self.key = key


# Raised when a change would leave a flag that the engine can't evaluate in some environment,
# such as a rule serving a variant the flag no longer has. environment_id names the environment
# whose targeting it would break; the domain only knows ids, so services put the key in front
# when the caller didn't name that environment themselves.
class InvalidTargetingError(DomainError):
    def __init__(self, reason: str, *, environment_id: EnvironmentId | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.environment_id = environment_id


class ArchivedFlagError(DomainError):
    def __init__(self, key: str) -> None:
        super().__init__(f"flag {key!r} is archived and can no longer be changed")
        self.key = key
