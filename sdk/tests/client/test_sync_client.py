import threading
import time
from collections.abc import Callable, Iterator

import pytest

from flagstaff import EvaluationContext, FlagstaffClient, Reason
from tests.client.fake_server import BASE_URL, SDK_KEY, FakeServer
from tests.client.rulesets import storefront


@pytest.fixture
def server() -> FakeServer:
    return FakeServer(storefront(1))


@pytest.fixture
def flags(server: FakeServer) -> Iterator[FlagstaffClient]:
    with FlagstaffClient(
        SDK_KEY,
        base_url=BASE_URL,
        transport=server.transport,
        initial_reconnect_delay=0.01,
        max_reconnect_delay=0.02,
    ) as client:
        yield client


def until(condition: Callable[[], bool], within: float = 2.0) -> None:
    deadline = time.monotonic() + within
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.005)


def test_evaluates_without_an_event_loop(flags: FlagstaffClient) -> None:
    assert flags.wait_until_ready(timeout=2)

    user = EvaluationContext("user-310", {"country": "BG"})
    assert flags.str_value("checkout-theme", user, default="classic") == "spruce"
    assert flags.bool_value("new-checkout", "user-7", default=False) is True


def test_picks_up_a_change_in_the_background(flags: FlagstaffClient, server: FakeServer) -> None:
    flags.wait_until_ready(timeout=2)

    server.publish(storefront(2, checkout_enabled=False))
    until(lambda: flags.ruleset_version == 2)

    assert flags.bool_detail("new-checkout", "user-7", default=True).reason is Reason.DISABLED


def test_any_thread_can_evaluate_while_the_rules_change(
    flags: FlagstaffClient, server: FakeServer
) -> None:
    flags.wait_until_ready(timeout=2)
    seen: list[bool] = []

    def evaluate_many() -> None:
        seen.extend(flags.bool_value("new-checkout", "user-7", default=True) for _ in range(5_000))

    workers = [threading.Thread(target=evaluate_many) for _ in range(4)]
    for worker in workers:
        worker.start()
    for version in range(2, 12):
        server.publish(storefront(version, checkout_enabled=version % 2 == 0))
    for worker in workers:
        worker.join()

    assert len(seen) == 20_000
    until(lambda: flags.ruleset_version == 11)


def test_closing_stops_the_background_thread(server: FakeServer) -> None:
    client = FlagstaffClient(SDK_KEY, base_url=BASE_URL, transport=server.transport)
    client.wait_until_ready(timeout=2)
    updater = [thread for thread in threading.enumerate() if thread.name == "flagstaff-updater"]

    client.close()

    assert updater
    assert not any(thread.is_alive() for thread in updater)
    until(lambda: server.open_streams == 0)


def test_closing_a_client_that_never_got_rules_is_quick(server: FakeServer) -> None:
    server.reachable = False
    client = FlagstaffClient(SDK_KEY, base_url=BASE_URL, transport=server.transport)
    started = time.monotonic()

    client.close()

    assert time.monotonic() - started < 1
    assert client.bool_value("new-checkout", "user-7", default=True) is True
