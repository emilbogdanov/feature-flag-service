from collections.abc import AsyncIterator

import pytest
from flagstaff.engine.context import EvaluationContext
from flagstaff.engine.wire import ruleset_from_document
from httpx import ASGITransport, AsyncClient
from pydantic import PostgresDsn, RedisDsn
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from flagstaff_server.api.app import create_app
from flagstaff_server.application.api_keys import ApiKeyService
from flagstaff_server.config import Settings
from flagstaff_server.domain.audit import Actor
from flagstaff_server.domain.values import Name
from flagstaff_server.infrastructure.clock import SystemClock
from flagstaff_server.infrastructure.db.unit_of_work import SqlUnitOfWork
from flagstaff_server.main import build_container

FLAGS = "/projects/storefront/flags"

# The app runs on its own connection pool; the engine fixture is what empties the tables after.
pytestmark = pytest.mark.usefixtures("engine")


@pytest.fixture
async def http(database_url: str) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        database_url=PostgresDsn(database_url),
        redis_url=RedisDsn("redis://localhost:6379/0"),
        _env_file=None,
    )
    app = create_app(build_container(settings))
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://flagstaff.test") as client:
            yield client


@pytest.fixture
async def as_admin(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, str]:
    issued = await ApiKeyService(SqlUnitOfWork(session_factory), SystemClock()).issue_admin_key(
        Actor.command_line(), name=Name("Release tooling")
    )
    return {"Authorization": f"Bearer {issued.secret}"}


async def test_an_sdk_reads_the_rules_an_admin_just_set(
    http: AsyncClient, as_admin: dict[str, str]
) -> None:
    await http.post("/projects", json={"key": "storefront", "name": "Storefront"}, headers=as_admin)
    created = await http.post(
        FLAGS,
        json={
            "key": "new-checkout",
            "name": "New checkout",
            "kind": "boolean",
            "variants": [{"key": "on", "value": True}, {"key": "off", "value": False}],
            "off_variant": "off",
            "on_variant": "on",
        },
        headers=as_admin,
    )
    targeted = await http.put(
        f"{FLAGS}/new-checkout/environments/prod/targeting",
        json={
            "enabled": True,
            "off_variant": "off",
            "rules": [
                {
                    "id": "eu",
                    "conditions": [
                        {
                            "type": "attribute",
                            "attribute": "country",
                            "operator": "in",
                            "values": ["BG"],
                        }
                    ],
                    "serve": {"variant": "on"},
                }
            ],
            "fallthrough": {"variant": "off"},
        },
        headers={**as_admin, "If-Match": created.headers["ETag"]},
    )
    issued = await http.post(
        "/api-keys",
        json={
            "kind": "sdk",
            "name": "checkout-api",
            "project": "storefront",
            "environment": "prod",
        },
        headers=as_admin,
    )
    sdk = {"Authorization": f"Bearer {issued.json()['secret']}"}

    downloaded = await http.get("/sdk/ruleset", headers=sdk)
    unchanged = await http.get(
        "/sdk/ruleset", headers={**sdk, "If-None-Match": downloaded.headers["ETag"]}
    )
    audit = await http.get("/audit?project=storefront", headers=as_admin)

    assert targeted.status_code == 200, targeted.text
    ruleset = ruleset_from_document(downloaded.json())
    bulgarian = ruleset.evaluate("new-checkout", EvaluationContext("user-1", {"country": "BG"}))
    assert bulgarian is not None
    assert bulgarian.value is True
    assert unchanged.status_code == 304
    assert [entry["action"] for entry in audit.json()["entries"]] == [
        "api_key.issued",
        "flag.targeting_changed",
        "flag.created",
        "project.created",
    ]


async def test_a_stale_edit_is_refused_by_postgres_too(
    http: AsyncClient, as_admin: dict[str, str]
) -> None:
    await http.post("/projects", json={"key": "storefront", "name": "Storefront"}, headers=as_admin)
    await http.post(
        FLAGS,
        json={
            "key": "dark-mode",
            "name": "Dark mode",
            "kind": "boolean",
            "variants": [{"key": "on", "value": True}, {"key": "off", "value": False}],
            "off_variant": "off",
            "on_variant": "on",
        },
        headers=as_admin,
    )
    await http.post(f"{FLAGS}/dark-mode/environments/dev/enable", headers=as_admin)

    response = await http.patch(
        f"{FLAGS}/dark-mode",
        json={"name": "Dark theme"},
        headers={**as_admin, "If-Match": '"1"'},
    )

    assert (response.status_code, response.json()["code"]) == (412, "version_mismatch")
