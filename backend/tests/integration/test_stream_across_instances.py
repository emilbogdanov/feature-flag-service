import json
from collections.abc import AsyncIterator

import pytest
from flagstaff.engine.wire import ruleset_from_document
from httpx import AsyncClient
from pydantic import PostgresDsn, RedisDsn

from flagstaff_server.api.app import create_app
from flagstaff_server.config import Settings
from flagstaff_server.main import build_container
from tests.api.sse import RunningServer, events, next_event

pytestmark = pytest.mark.usefixtures("engine", "redis")


@pytest.fixture
def settings(database_url: str, redis_url: str) -> Settings:
    return Settings(
        database_url=PostgresDsn(database_url),
        redis_url=RedisDsn(redis_url),
        stream_heartbeat_seconds=0.5,
        ruleset_resync_seconds=60,
        _env_file=None,
    )


# Two API processes in all but name: each has its own pools, its own Redis subscription and
# its own streams, and they share only Postgres and Redis.
@pytest.fixture
async def instances(settings: Settings) -> AsyncIterator[tuple[AsyncClient, AsyncClient]]:
    async with (
        RunningServer(create_app(build_container(settings))) as first_url,
        RunningServer(create_app(build_container(settings))) as second_url,
        AsyncClient(base_url=first_url, timeout=5) as first,
        AsyncClient(base_url=second_url, timeout=5) as second,
    ):
        yield first, second


async def test_a_change_made_on_one_instance_reaches_streams_on_another(
    instances: tuple[AsyncClient, AsyncClient], as_admin: dict[str, str]
) -> None:
    editing, streaming = instances
    await editing.post(
        "/projects", json={"key": "storefront", "name": "Storefront"}, headers=as_admin
    )
    await editing.post(
        "/projects/storefront/flags",
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
    issued = await editing.post(
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

    async with streaming.stream("GET", "/sdk/stream", headers=sdk) as response:
        stream = events(response)
        opening = await next_event(stream, kind="ruleset")
        await editing.post(
            "/projects/storefront/flags/new-checkout/environments/prod/enable", headers=as_admin
        )
        # Well under the 60-second resync: only the Redis announcement can have brought it.
        changed = await next_event(stream, kind="ruleset", within=2)

    assert opening.id == "1"
    assert changed.id == "2"
    assert ruleset_from_document(json.loads(changed.data)).flags["new-checkout"].enabled
