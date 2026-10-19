from flagstaff._backoff import Backoff


def test_the_ceiling_doubles_up_to_the_maximum() -> None:
    backoff = Backoff(base_seconds=0.5, max_seconds=4.0, jitter=lambda: 1.0)

    assert [backoff.next_delay() for _ in range(6)] == [0.5, 1.0, 2.0, 4.0, 4.0, 4.0]


def test_each_wait_is_a_random_share_of_the_ceiling() -> None:
    backoff = Backoff(base_seconds=1.0, max_seconds=60.0, jitter=lambda: 0.25)

    assert [backoff.next_delay() for _ in range(3)] == [0.25, 0.5, 1.0]


def test_a_reset_starts_again_from_the_base() -> None:
    backoff = Backoff(base_seconds=0.5, max_seconds=30.0, jitter=lambda: 1.0)
    for _ in range(5):
        backoff.next_delay()

    backoff.reset()

    assert backoff.next_delay() == 0.5


def test_waiting_for_ever_does_not_overflow() -> None:
    backoff = Backoff(base_seconds=0.5, max_seconds=30.0, jitter=lambda: 1.0)

    delays = [backoff.next_delay() for _ in range(2_000)]

    assert delays[-1] == 30.0
