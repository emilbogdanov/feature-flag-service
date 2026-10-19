from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from flagstaff_server.application.api_keys import ApiKeyService
from flagstaff_server.application.audit import AuditService
from flagstaff_server.application.flags import FlagService
from flagstaff_server.application.ports import Clock, UnitOfWork
from flagstaff_server.application.projects import ProjectService
from flagstaff_server.application.rulesets import RulesetService


async def _nothing_to_close() -> None:
    return None


# Everything a request needs, built once at start-up. Services are cheap and get a fresh unit
# of work each, so no transaction is ever shared between two requests.
@dataclass(frozen=True, slots=True, kw_only=True)
class Container:
    uow_factory: Callable[[], UnitOfWork]
    clock: Clock
    close: Callable[[], Awaitable[None]] = _nothing_to_close

    def projects(self) -> ProjectService:
        return ProjectService(self.uow_factory(), self.clock)

    def flags(self) -> FlagService:
        return FlagService(self.uow_factory(), self.clock)

    def api_keys(self) -> ApiKeyService:
        return ApiKeyService(self.uow_factory(), self.clock)

    def audit(self) -> AuditService:
        return AuditService(self.uow_factory())

    def rulesets(self) -> RulesetService:
        return RulesetService(self.uow_factory())
