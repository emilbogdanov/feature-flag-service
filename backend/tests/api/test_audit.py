from datetime import timedelta

import pytest
from httpx import AsyncClient

from tests.api.conftest import Headers
from tests.unit.application.fakes import FixedClock


@pytest.fixture(autouse=True)
async def history(http: AsyncClient, as_admin: Headers, clock: FixedClock) -> None:
    await http.post("/projects", json={"key": "storefront", "name": "Storefront"}, headers=as_admin)
    clock.advance(timedelta(minutes=1))
    await http.post(
        "/projects", json={"key": "back-office", "name": "Back office"}, headers=as_admin
    )
    for minute, key in enumerate(["new-checkout", "search-v2", "dark-mode"], start=2):
        clock.advance(timedelta(minutes=minute))
        await http.post(
            "/projects/storefront/flags",
            json={
                "key": key,
                "name": key,
                "kind": "boolean",
                "variants": [{"key": "on", "value": True}, {"key": "off", "value": False}],
                "off_variant": "off",
                "on_variant": "on",
            },
            headers=as_admin,
        )
    clock.advance(timedelta(minutes=5))
    await http.post(
        "/projects/storefront/flags/dark-mode/environments/prod/enable", headers=as_admin
    )


async def test_pages_through_a_project_newest_first(http: AsyncClient, as_admin: Headers) -> None:
    first = (await http.get("/audit?project=storefront&limit=3", headers=as_admin)).json()
    second = (
        await http.get(
            f"/audit?project=storefront&limit=3&cursor={first['next_cursor']}", headers=as_admin
        )
    ).json()

    entries = first["entries"] + second["entries"]
    assert [(e["action"], e["subject"]) for e in entries] == [
        ("flag.enabled", "dark-mode"),
        ("flag.created", "dark-mode"),
        ("flag.created", "search-v2"),
        ("flag.created", "new-checkout"),
        ("project.created", "storefront"),
    ]
    assert second["next_cursor"] is None


async def test_names_projects_environments_and_actors_as_people_see_them(
    http: AsyncClient, as_admin: Headers
) -> None:
    [enabled] = (await http.get("/audit?limit=1", headers=as_admin)).json()["entries"]

    assert (enabled["project"], enabled["environment"]) == ("storefront", "prod")
    assert enabled["actor"]["name"] == "Release tooling"
    assert enabled["at"] == "2026-10-19T09:45:00Z"


async def test_without_a_project_includes_every_project(
    http: AsyncClient, as_admin: Headers
) -> None:
    page = (await http.get("/audit?limit=100", headers=as_admin)).json()

    assert {e["subject"] for e in page["entries"]} >= {
        "storefront",
        "back-office",
        "Release tooling",
    }


@pytest.mark.parametrize("cursor", ["not-a-cursor", "eyJhdCI6IjIwMjYtMTAtMTkifQ"])
async def test_a_mangled_cursor_is_refused(
    http: AsyncClient, as_admin: Headers, cursor: str
) -> None:
    response = await http.get(f"/audit?cursor={cursor}", headers=as_admin)

    assert (response.status_code, response.json()["detail"]) == (422, "cursor is invalid")


async def test_page_size_is_bounded(http: AsyncClient, as_admin: Headers) -> None:
    response = await http.get("/audit?limit=101", headers=as_admin)

    assert (response.status_code, response.json()["code"]) == (422, "invalid_request")
