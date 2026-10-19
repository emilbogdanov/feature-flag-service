from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from flagstaff.engine.errors import InvalidFlagError

from flagstaff_server.api.schemas.common import ErrorResponse
from flagstaff_server.application.errors import (
    ApiKeyNotFoundError,
    InvalidApiKeyError,
    PermissionDeniedError,
    StaleFlagError,
)
from flagstaff_server.domain.errors import (
    ArchivedFlagError,
    EnvironmentKeyTakenError,
    EnvironmentNotFoundError,
    FlagKeyTakenError,
    FlagNotFoundError,
    InvalidTargetingError,
    InvalidValueError,
    ProjectKeyTakenError,
    ProjectNotFoundError,
)

# The one place where business errors become HTTP responses. The code is stable and meant for
# clients to branch on; the message is for people.
ERROR_RESPONSES: dict[type[Exception], tuple[int, str]] = {
    InvalidValueError: (422, "invalid_value"),
    InvalidTargetingError: (422, "invalid_targeting"),
    # The engine's own check of a targeting or variants body, with the path of the bad part.
    InvalidFlagError: (422, "invalid_targeting"),
    InvalidApiKeyError: (401, "invalid_api_key"),
    PermissionDeniedError: (403, "forbidden"),
    ProjectNotFoundError: (404, "project_not_found"),
    EnvironmentNotFoundError: (404, "environment_not_found"),
    FlagNotFoundError: (404, "flag_not_found"),
    ApiKeyNotFoundError: (404, "api_key_not_found"),
    ProjectKeyTakenError: (409, "project_key_taken"),
    EnvironmentKeyTakenError: (409, "environment_key_taken"),
    FlagKeyTakenError: (409, "flag_key_taken"),
    ArchivedFlagError: (409, "flag_archived"),
    StaleFlagError: (412, "version_mismatch"),
}


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI entries so generated clients know every error has the ErrorResponse shape."""
    return {status_code: {"model": ErrorResponse} for status_code in status_codes}


def register_error_handlers(app: FastAPI) -> None:
    for error_type in ERROR_RESPONSES:
        app.add_exception_handler(error_type, _to_response)
    app.exception_handler(RequestValidationError)(_malformed_request)
    # Everything else is a bug, including a business error nobody mapped. Starlette answers it
    # with this handler and then re-raises it, so the server logs the full traceback.
    app.add_exception_handler(Exception, _unexpected)


# FastAPI's default 422 body has a different shape from every other error. Clients get one
# shape to handle instead, with the per-field details kept under "errors".
async def _malformed_request(_: Request, error: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        {
            "detail": "request is malformed",
            "code": "invalid_request",
            "errors": jsonable_encoder(error.errors()),
        },
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


async def _to_response(_: Request, error: Exception) -> JSONResponse:
    # Handlers are registered per mapped type, so one of the error's classes is in the table,
    # and walking the MRO picks the most specific mapping.
    status_code, code = next(
        ERROR_RESPONSES[cls] for cls in type(error).__mro__ if cls in ERROR_RESPONSES
    )
    return JSONResponse(
        {"detail": str(error), "code": code},
        status_code=status_code,
        headers={"WWW-Authenticate": "Bearer"}
        if status_code == status.HTTP_401_UNAUTHORIZED
        else None,
    )


async def _unexpected(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse(
        {"detail": "internal error", "code": "internal"},
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
