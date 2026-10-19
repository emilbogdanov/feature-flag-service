from fastapi import APIRouter, Depends, Response, status

from flagstaff_server.api.dependencies import AdminActor, ContainerDep, require_admin
from flagstaff_server.api.errors import error_responses
from flagstaff_server.api.schemas.projects import (
    CreateEnvironment,
    CreateProject,
    EnvironmentResponse,
    ProjectResponse,
)
from flagstaff_server.domain.values import Name, Slug

router = APIRouter(
    prefix="/projects",
    tags=["projects"],
    dependencies=[Depends(require_admin)],
    responses=error_responses(401, 403, 422),
)


@router.post("", status_code=status.HTTP_201_CREATED, responses=error_responses(409))
async def create_project(
    body: CreateProject, actor: AdminActor, container: ContainerDep, response: Response
) -> ProjectResponse:
    project = await container.projects().create_project(
        actor, key=Slug(body.key), name=Name(body.name)
    )
    response.headers["Location"] = f"/projects/{project.key}"
    return ProjectResponse.of(project)


@router.get("")
async def list_projects(container: ContainerDep) -> list[ProjectResponse]:
    return [ProjectResponse.of(project) for project in await container.projects().list_projects()]


@router.get("/{project_key}", responses=error_responses(404))
async def get_project(project_key: str, container: ContainerDep) -> ProjectResponse:
    return ProjectResponse.of(await container.projects().get_project(Slug(project_key)))


@router.get("/{project_key}/environments", responses=error_responses(404))
async def list_environments(project_key: str, container: ContainerDep) -> list[EnvironmentResponse]:
    environments = await container.projects().list_environments(Slug(project_key))
    return [EnvironmentResponse.of(environment) for environment in environments]


@router.post(
    "/{project_key}/environments",
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(404, 409),
)
async def add_environment(
    project_key: str,
    body: CreateEnvironment,
    actor: AdminActor,
    container: ContainerDep,
    response: Response,
) -> EnvironmentResponse:
    environment = await container.projects().add_environment(
        actor, Slug(project_key), key=Slug(body.key), name=Name(body.name)
    )
    response.headers["Location"] = f"/projects/{project_key}/environments/{environment.key}"
    return EnvironmentResponse.of(environment)
