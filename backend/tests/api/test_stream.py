import asyncio
import json
from collections.abc import AsyncIterator

import pytest
from flagstaff.engine.wire import ruleset_from_document
from httpx import AsyncClient

from flagstaff_server.api.app import create_app
from flagstaff_server.api.container import Container
from tests.api.conftest import Headers, sdk_key_for
from tests.api.sse import RunningServer, events, next_event
from tests.unit.application.fakes import FakeUnitOfWork, FixedClock

NEW_CHECKOUT = {
    "key": "new-checkout",
    "name": "New checkout",
    "kind": "boolean",
    "variants": [{"key": "on", "value": True}, {"key": "off", "value": False}],
    "off_variant": "off",
    "on_variant": "on",
}


@pytest.fixture
async def base_url(container: Container) -> AsyncIterator[str]:
    async with RunningServer(create_app(container)) as url:
        yield url


@pytest.fixture
async def live(base_url: str) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(base_url=base_url, timeout=5) as client:
        yield client


@pytest.fixture
async def as_prod(
    live: AsyncClient, as_admin: Headers, uow: FakeUnitOfWork, clock: FixedClock
) -> Headers:
    await live.post("/projects", json={"key": "storefront", "name": "Storefront"}, headers=as_admin)
    await live.post("/projects/storefront/flags", json=NEW_CHECKOUT, headers=as_admin)
    return await sdk_key_for(uow, clock, "prod")


async def test_a_new_stream_opens_with_the_current_ruleset(
    live: AsyncClient, as_prod: Headers
) -> None:
    async with live.stream("GET", "/sdk/stream", headers=as_prod) as response:
        stream = events(response)
        first = await anext(stream)
        ruleset_event = await next_event(stream, kind="ruleset")

    ruleset = ruleset_from_document(json.loads(ruleset_event.data))
    assert response.headers["content-type"].startswith("text/event-stream")
    assert first.retry == "1000"
    assert ruleset_event.id == str(ruleset.version) == "1"
    assert list(ruleset.flags) == ["new-checkout"]


async def test_a_change_arrives_while_the_stream_is_open(
    live: AsyncClient, as_prod: Headers, as_admin: Headers
) -> None:
    async with live.stream("GET", "/sdk/stream", headers=as_prod) as response:
        stream = events(response)
        await next_event(stream, kind="ruleset")

        await live.post(
            "/projects/storefront/flags/new-checkout/environments/prod/enable", headers=as_admin
        )
        changed = await next_event(stream, kind="ruleset")

    ruleset = ruleset_from_document(json.loads(changed.data))
    assert changed.id == "2"
    assert ruleset.flags["new-checkout"].enabled


async def test_reconnecting_with_the_held_version_sends_only_keep_alives(
    live: AsyncClient, as_prod: Headers
) -> None:
    headers = {**as_prod, "Last-Event-ID": "1"}
    async with live.stream("GET", "/sdk/stream", headers=headers) as response:
        stream = events(response)
        await anext(stream)
        quiet = await anext(stream)

    assert quiet.comments == ["keep-alive"]
    assert quiet.data == ""


async def test_an_admin_key_cannot_stream(live: AsyncClient, as_admin: Headers) -> None:
    response = await live.get("/sdk/stream", headers=as_admin)

    assert response.status_code == 403


async def test_a_client_that_hangs_up_leaves_no_stream_behind(
    live: AsyncClient, as_prod: Headers, container: Container
) -> None:
    async with live.stream("GET", "/sdk/stream", headers=as_prod) as response:
        await next_event(events(response), kind="ruleset")
        assert container.broadcaster.stream_count == 1

    async with asyncio.timeout(2):
        while container.broadcaster.stream_count:
            await asyncio.sleep(0.01)
