import pytest

from flagstaff.engine.bucketing import BUCKET_COUNT, bucket

USERS = [f"user-{number}" for number in range(20_000)]


# Pinned on purpose. If any of these change, every running rollout reshuffles its users and
# SDKs on the old version disagree with the server about who gets what.
@pytest.mark.parametrize(
    ("flag_key", "user_key", "expected"),
    [
        ("new-checkout", "user-1042", 27_649),
        ("new-checkout", "user-1043", 69_033),
        ("search-v2", "user-1042", 52_556),
        ("dark-mode", "8f14e45f-ceea-467f-a0e6-b2c9f3c0a1d4", 57_036),
    ],
)
def test_buckets_are_fixed_for_good(flag_key: str, user_key: str, expected: int) -> None:
    assert bucket(flag_key, user_key) == expected


def test_every_bucket_is_in_range() -> None:
    assert all(0 <= bucket("new-checkout", user) < BUCKET_COUNT for user in USERS)


def test_being_early_in_one_rollout_says_nothing_about_another() -> None:
    tenth = BUCKET_COUNT // 10
    early_for_checkout = [user for user in USERS if bucket("new-checkout", user) < tenth]
    early_for_both = [user for user in early_for_checkout if bucket("search-v2", user) < tenth]

    # Independent flags put about a tenth of checkout's first 10% into search's first 10% too.
    share = len(early_for_both) / len(early_for_checkout)
    assert 0.08 < share < 0.12


def test_a_key_with_a_lone_surrogate_still_gets_a_bucket() -> None:
    assert 0 <= bucket("new-checkout", "user-\ud800") < BUCKET_COUNT
