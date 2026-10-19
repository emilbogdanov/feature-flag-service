from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from flagstaff_server.api.container import Container
from flagstaff_server.application.errors import InvalidApiKeyError, PermissionDeniedError
from flagstaff_server.domain.api_keys import ApiKey
from flagstaff_server.domain.audit import Actor
from flagstaff_server.domain.ids import EnvironmentId

_bearer = HTTPBearer(
    auto_error=False,
    description="An admin key for the management API, an SDK key for /sdk.",
)


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


async def get_current_key(
    container: ContainerDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> ApiKey:
    # auto_error is off so a missing key goes through the same 401 path as a wrong one.
    if credentials is None:
        raise InvalidApiKeyError
    return await container.authenticated_keys.authenticate(credentials.credentials)


CurrentKey = Annotated[ApiKey, Depends(get_current_key)]


# FastAPI resolves get_current_key once per request, so a route that also asks for the actor
# doesn't authenticate twice.
async def require_admin(key: CurrentKey) -> Actor:
    if not key.can_manage:
        raise PermissionDeniedError("this endpoint needs an admin key")
    return Actor.of(key)


AdminActor = Annotated[Actor, Depends(require_admin)]


async def require_sdk_environment(key: CurrentKey) -> EnvironmentId:
    if key.environment_id is None:
        raise PermissionDeniedError(
            "this endpoint needs an SDK key; admin keys read rulesets under /projects"
        )
    return key.environment_id


SdkEnvironment = Annotated[EnvironmentId, Depends(require_sdk_environment)]
