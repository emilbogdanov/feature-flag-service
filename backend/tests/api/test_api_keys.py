from datetime import timedelta

import pytest
from httpx import AsyncClient

from tests.api.conftest import Headers, bearer
from tests.unit.application.fakes import FixedClock

PROD_SDK_KEY = {
    "kind": "sdk",
    "name": "checkout-api",
    "project": "storefront",
    "environment": "prod",
}


@pytest.fixture(autouse=True)
async def storefront(http: AsyncClient, as_admin: Headers) -> None:
    await http.post("/projects", json={"key": "storefront", "name": "Storefront"}, headers=as_admin)


async def test_issues_an_sdk_key_for_one_environment(http: AsyncClient, as_admin: Headers) -> None:
    response = await http.post(
        "/api-keys",
        json={
            "kind": "sdk",
            "name": "checkout-api",
            "project": "storefront",
            "environment": "prod",
        },
        headers=as_admin,
    )

    body = response.json()
    assert response.status_code == 201
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Location"] == f"/api-keys/{body['id']}"
    assert body["secret"].startswith("fs_sdk_")
    assert (body["kind"], body["project"], body["environment"], body["revoked_at"]) == (
        "sdk",
        "storefront",
        "prod",
        None,
    )


async def test_an_issued_admin_key_works_at_once(http: AsyncClient, as_admin: Headers) -> None:
    issued = await http.post(
        "/api-keys", json={"kind": "admin", "name": "Deploy pipeline"}, headers=as_admin
    )

    response = await http.get("/projects", headers=bearer(issued.json()["secret"]))

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"kind": "sdk", "name": "checkout-api", "project": "storefront"}, "needs the project"),
        ({"kind": "admin", "name": "ops", "environment": "prod"}, "leave out project"),
    ],
)
async def test_the_scope_has_to_fit_the_kind(
    http: AsyncClient, as_admin: Headers, body: dict[str, str], message: str
) -> None:
    response = await http.post("/api-keys", json=body, headers=as_admin)

    assert response.status_code == 422
    assert message in response.json()["detail"]


async def test_lists_keys_newest_first_without_their_secrets(
    http: AsyncClient, as_admin: Headers, clock: FixedClock
) -> None:
    clock.advance(timedelta(minutes=5))
    await http.post(
        "/api-keys",
        json={"kind": "sdk", "name": "checkout-api", "project": "storefront", "environment": "dev"},
        headers=as_admin,
    )

    listed = (await http.get("/api-keys", headers=as_admin)).json()

    assert [(key["name"], key["environment"]) for key in listed] == [
        ("checkout-api", "dev"),
        ("Release tooling", None),
    ]
    assert all("secret" not in key for key in listed)


async def test_a_revoked_key_stops_working_and_stays_listed(
    http: AsyncClient, as_admin: Headers
) -> None:
    issued = (
        await http.post("/api-keys", json={"kind": "admin", "name": "Old laptop"}, headers=as_admin)
    ).json()

    revoked = await http.post(f"/api-keys/{issued['id']}/revoke", headers=as_admin)
    used = await http.get("/projects", headers=bearer(issued["secret"]))

    assert revoked.json()["revoked_at"] == "2026-10-19T09:30:00Z"
    assert used.status_code == 401
    assert issued["id"] in [
        key["id"] for key in (await http.get("/api-keys", headers=as_admin)).json()
    ]


async def test_revoking_an_unknown_key_is_not_found(http: AsyncClient, as_admin: Headers) -> None:
    response = await http.post(
        "/api-keys/8f14e45f-ceea-467f-a0e6-b2c9f3c0a1d4/revoke", headers=as_admin
    )

    assert (response.status_code, response.json()["code"]) == (404, "api_key_not_found")


async def test_an_sdk_key_cannot_issue_keys(http: AsyncClient, as_admin: Headers) -> None:
    sdk = (
        await http.post(
            "/api-keys",
            json={
                "kind": "sdk",
                "name": "checkout-api",
                "project": "storefront",
                "environment": "prod",
            },
            headers=as_admin,
        )
    ).json()

    response = await http.post(
        "/api-keys", json={"kind": "admin", "name": "escalated"}, headers=bearer(sdk["secret"])
    )

    assert response.status_code == 403
