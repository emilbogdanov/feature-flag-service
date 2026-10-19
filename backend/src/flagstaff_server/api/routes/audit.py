from typing import Annotated

from fastapi import APIRouter, Depends, Query

from flagstaff_server.api.cursors import decode_cursor, encode_cursor
from flagstaff_server.api.dependencies import ContainerDep, require_admin
from flagstaff_server.api.errors import error_responses
from flagstaff_server.api.schemas.audit import AuditEntryResponse, AuditPageResponse
from flagstaff_server.application.audit import MAX_PAGE_SIZE
from flagstaff_server.domain.values import Slug

router = APIRouter(
    prefix="/audit",
    tags=["audit"],
    dependencies=[Depends(require_admin)],
    responses=error_responses(401, 403, 404, 422),
)


@router.get("")
async def list_audit_entries(
    container: ContainerDep,
    project: Annotated[str | None, Query(description="Only this project's changes.")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
    cursor: Annotated[str | None, Query(description="next_cursor from the previous page")] = None,
) -> AuditPageResponse:
    page = await container.audit().list_entries(
        project_key=Slug(project) if project is not None else None,
        after=decode_cursor(cursor) if cursor is not None else None,
        limit=limit,
    )
    return AuditPageResponse(
        entries=[AuditEntryResponse.of(entry, page) for entry in page.entries],
        next_cursor=encode_cursor(page.next_cursor) if page.next_cursor is not None else None,
    )
