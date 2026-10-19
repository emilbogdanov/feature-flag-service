import asyncio
import socket
from collections.abc import Callable

import pytest
from flagstaff import AsyncFlagstaffClient, EvaluationContext, FlagstaffClient
from httpx import AsyncClient
from pydantic import PostgresDsn, RedisDsn

from flagstaff_server.api.app import create_app
from flagstaff_server.config import Settings
from flagstaff_server.main import build_container
from tests.api.sse import RunningServer

pytestmark = pytest.mark.usefixtures("engine", "redis")
NEW_CHECKOUT = {
    "key": "new-checkout",
    "name": "New checkout",
    "kind": "boolean",
    "variants": [{"key": "on", "value": True}, {"key": "off", "value": False}],
    "off_variant": "off",
    "on_variant": "on",
}
BULGARIA_FIRST = {
    "enabled": True,
    "off_variant": "off",
    "rules": [
        {
            "id": "bulgaria",
            "conditions": [
                {"type": "attribute", "attribute": "country", "operator": "in", "values": ["BG"]}
            ],
            "serve": {"variant": "on"},
        }
    ],
    "fallthrough": {"variant": "off"},
}


@pytest.fixture
def settings(database_url: str, redis_url: str) -> Settings:
    return Settings(
        database_url=PostgresDsn(database_url),
        redis_url=RedisDsn(redis_url),
        stream_heartbeat_seconds=0.5,
        ruleset_resync_seconds=60,
        _env_file=None,
    )


@pytest.fixture
def port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free: int = probe.getsockname()[1]
        return free


async def until(condition: Callable[[], bool], within: float = 5.0) -> None:
    async with asyncio.timeout(within):
        while not condition():
            await asyncio.sleep(0.01)


async def set_up_storefront(admin: AsyncClient, headers: dict[str, str]) -> str:
    await admin.post("/projects", json={"key": "storefront", "name": "Storefront"}, headers=headers)
    await admin.post("/projects/storefront/flags", json=NEW_CHECKOUT, headers=headers)
    issued = await admin.post(
        "/api-keys",
        json={
            "kind": "sdk",
            "name": "checkout-api",
            "project": "storefront",
            "environment": "prod",
        },
        headers=headers,
    )
    secret: str = issued.json()["secret"]
    return secret


async def target_bulgaria(admin: AsyncClient, headers: dict[str, str]) -> None:
    response = await admin.put(
        "/projects/storefront/flags/new-checkout/environments/prod/targeting",
        json=BULGARIA_FIRST,
        headers={**headers, "If-Match": "*"},
    )
    assert response.status_code == 200, response.text


async def test_an_edit_reaches_a_running_app_within_moments(
    settings: Settings, port: int, as_admin: dict[str, str]
) -> None:
    async with (
        RunningServer(create_app(build_container(settings)), port=port) as url,
        AsyncClient(base_url=url) as admin,
    ):
        sdk_key = await set_up_storefront(admin, as_admin)
        async with AsyncFlagstaffClient(sdk_key, base_url=url) as flags:
            assert await flags.wait_until_ready(timeout=5)
            sofia = EvaluationContext("user-1042", {"country": "BG"})
            assert flags.bool_value("new-checkout", sofia, default=True) is False

            await target_bulgaria(admin, as_admin)

            await until(lambda: flags.bool_value("new-checkout", sofia, default=False))
            assert flags.bool_value("new-checkout", "user-1043", default=True) is False


async def test_an_app_rides_out_a_server_restart_on_its_last_rules(
    settings: Settings, port: int, as_admin: dict[str, str]
) -> None:
    sofia = EvaluationContext("user-1042", {"country": "BG"})
    url = f"http://127.0.0.1:{port}"
    async with RunningServer(create_app(build_container(settings)), port=port):
        async with AsyncClient(base_url=url) as admin:
            sdk_key = await set_up_storefront(admin, as_admin)
            await target_bulgaria(admin, as_admin)
        flags = FlagstaffClient(sdk_key, base_url=url, max_reconnect_delay=0.5)
        # Waited for on a thread: this test's event loop is the one the servers run on.
        ready = await asyncio.to_thread(flags.wait_until_ready, 5)
    try:
        assert ready

        # No server at all now: the app keeps answering from what it last received.
        await asyncio.sleep(0.3)
        assert flags.bool_value("new-checkout", sofia, default=False) is True

        async with (
            RunningServer(create_app(build_container(settings)), port=port),
            AsyncClient(base_url=url) as admin,
        ):
            await admin.post(
                "/projects/storefront/flags/new-checkout/environments/prod/disable",
                headers=as_admin,
            )
            await until(lambda: not flags.bool_value("new-checkout", sofia, default=True))
    finally:
        flags.close()
