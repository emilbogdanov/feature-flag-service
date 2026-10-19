from httpx import AsyncClient

from tests.api.conftest import Headers


async def create_storefront(http: AsyncClient, headers: Headers) -> None:
    response = await http.post(
        "/projects", json={"key": "storefront", "name": "Storefront"}, headers=headers
    )
    assert response.status_code == 201


async def test_creates_a_project_with_three_environments(
    http: AsyncClient, as_admin: Headers
) -> None:
    created = await http.post(
        "/projects", json={"key": "storefront", "name": "Storefront"}, headers=as_admin
    )
    environments = await http.get("/projects/storefront/environments", headers=as_admin)

    assert created.status_code == 201
    assert created.headers["Location"] == "/projects/storefront"
    assert created.json() == {
        "key": "storefront",
        "name": "Storefront",
        "created_at": "2026-10-19T09:30:00Z",
    }
    assert [(e["key"], e["name"], e["ruleset_version"]) for e in environments.json()] == [
        ("dev", "Development", 0),
        ("staging", "Staging", 0),
        ("prod", "Production", 0),
    ]


async def test_lists_and_reads_projects(http: AsyncClient, as_admin: Headers) -> None:
    await create_storefront(http, as_admin)
    await http.post(
        "/projects", json={"key": "back-office", "name": "Back office"}, headers=as_admin
    )

    listed = await http.get("/projects", headers=as_admin)
    one = await http.get("/projects/back-office", headers=as_admin)

    assert [project["key"] for project in listed.json()] == ["back-office", "storefront"]
    assert one.json()["name"] == "Back office"


async def test_adds_an_environment(http: AsyncClient, as_admin: Headers) -> None:
    await create_storefront(http, as_admin)

    response = await http.post(
        "/projects/storefront/environments",
        json={"key": "eu-canary", "name": "EU canary"},
        headers=as_admin,
    )

    assert response.status_code == 201
    assert response.headers["Location"] == "/projects/storefront/environments/eu-canary"
    assert response.json()["ruleset_version"] == 0


async def test_a_taken_key_is_a_conflict(http: AsyncClient, as_admin: Headers) -> None:
    await create_storefront(http, as_admin)

    project = await http.post(
        "/projects", json={"key": "storefront", "name": "Again"}, headers=as_admin
    )
    environment = await http.post(
        "/projects/storefront/environments", json={"key": "prod", "name": "Prod"}, headers=as_admin
    )

    assert (project.status_code, project.json()["code"]) == (409, "project_key_taken")
    assert (environment.status_code, environment.json()["code"]) == (409, "environment_key_taken")


async def test_an_unknown_project_is_not_found(http: AsyncClient, as_admin: Headers) -> None:
    response = await http.get("/projects/billing/environments", headers=as_admin)

    assert response.status_code == 404
    assert response.json() == {
        "detail": "project 'billing' does not exist",
        "code": "project_not_found",
    }


async def test_a_key_that_breaks_the_rules_is_refused(http: AsyncClient, as_admin: Headers) -> None:
    response = await http.post(
        "/projects", json={"key": "Store Front", "name": "Storefront"}, headers=as_admin
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_value"


async def test_a_malformed_body_gets_the_same_error_shape(
    http: AsyncClient, as_admin: Headers
) -> None:
    response = await http.post(
        "/projects", json={"key": "storefront", "nmae": "Storefront"}, headers=as_admin
    )

    body = response.json()
    assert response.status_code == 422
    assert (body["code"], body["detail"]) == ("invalid_request", "request is malformed")
    assert {tuple(error["loc"]) for error in body["errors"]} == {
        ("body", "name"),
        ("body", "nmae"),
    }
