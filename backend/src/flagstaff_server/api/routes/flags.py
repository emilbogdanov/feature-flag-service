from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response, status

from flagstaff_server.api.dependencies import AdminActor, ContainerDep, require_admin
from flagstaff_server.api.errors import error_responses
from flagstaff_server.api.schemas.flags import (
    ChangeFlagDetails,
    ChangeVariants,
    CreateFlag,
    FlagResponse,
    TargetingSchema,
    variants_of,
)
from flagstaff_server.api.versions import etag, expected_version
from flagstaff_server.domain.flags import Flag
from flagstaff_server.domain.values import Description, Name, Slug

router = APIRouter(
    prefix="/projects/{project_key}/flags",
    tags=["flags"],
    dependencies=[Depends(require_admin)],
    responses=error_responses(401, 403, 404, 422),
)

IfMatch = Annotated[
    str | None,
    Header(description='The ETag from the last read of the flag, such as "3".'),
]
_VERSIONED = error_responses(409, 412, 428)
_UNVERSIONED = error_responses(409, 412)


@router.post("", status_code=status.HTTP_201_CREATED, responses=error_responses(409))
async def create_flag(
    project_key: str,
    *,
    body: CreateFlag,
    actor: AdminActor,
    container: ContainerDep,
    response: Response,
) -> FlagResponse:
    flag = await container.flags().create_flag(
        actor,
        Slug(project_key),
        key=body.key,
        name=Name(body.name),
        description=Description(body.description),
        kind=body.kind,
        variants=variants_of(body.variants),
        off_variant=body.off_variant,
        on_variant=body.on_variant,
    )
    response.headers["Location"] = f"/projects/{project_key}/flags/{flag.key}"
    return await _respond(container, project_key, flag, response)


@router.get("")
async def list_flags(project_key: str, container: ContainerDep) -> list[FlagResponse]:
    flags = await container.flags().list_flags(Slug(project_key))
    environments = await container.projects().list_environments(Slug(project_key))
    return [FlagResponse.of(flag, environments) for flag in flags]


@router.get("/{flag_key}")
async def get_flag(
    project_key: str, flag_key: str, container: ContainerDep, response: Response
) -> FlagResponse:
    flag = await container.flags().get_flag(Slug(project_key), flag_key)
    return await _respond(container, project_key, flag, response)


@router.patch("/{flag_key}", responses=_VERSIONED)
async def change_details(
    project_key: str,
    flag_key: str,
    *,
    body: ChangeFlagDetails,
    actor: AdminActor,
    container: ContainerDep,
    response: Response,
    if_match: IfMatch = None,
) -> FlagResponse:
    flag = await container.flags().change_details(
        actor,
        Slug(project_key),
        flag_key,
        name=Name(body.name),
        description=Description(body.description),
        expected_version=expected_version(if_match, required=True),
    )
    return await _respond(container, project_key, flag, response)


@router.put("/{flag_key}/variants", responses=_VERSIONED)
async def change_variants(
    project_key: str,
    flag_key: str,
    *,
    body: ChangeVariants,
    actor: AdminActor,
    container: ContainerDep,
    response: Response,
    if_match: IfMatch = None,
) -> FlagResponse:
    flag = await container.flags().change_variants(
        actor,
        Slug(project_key),
        flag_key,
        variants=variants_of(body.variants),
        expected_version=expected_version(if_match, required=True),
    )
    return await _respond(container, project_key, flag, response)


@router.put("/{flag_key}/environments/{environment_key}/targeting", responses=_VERSIONED)
async def change_targeting(
    project_key: str,
    flag_key: str,
    environment_key: str,
    *,
    body: TargetingSchema,
    actor: AdminActor,
    container: ContainerDep,
    response: Response,
    if_match: IfMatch = None,
) -> FlagResponse:
    flag = await container.flags().change_targeting(
        actor,
        Slug(project_key),
        flag_key,
        Slug(environment_key),
        targeting=body.to_targeting(),
        expected_version=expected_version(if_match, required=True),
    )
    return await _respond(container, project_key, flag, response)


# Switching and archiving take If-Match too, but don't insist on it: a kill switch has to work
# from a script that never read the flag.
@router.post("/{flag_key}/environments/{environment_key}/enable", responses=_UNVERSIONED)
async def enable(
    project_key: str,
    flag_key: str,
    environment_key: str,
    *,
    actor: AdminActor,
    container: ContainerDep,
    response: Response,
    if_match: IfMatch = None,
) -> FlagResponse:
    flag = await container.flags().enable(
        actor,
        Slug(project_key),
        flag_key,
        Slug(environment_key),
        expected_version=expected_version(if_match, required=False),
    )
    return await _respond(container, project_key, flag, response)


@router.post("/{flag_key}/environments/{environment_key}/disable", responses=_UNVERSIONED)
async def disable(
    project_key: str,
    flag_key: str,
    environment_key: str,
    *,
    actor: AdminActor,
    container: ContainerDep,
    response: Response,
    if_match: IfMatch = None,
) -> FlagResponse:
    flag = await container.flags().disable(
        actor,
        Slug(project_key),
        flag_key,
        Slug(environment_key),
        expected_version=expected_version(if_match, required=False),
    )
    return await _respond(container, project_key, flag, response)


@router.post("/{flag_key}/archive", responses=_UNVERSIONED)
async def archive(
    project_key: str,
    flag_key: str,
    *,
    actor: AdminActor,
    container: ContainerDep,
    response: Response,
    if_match: IfMatch = None,
) -> FlagResponse:
    flag = await container.flags().archive(
        actor,
        Slug(project_key),
        flag_key,
        expected_version=expected_version(if_match, required=False),
    )
    return await _respond(container, project_key, flag, response)


async def _respond(
    container: ContainerDep, project_key: str, flag: Flag, response: Response
) -> FlagResponse:
    response.headers["ETag"] = etag(flag.version)
    environments = await container.projects().list_environments(Slug(project_key))
    return FlagResponse.of(flag, environments)
