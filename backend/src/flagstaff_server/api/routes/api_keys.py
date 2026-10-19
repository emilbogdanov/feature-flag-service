from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from flagstaff_server.api.dependencies import AdminActor, ContainerDep, require_admin
from flagstaff_server.api.errors import error_responses
from flagstaff_server.api.schemas.api_keys import ApiKeyResponse, IssueApiKey, IssuedApiKeyResponse
from flagstaff_server.application.api_keys import IssuedApiKey
from flagstaff_server.domain.api_keys import ApiKeyKind
from flagstaff_server.domain.errors import InvalidValueError
from flagstaff_server.domain.ids import ApiKeyId
from flagstaff_server.domain.values import Name, Slug

router = APIRouter(
    prefix="/api-keys",
    tags=["api keys"],
    dependencies=[Depends(require_admin)],
    responses=error_responses(401, 403, 422),
)


@router.post("", status_code=status.HTTP_201_CREATED, responses=error_responses(404))
async def issue_api_key(
    body: IssueApiKey, actor: AdminActor, container: ContainerDep, response: Response
) -> IssuedApiKeyResponse:
    issued = await _issue(body, actor, container)
    response.headers["Location"] = f"/api-keys/{issued.key.id}"
    # The secret is in the body, so nothing on the way may keep a copy of it.
    response.headers["Cache-Control"] = "no-store"
    return IssuedApiKeyResponse.issued(issued)


@router.get("")
async def list_api_keys(container: ContainerDep) -> list[ApiKeyResponse]:
    return [ApiKeyResponse.of(scoped) for scoped in await container.api_keys().list_keys()]


# Revoked keys stay listed, so the audit log's mentions of them still lead somewhere.
@router.post("/{key_id}/revoke", responses=error_responses(404))
async def revoke_api_key(
    key_id: UUID, actor: AdminActor, container: ContainerDep
) -> ApiKeyResponse:
    return ApiKeyResponse.of(await container.api_keys().revoke(actor, ApiKeyId(key_id)))


async def _issue(body: IssueApiKey, actor: AdminActor, container: ContainerDep) -> IssuedApiKey:
    keys = container.api_keys()
    if body.kind is ApiKeyKind.ADMIN:
        if body.project is not None or body.environment is not None:
            raise InvalidValueError(
                "an admin key manages everything; leave out project and environment"
            )
        return await keys.issue_admin_key(actor, name=Name(body.name))
    if body.project is None or body.environment is None:
        raise InvalidValueError("an SDK key needs the project and environment it reads")
    return await keys.issue_sdk_key(
        actor, Slug(body.project), Slug(body.environment), name=Name(body.name)
    )
