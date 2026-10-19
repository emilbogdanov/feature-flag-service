import threading

from flagstaff._store import RulesetStore
from tests.client.rulesets import storefront


def test_starts_empty_and_not_ready() -> None:
    store = RulesetStore()

    assert store.ruleset is None
    assert store.wait_until_ready(timeout=0) is False


def test_takes_newer_rulesets_and_ignores_older_ones() -> None:
    store = RulesetStore()

    assert store.replace(storefront(3)) is True
    assert store.replace(storefront(2)) is False
    assert store.replace(storefront(3)) is False
    assert store.replace(storefront(4)) is True

    assert store.ruleset is not None
    assert store.ruleset.version == 4


def test_becomes_ready_with_its_first_ruleset() -> None:
    store = RulesetStore()
    readiness: list[bool] = []
    waiter = threading.Thread(target=lambda: readiness.append(store.wait_until_ready(timeout=2)))
    waiter.start()

    store.replace(storefront(1))
    waiter.join()

    assert readiness == [True]


def test_racing_writers_leave_the_newest_ruleset() -> None:
    store = RulesetStore()
    rulesets = [storefront(version) for version in range(1, 201)]
    writers = [
        threading.Thread(target=lambda chunk=chunk: [store.replace(r) for r in chunk])
        for chunk in (rulesets[0::3], rulesets[1::3], rulesets[2::3])
    ]

    for writer in writers:
        writer.start()
    for writer in writers:
        writer.join()

    assert store.ruleset is not None
    assert store.ruleset.version == 200
