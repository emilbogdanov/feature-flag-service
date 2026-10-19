import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest

from flagstaff._cache import RulesetFile
from flagstaff.aio import AsyncFlagstaffClient
from flagstaff.reader import Reason
from tests.client.fake_server import BASE_URL, SDK_KEY, FakeServer
from tests.client.rulesets import storefront


@pytest.fixture
def server() -> FakeServer:
    return FakeServer(storefront(1))


def client_for(
    server: FakeServer,
    *,
    cache_path: Path | None = None,
    streaming: bool = True,
    poll_interval: float = 60.0,
) -> AsyncFlagstaffClient:
    return AsyncFlagstaffClient(
        SDK_KEY,
        base_url=BASE_URL,
        transport=server.transport,
        initial_reconnect_delay=0.01,
        max_reconnect_delay=0.02,
        cache_path=cache_path,
        streaming=streaming,
        poll_interval=poll_interval,
    )


@pytest.fixture
async def flags(server: FakeServer) -> AsyncIterator[AsyncFlagstaffClient]:
    async with client_for(server) as client:
        yield client


async def until(condition: Callable[[], bool], within: float = 2.0) -> None:
    async with asyncio.timeout(within):
        while not condition():
            await asyncio.sleep(0.005)


async def test_evaluates_with_the_rules_the_stream_opened_with(
    flags: AsyncFlagstaffClient,
) -> None:
    assert await flags.wait_until_ready(timeout=2)

    assert flags.ruleset_version == 1
    assert flags.bool_value("new-checkout", "user-7", default=False) is True
    assert flags.bool_value("new-checkout", "user-8", default=True) is False


async def test_picks_up_a_change_without_asking(
    flags: AsyncFlagstaffClient, server: FakeServer
) -> None:
    await flags.wait_until_ready(timeout=2)

    server.publish(storefront(2, checkout_enabled=False))
    await until(lambda: flags.ruleset_version == 2)

    detail = flags.bool_detail("new-checkout", "user-7", default=True)
    assert (detail.value, detail.reason) == (False, Reason.DISABLED)
    assert len(server.requests_to("/sdk/stream")) == 1


async def test_reconnects_from_the_version_it_holds(
    flags: AsyncFlagstaffClient, server: FakeServer
) -> None:
    await flags.wait_until_ready(timeout=2)

    server.drop_streams()
    await until(lambda: len(server.requests_to("/sdk/stream")) == 2 and server.open_streams == 1)

    assert server.requests_to("/sdk/stream")[-1].headers["Last-Event-ID"] == "1"


async def test_keeps_serving_the_last_rules_while_the_server_is_away(
    flags: AsyncFlagstaffClient, server: FakeServer
) -> None:
    await flags.wait_until_ready(timeout=2)
    server.reachable = False
    server.drop_streams()
    await until(lambda: len(server.requests_to("/sdk/stream")) >= 3)

    assert flags.bool_value("new-checkout", "user-7", default=False) is True

    server.reachable = True
    server.publish(storefront(5))
    await until(lambda: flags.ruleset_version == 5)


async def test_waits_for_a_server_that_is_down_at_start(server: FakeServer) -> None:
    server.reachable = False
    async with client_for(server) as flags:
        assert not await flags.wait_until_ready(timeout=0.1)
        assert flags.bool_detail("new-checkout", "user-7", default=False).reason is Reason.NOT_READY

        server.reachable = True

        assert await flags.wait_until_ready(timeout=2)


async def test_stops_for_good_when_the_key_is_rejected(server: FakeServer) -> None:
    async with AsyncFlagstaffClient(
        "fs_sdk_revoked", base_url=BASE_URL, transport=server.transport
    ) as flags:
        assert not await flags.wait_until_ready(timeout=0.2)

    assert len(server.requests) == 1


async def test_ignores_a_ruleset_it_cannot_read_and_keeps_listening(
    flags: AsyncFlagstaffClient, server: FakeServer
) -> None:
    await flags.wait_until_ready(timeout=2)

    server.send_raw('event: ruleset\nid: 2\ndata: {"format": 2, "version": 2, "flags": []}\n\n')
    server.publish(storefront(3))
    await until(lambda: flags.ruleset_version == 3)

    assert len(server.requests_to("/sdk/stream")) == 1


async def test_starts_from_the_cached_rules_when_the_server_is_down(
    server: FakeServer, tmp_path: Path
) -> None:
    cache = tmp_path / "prod.json"
    RulesetFile(cache).save(storefront(4))
    server.reachable = False

    async with client_for(server, cache_path=cache) as flags:
        assert await flags.wait_until_ready(timeout=1)
        assert flags.ruleset_version == 4

        server.reachable = True
        server.ruleset = storefront(6)
        await until(lambda: flags.ruleset_version == 6)

    await until(lambda: (cached := RulesetFile(cache).load()) is not None and cached.version == 6)


async def test_a_cache_already_current_is_not_sent_again(
    server: FakeServer, tmp_path: Path
) -> None:
    cache = tmp_path / "prod.json"
    RulesetFile(cache).save(storefront(1))

    async with client_for(server, cache_path=cache) as flags:
        await until(lambda: server.open_streams == 1)

        assert flags.ruleset_version == 1
        assert server.requests_to("/sdk/stream")[0].headers["Last-Event-ID"] == "1"


async def test_polls_instead_of_streaming_when_asked_to(server: FakeServer) -> None:
    async with client_for(server, streaming=False, poll_interval=0.02) as flags:
        assert await flags.wait_until_ready(timeout=2)
        await until(lambda: len(server.requests_to("/sdk/ruleset")) >= 3)

        server.ruleset = storefront(2)
        await until(lambda: flags.ruleset_version == 2)

    assert server.requests_to("/sdk/stream") == []
    assert server.requests_to("/sdk/ruleset")[1].headers["If-None-Match"] == '"1"'


async def test_closing_stops_every_request(server: FakeServer) -> None:
    async with client_for(server) as flags:
        await flags.wait_until_ready(timeout=2)
    requests_when_closed = len(server.requests)

    await asyncio.sleep(0.05)

    assert len(server.requests) == requests_when_closed
    assert server.open_streams == 0
