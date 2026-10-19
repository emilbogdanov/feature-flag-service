import pytest
from httpx import AsyncClient

from flagstaff_server.api.app import openapi_schema
from flagstaff_server.application.api_keys import ApiKeyService
from flagstaff_server.domain.audit import Actor
from flagstaff_server.domain.values import Name
from tests.api.conftest import Headers, bearer
from tests.unit.application.fakes import FakeUnitOfWork, FixedClock


# An admin key exists, so the refusals below are about the key and not an empty system.
@pytest.mark.usefixtures("as_admin")
@pytest.mark.parametrize(
    "headers",
    [
        {},
        bearer("fs_admin_made-up"),
        {"Authorization": "Basic cmVsZWFzZTpzZWNyZXQ="},
    ],
)
async def test_requests_without_a_valid_key_are_refused(
    http: AsyncClient, headers: Headers
) -> None:
    response = await http.get("/projects", headers=headers)

    assert response.status_code == 401
    assert response.json() == {
        "detail": "API key is missing, unknown or revoked",
        "code": "invalid_api_key",
    }
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_a_revoked_admin_key_is_refused(
    http: AsyncClient, uow: FakeUnitOfWork, clock: FixedClock
) -> None:
    keys = ApiKeyService(uow, clock)
    issued = await keys.issue_admin_key(Actor.command_line(), name=Name("Old laptop"))
    await keys.revoke(Actor.command_line(), issued.key.id)

    response = await http.get("/projects", headers=bearer(issued.secret))

    assert response.status_code == 401


async def test_an_sdk_key_cannot_manage_anything(http: AsyncClient, as_prod_sdk: Headers) -> None:
    listed = await http.get("/projects", headers=as_prod_sdk)
    created = await http.post("/projects", json={"key": "x", "name": "X"}, headers=as_prod_sdk)

    assert listed.status_code == created.status_code == 403
    assert listed.json() == {"detail": "this endpoint needs an admin key", "code": "forbidden"}


async def test_health_needs_no_key(http: AsyncClient) -> None:
    response = await http.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_the_schema_builds_without_a_database() -> None:
    schema = openapi_schema()

    assert schema["info"]["title"] == "Flagstaff"
    assert "/projects" in schema["paths"]
