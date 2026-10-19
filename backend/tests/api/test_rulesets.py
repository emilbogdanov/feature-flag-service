from typing import Any, NoReturn

import pytest
from flagstaff.engine.context import EvaluationContext
from flagstaff.engine.wire import ruleset_from_document
from httpx import AsyncClient

from flagstaff_server.application.rulesets import RulesetService
from tests.api.conftest import Headers, sdk_key_for
from tests.unit.application.fakes import FakeUnitOfWork, FixedClock

FLAGS = "/projects/storefront/flags"
BOOLEAN = {
    "kind": "boolean",
    "variants": [{"key": "on", "value": True}, {"key": "off", "value": False}],
    "off_variant": "off",
    "on_variant": "on",
}
BETA_TESTERS = {
    "enabled": True,
    "off_variant": "off",
    "rules": [
        {
            "id": "beta-testers",
            "conditions": [{"type": "user_list", "user_keys": ["user-7"]}],
            "serve": {"variant": "on"},
        }
    ],
    "fallthrough": {"variant": "off"},
}


@pytest.fixture(autouse=True)
async def storefront(http: AsyncClient, as_admin: Headers) -> None:
    await http.post("/projects", json={"key": "storefront", "name": "Storefront"}, headers=as_admin)
    for key in ["new-checkout", "search-v2"]:
        await http.post(FLAGS, json={**BOOLEAN, "key": key, "name": key}, headers=as_admin)
    response = await http.put(
        f"{FLAGS}/new-checkout/environments/prod/targeting",
        json=BETA_TESTERS,
        headers={**as_admin, "If-Match": '"1"'},
    )
    assert response.status_code == 200


@pytest.fixture
async def as_prod(uow: FakeUnitOfWork, clock: FixedClock) -> Headers:
    return await sdk_key_for(uow, clock, "prod")


class TestRuleset:
    async def test_an_sdk_key_downloads_its_environments_rules(
        self, http: AsyncClient, as_prod: Headers
    ) -> None:
        response = await http.get("/sdk/ruleset", headers=as_prod)

        ruleset = ruleset_from_document(response.json())
        assert response.status_code == 200
        assert response.headers["ETag"] == f'"{ruleset.version}"'
        assert response.headers["Cache-Control"] == "private, no-cache"
        assert sorted(ruleset.flags) == ["new-checkout", "search-v2"]
        checkout = ruleset.evaluate("new-checkout", EvaluationContext("user-7"))
        assert checkout is not None
        assert checkout.rule_id == "beta-testers"

    async def test_each_environment_gets_its_own_rules(
        self, http: AsyncClient, uow: FakeUnitOfWork, clock: FixedClock
    ) -> None:
        dev = await http.get("/sdk/ruleset", headers=await sdk_key_for(uow, clock, "dev"))

        [checkout] = [flag for flag in dev.json()["flags"] if flag["key"] == "new-checkout"]
        assert checkout["rules"] == []
        assert checkout["enabled"] is False

    async def test_the_held_version_gets_a_304(self, http: AsyncClient, as_prod: Headers) -> None:
        first = await http.get("/sdk/ruleset", headers=as_prod)

        again = await http.get(
            "/sdk/ruleset", headers={**as_prod, "If-None-Match": first.headers["ETag"]}
        )

        assert again.status_code == 304
        assert again.content == b""
        assert again.headers["ETag"] == first.headers["ETag"]

    async def test_the_held_version_is_answered_without_building_the_rules(
        self, http: AsyncClient, as_prod: Headers, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        first = await http.get("/sdk/ruleset", headers=as_prod)

        async def build_refused(*_: object) -> NoReturn:
            raise AssertionError("a 304 should not need the rules themselves")

        monkeypatch.setattr(RulesetService, "ruleset_for", build_refused)
        again = await http.get(
            "/sdk/ruleset", headers={**as_prod, "If-None-Match": first.headers["ETag"]}
        )

        assert again.status_code == 304
        assert again.headers["Cache-Control"] == "private, no-cache"

    async def test_a_change_moves_the_etag_on(
        self, http: AsyncClient, as_admin: Headers, as_prod: Headers
    ) -> None:
        first = await http.get("/sdk/ruleset", headers=as_prod)
        await http.post(f"{FLAGS}/search-v2/environments/prod/enable", headers=as_admin)

        after = await http.get(
            "/sdk/ruleset", headers={**as_prod, "If-None-Match": first.headers["ETag"]}
        )

        assert after.status_code == 200
        assert after.json()["version"] == first.json()["version"] + 1

    async def test_the_same_rules_are_the_same_bytes(
        self, http: AsyncClient, as_prod: Headers
    ) -> None:
        first = await http.get("/sdk/ruleset", headers=as_prod)
        second = await http.get("/sdk/ruleset", headers=as_prod)

        assert first.content == second.content

    async def test_an_admin_key_reads_any_environment_by_url(
        self, http: AsyncClient, as_admin: Headers, as_prod: Headers
    ) -> None:
        by_url = await http.get("/projects/storefront/environments/prod/ruleset", headers=as_admin)
        by_key = await http.get("/sdk/ruleset", headers=as_prod)

        assert by_url.content == by_key.content

    async def test_an_admin_key_is_pointed_away_from_the_sdk_route(
        self, http: AsyncClient, as_admin: Headers
    ) -> None:
        response = await http.get("/sdk/ruleset", headers=as_admin)

        assert response.status_code == 403
        assert "admin keys read rulesets under /projects" in response.json()["detail"]

    async def test_an_sdk_key_cannot_read_another_environment_by_url(
        self, http: AsyncClient, as_prod: Headers
    ) -> None:
        response = await http.get("/projects/storefront/environments/dev/ruleset", headers=as_prod)

        assert response.status_code == 403


class TestEvaluate:
    async def test_evaluates_every_flag_for_one_user(
        self, http: AsyncClient, as_prod: Headers
    ) -> None:
        response = await http.post(
            "/sdk/evaluate", json={"context": {"key": "user-7"}}, headers=as_prod
        )

        body: dict[str, Any] = response.json()
        assert body["evaluations"] == {
            "new-checkout": {
                "variant": "on",
                "value": True,
                "reason": "rule_match",
                "rule_id": "beta-testers",
            },
            "search-v2": {"variant": "off", "value": False, "reason": "disabled", "rule_id": None},
        }

    async def test_evaluates_only_the_flags_asked_for(
        self, http: AsyncClient, as_prod: Headers
    ) -> None:
        response = await http.post(
            "/sdk/evaluate",
            json={"context": {"key": "user-8"}, "flags": ["new-checkout", "dark-mode"]},
            headers=as_prod,
        )

        assert list(response.json()["evaluations"]) == ["new-checkout"]
        assert response.json()["evaluations"]["new-checkout"]["reason"] == "fallthrough"

    async def test_the_dashboard_previews_an_environment(
        self, http: AsyncClient, as_admin: Headers
    ) -> None:
        response = await http.post(
            "/projects/storefront/environments/prod/evaluate",
            json={"context": {"key": "user-7", "attributes": {"country": "BG", "seats": 12}}},
            headers=as_admin,
        )

        assert response.json()["evaluations"]["new-checkout"]["value"] is True

    @pytest.mark.parametrize(
        "context",
        [{"key": ""}, {"key": "user-7", "attributes": {"tags": ["beta"]}}, {"attributes": {}}],
    )
    async def test_a_context_it_cannot_evaluate_is_refused(
        self, http: AsyncClient, as_prod: Headers, context: dict[str, Any]
    ) -> None:
        response = await http.post("/sdk/evaluate", json={"context": context}, headers=as_prod)

        assert response.status_code == 422
        assert response.json()["code"] in {"invalid_context", "invalid_request"}
