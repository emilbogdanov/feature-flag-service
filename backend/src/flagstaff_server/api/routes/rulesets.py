import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Response, status
from flagstaff.engine.ruleset import Ruleset
from flagstaff.engine.wire import ruleset_to_document

from flagstaff_server.api.dependencies import ContainerDep, SdkEnvironment, require_admin
from flagstaff_server.api.errors import error_responses
from flagstaff_server.api.schemas.rulesets import (
    EvaluateRequest,
    EvaluationResponse,
    EvaluationsResponse,
    RulesetSchema,
)
from flagstaff_server.api.versions import etag
from flagstaff_server.domain.values import Slug

router = APIRouter(tags=["rulesets"], responses=error_responses(401, 403, 422))
_admin_only = [Depends(require_admin)]
_RULESET: dict[int | str, dict[str, Any]] = {
    200: {"model": RulesetSchema, "description": "The environment's ruleset."},
    304: {"description": "The ruleset is still at the version in If-None-Match."},
}

IfNoneMatch = Annotated[
    str | None, Header(description="The ETag of the ruleset the SDK already holds.")
]


@router.get("/sdk/ruleset", responses=_RULESET, response_class=Response)
async def sdk_ruleset(
    environment: SdkEnvironment, container: ContainerDep, if_none_match: IfNoneMatch = None
) -> Response:
    # Most polls come from SDKs that already hold the current rules. The version alone tells
    # them so, without loading and compiling every flag in the project, and this instance
    # usually knows it without asking the database.
    if if_none_match is not None:
        version = (await container.broadcaster.current_versions([environment])).get(environment)
        if version is not None and _is_held(version, if_none_match):
            return _not_modified(version)
    return _ruleset_response(await container.rulesets().ruleset_for(environment), if_none_match)


@router.post("/sdk/evaluate")
async def sdk_evaluate(
    body: EvaluateRequest, environment: SdkEnvironment, container: ContainerDep
) -> EvaluationsResponse:
    return _evaluate(await container.rulesets().ruleset_for(environment), body)


@router.get(
    "/projects/{project_key}/environments/{environment_key}/ruleset",
    dependencies=_admin_only,
    responses={**_RULESET, **error_responses(404)},
    response_class=Response,
)
async def environment_ruleset(
    project_key: str,
    environment_key: str,
    container: ContainerDep,
    if_none_match: IfNoneMatch = None,
) -> Response:
    ruleset = await container.rulesets().ruleset_in(Slug(project_key), Slug(environment_key))
    return _ruleset_response(ruleset, if_none_match)


# What the dashboard uses to answer "what would this user get in prod right now?"
@router.post(
    "/projects/{project_key}/environments/{environment_key}/evaluate",
    dependencies=_admin_only,
    responses=error_responses(404),
)
async def environment_evaluate(
    project_key: str, environment_key: str, body: EvaluateRequest, container: ContainerDep
) -> EvaluationsResponse:
    ruleset = await container.rulesets().ruleset_in(Slug(project_key), Slug(environment_key))
    return _evaluate(ruleset, body)


def _ruleset_response(ruleset: Ruleset, if_none_match: str | None) -> Response:
    if if_none_match is not None and _is_held(ruleset.version, if_none_match):
        return _not_modified(ruleset.version)
    # Serialised straight from the engine's document: running a large ruleset through response
    # validation on every SDK start would cost more than building it.
    body = json.dumps(ruleset_to_document(ruleset), separators=(",", ":"))
    return Response(body, media_type="application/json", headers=_headers(ruleset.version))


def _is_held(version: int, if_none_match: str) -> bool:
    return etag(version) in {part.strip() for part in if_none_match.split(",")}


def _not_modified(version: int) -> Response:
    return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=_headers(version))


# The answer depends on the key as much as the URL, and must be revalidated every time: a
# cached ruleset is exactly the stale rules this endpoint exists to replace.
def _headers(version: int) -> dict[str, str]:
    return {"ETag": etag(version), "Cache-Control": "private, no-cache", "Vary": "Authorization"}


def _evaluate(ruleset: Ruleset, body: EvaluateRequest) -> EvaluationsResponse:
    context = body.context.to_context()
    keys = body.flags if body.flags is not None else sorted(ruleset.flags)
    evaluations = {key: ruleset.evaluate(key, context) for key in keys}
    return EvaluationsResponse(
        version=ruleset.version,
        evaluations={
            key: EvaluationResponse.of(evaluation)
            for key, evaluation in evaluations.items()
            if evaluation is not None
        },
    )
