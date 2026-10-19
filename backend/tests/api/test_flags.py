from typing import Any

import pytest
from httpx import AsyncClient

from flagstaff_server.domain.audit import AuditAction
from tests.api.conftest import Headers, sdk_key_for
from tests.unit.application.fakes import FakeUnitOfWork, FixedClock

FLAGS = "/projects/storefront/flags"
NEW_CHECKOUT = {
    "key": "new-checkout",
    "name": "New checkout",
    "description": "Two-step checkout with saved cards",
    "kind": "boolean",
    "variants": [{"key": "on", "value": True}, {"key": "off", "value": False}],
    "off_variant": "off",
    "on_variant": "on",
}
BETA_IN_PROD: dict[str, Any] = {
    "enabled": True,
    "off_variant": "off",
    "rules": [
        {
            "id": "beta-testers",
            "conditions": [{"type": "user_list", "user_keys": ["user-1042", "user-7"]}],
            "serve": {"variant": "on"},
        },
        {
            "id": "eu-pro",
            "conditions": [
                {
                    "type": "attribute",
                    "attribute": "country",
                    "operator": "in",
                    "values": ["BG", "DE"],
                    "negate": False,
                }
            ],
            "serve": {
                "rollout": [
                    {"variant": "on", "weight": 25_000},
                    {"variant": "off", "weight": 75_000},
                ]
            },
        },
    ],
    "fallthrough": {"variant": "off"},
}
INITIAL = {
    "enabled": False,
    "off_variant": "off",
    "rules": [],
    "fallthrough": {"variant": "on"},
}


@pytest.fixture(autouse=True)
async def storefront(http: AsyncClient, as_admin: Headers) -> None:
    response = await http.post(
        "/projects", json={"key": "storefront", "name": "Storefront"}, headers=as_admin
    )
    assert response.status_code == 201


async def create_new_checkout(http: AsyncClient, headers: Headers) -> dict[str, Any]:
    response = await http.post(FLAGS, json=NEW_CHECKOUT, headers=headers)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


class TestCreate:
    async def test_starts_off_in_every_environment(
        self, http: AsyncClient, as_admin: Headers
    ) -> None:
        response = await http.post(FLAGS, json=NEW_CHECKOUT, headers=as_admin)

        body = response.json()
        assert response.status_code == 201
        assert response.headers["Location"] == f"{FLAGS}/new-checkout"
        assert response.headers["ETag"] == '"1"'
        assert body["version"] == 1
        assert body["environments"] == {"dev": INITIAL, "staging": INITIAL, "prod": INITIAL}
        assert body["variants"] == NEW_CHECKOUT["variants"]

    async def test_variant_values_must_fit_the_kind(
        self, http: AsyncClient, as_admin: Headers
    ) -> None:
        body = {
            **NEW_CHECKOUT,
            "variants": [{"key": "on", "value": "yes"}, {"key": "off", "value": False}],
        }

        response = await http.post(FLAGS, json=body, headers=as_admin)

        assert response.status_code == 422
        assert response.json()["code"] == "invalid_targeting"
        assert "variant 'on' is 'yes'" in response.json()["detail"]

    async def test_a_kind_it_does_not_know_is_a_malformed_request(
        self, http: AsyncClient, as_admin: Headers
    ) -> None:
        response = await http.post(FLAGS, json={**NEW_CHECKOUT, "kind": "date"}, headers=as_admin)

        assert response.status_code == 422
        assert response.json()["code"] == "invalid_request"

    async def test_a_taken_key_is_a_conflict(self, http: AsyncClient, as_admin: Headers) -> None:
        await create_new_checkout(http, as_admin)

        response = await http.post(FLAGS, json=NEW_CHECKOUT, headers=as_admin)

        assert (response.status_code, response.json()["code"]) == (409, "flag_key_taken")


async def test_reads_one_flag_with_its_etag(http: AsyncClient, as_admin: Headers) -> None:
    await create_new_checkout(http, as_admin)

    response = await http.get(f"{FLAGS}/new-checkout", headers=as_admin)

    assert response.headers["ETag"] == '"1"'
    assert response.json()["name"] == "New checkout"


async def test_an_unknown_flag_is_not_found(http: AsyncClient, as_admin: Headers) -> None:
    response = await http.get(f"{FLAGS}/dark-mode", headers=as_admin)

    assert (response.status_code, response.json()["code"]) == (404, "flag_not_found")


class TestTargeting:
    async def test_replaces_one_environments_targeting(
        self, http: AsyncClient, as_admin: Headers
    ) -> None:
        await create_new_checkout(http, as_admin)

        response = await http.put(
            f"{FLAGS}/new-checkout/environments/prod/targeting",
            json=BETA_IN_PROD,
            headers={**as_admin, "If-Match": '"1"'},
        )

        body = response.json()
        assert response.status_code == 200, response.text
        assert response.headers["ETag"] == '"2"'
        assert body["environments"]["prod"] == BETA_IN_PROD
        assert body["environments"]["dev"] == INITIAL

    async def test_needs_the_version_it_was_based_on(
        self, http: AsyncClient, as_admin: Headers
    ) -> None:
        await create_new_checkout(http, as_admin)

        response = await http.put(
            f"{FLAGS}/new-checkout/environments/prod/targeting", json=BETA_IN_PROD, headers=as_admin
        )

        assert (response.status_code, response.json()["code"]) == (428, "version_required")

    async def test_an_edit_from_a_stale_version_is_refused(
        self, http: AsyncClient, as_admin: Headers
    ) -> None:
        await create_new_checkout(http, as_admin)
        await http.post(f"{FLAGS}/new-checkout/environments/dev/enable", headers=as_admin)

        response = await http.put(
            f"{FLAGS}/new-checkout/environments/prod/targeting",
            json=BETA_IN_PROD,
            headers={**as_admin, "If-Match": '"1"'},
        )

        assert response.status_code == 412
        assert response.json() == {
            "detail": "flag 'new-checkout' is no longer at version 1, it is at 2",
            "code": "version_mismatch",
        }

    async def test_rules_that_break_the_flag_say_where(
        self, http: AsyncClient, as_admin: Headers
    ) -> None:
        await create_new_checkout(http, as_admin)
        broken = {
            **BETA_IN_PROD,
            "rules": [
                {
                    **BETA_IN_PROD["rules"][1],
                    "serve": {"rollout": [{"variant": "on", "weight": 10}]},
                }
            ],
        }

        response = await http.put(
            f"{FLAGS}/new-checkout/environments/prod/targeting",
            json=broken,
            headers={**as_admin, "If-Match": '"1"'},
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": "rules[0].serve: rollout weights add up to 10, not 100000",
            "code": "invalid_targeting",
        }

    async def test_condition_values_keep_their_type(
        self, http: AsyncClient, as_admin: Headers
    ) -> None:
        await create_new_checkout(http, as_admin)
        seats = {
            **BETA_IN_PROD,
            "rules": [
                {
                    "id": "big-teams",
                    "conditions": [
                        {
                            "type": "attribute",
                            "attribute": "plan_code",
                            "operator": "in",
                            "values": ["5", 5],
                        }
                    ],
                    "serve": {"variant": "on"},
                }
            ],
        }

        response = await http.put(
            f"{FLAGS}/new-checkout/environments/prod/targeting",
            json=seats,
            headers={**as_admin, "If-Match": '"1"'},
        )

        assert response.json()["environments"]["prod"]["rules"][0]["conditions"][0]["values"] == [
            "5",
            5,
        ]

    @pytest.mark.parametrize("if_match", ['W/"1"', "1", '"1", "2"'])
    async def test_if_match_must_be_one_strong_etag(
        self, http: AsyncClient, as_admin: Headers, if_match: str
    ) -> None:
        await create_new_checkout(http, as_admin)

        response = await http.put(
            f"{FLAGS}/new-checkout/environments/prod/targeting",
            json=BETA_IN_PROD,
            headers={**as_admin, "If-Match": if_match},
        )

        assert (response.status_code, response.json()["code"]) == (422, "invalid_value")


class TestSwitching:
    async def test_switches_without_needing_a_version(
        self, http: AsyncClient, as_admin: Headers
    ) -> None:
        await create_new_checkout(http, as_admin)

        response = await http.post(
            f"{FLAGS}/new-checkout/environments/prod/enable", headers=as_admin
        )

        assert response.status_code == 200
        assert response.json()["environments"]["prod"]["enabled"] is True
        assert response.headers["ETag"] == '"2"'

    async def test_a_version_given_is_still_checked(
        self, http: AsyncClient, as_admin: Headers
    ) -> None:
        await create_new_checkout(http, as_admin)
        await http.post(f"{FLAGS}/new-checkout/environments/dev/enable", headers=as_admin)

        response = await http.post(
            f"{FLAGS}/new-checkout/environments/prod/disable",
            headers={**as_admin, "If-Match": '"1"'},
        )

        assert response.status_code == 412

    async def test_an_unknown_environment_is_not_found(
        self, http: AsyncClient, as_admin: Headers
    ) -> None:
        await create_new_checkout(http, as_admin)

        response = await http.post(f"{FLAGS}/new-checkout/environments/qa/enable", headers=as_admin)

        assert (response.status_code, response.json()["code"]) == (404, "environment_not_found")


async def test_edits_name_and_description(http: AsyncClient, as_admin: Headers) -> None:
    await create_new_checkout(http, as_admin)

    response = await http.patch(
        f"{FLAGS}/new-checkout",
        json={"name": "Checkout v2", "description": "Cards and wallets"},
        headers={**as_admin, "If-Match": "*"},
    )

    assert (response.json()["name"], response.json()["description"]) == (
        "Checkout v2",
        "Cards and wallets",
    )


async def test_replaces_the_variants(http: AsyncClient, as_admin: Headers) -> None:
    await create_new_checkout(http, as_admin)
    variants = [*NEW_CHECKOUT["variants"], {"key": "holdout", "value": False}]

    response = await http.put(
        f"{FLAGS}/new-checkout/variants",
        json={"variants": variants},
        headers={**as_admin, "If-Match": '"1"'},
    )

    assert response.json()["variants"] == variants


async def test_an_archived_flag_leaves_the_list_and_stops_changing(
    http: AsyncClient, as_admin: Headers
) -> None:
    await create_new_checkout(http, as_admin)
    await http.post(FLAGS, json={**NEW_CHECKOUT, "key": "search-v2"}, headers=as_admin)

    archived = await http.post(f"{FLAGS}/new-checkout/archive", headers=as_admin)
    listed = await http.get(FLAGS, headers=as_admin)
    enabled = await http.post(f"{FLAGS}/new-checkout/environments/prod/enable", headers=as_admin)

    assert archived.json()["archived_at"] == "2026-10-19T09:30:00Z"
    assert [flag["key"] for flag in listed.json()] == ["search-v2"]
    assert (enabled.status_code, enabled.json()["code"]) == (409, "flag_archived")


async def test_changes_are_audited_under_the_admin_keys_name(
    http: AsyncClient, as_admin: Headers, uow: FakeUnitOfWork
) -> None:
    await create_new_checkout(http, as_admin)

    await http.post(f"{FLAGS}/new-checkout/environments/prod/enable", headers=as_admin)

    entry = uow.committed.audit[-1]
    assert (entry.action, entry.actor.name, entry.subject) == (
        AuditAction.FLAG_ENABLED,
        "Release tooling",
        "new-checkout",
    )


async def test_an_sdk_key_cannot_read_flags(
    http: AsyncClient, uow: FakeUnitOfWork, clock: FixedClock
) -> None:
    response = await http.get(FLAGS, headers=await sdk_key_for(uow, clock))

    assert response.status_code == 403
