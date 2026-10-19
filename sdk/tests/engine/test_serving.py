import pytest

from flagstaff.engine.bucketing import BUCKET_COUNT, bucket
from flagstaff.engine.context import EvaluationContext
from flagstaff.engine.errors import InvalidFlagError
from flagstaff.engine.serving import FixedVariant, Rollout, WeightedVariant

FLAG = "new-checkout"
USER = EvaluationContext("user-1042")
USER_BUCKET = bucket(FLAG, USER.user_key)


def split(*weights: tuple[str, int]) -> Rollout:
    return Rollout(tuple(WeightedVariant(key, weight) for key, weight in weights))


def test_a_fixed_variant_is_served_to_everyone() -> None:
    serve = FixedVariant("on")

    assert serve.variant_for(FLAG, USER) == "on"
    assert serve.variant_for(FLAG, EvaluationContext("user-1043")) == "on"
    assert serve.variant_keys == {"on"}


class TestRollout:
    def test_serves_the_variant_whose_range_holds_the_users_bucket(self) -> None:
        just_in = split(("on", USER_BUCKET + 1), ("off", BUCKET_COUNT - USER_BUCKET - 1))
        just_out = split(("on", USER_BUCKET), ("off", BUCKET_COUNT - USER_BUCKET))

        assert just_in.variant_for(FLAG, USER) == "on"
        assert just_out.variant_for(FLAG, USER) == "off"

    def test_buckets_by_flag_key_and_user_key(self) -> None:
        search_bucket = bucket("search-v2", USER.user_key)
        # "on" owns exactly one bucket: the one this user lands in for search-v2.
        rollout = split(
            ("off", search_bucket), ("on", 1), ("rest", BUCKET_COUNT - search_bucket - 1)
        )

        assert rollout.variant_for("search-v2", USER) == "on"
        assert rollout.variant_for(FLAG, USER) != "on"

    def test_never_serves_a_variant_with_no_weight(self) -> None:
        rollout = split(("control", 0), ("treatment", BUCKET_COUNT), ("holdout", 0))
        users = [EvaluationContext(f"user-{number}") for number in range(2_000)]

        assert {rollout.variant_for(FLAG, user) for user in users} == {"treatment"}

    def test_splits_users_roughly_by_weight(self) -> None:
        rollout = split(("control", 50_000), ("treatment", 30_000), ("holdout", 20_000))
        served = [rollout.variant_for(FLAG, EvaluationContext(f"user-{n}")) for n in range(20_000)]

        assert served.count("control") == pytest.approx(10_000, rel=0.05)
        assert served.count("treatment") == pytest.approx(6_000, rel=0.05)
        assert served.count("holdout") == pytest.approx(4_000, rel=0.05)

    def test_lists_its_variants(self) -> None:
        assert split(("on", 1_000), ("off", 99_000)).variant_keys == {"on", "off"}

    @pytest.mark.parametrize(
        ("weights", "message"),
        [
            ((), "at least one variant"),
            ((("on", 50_000), ("on", 50_000)), "more than once"),
            ((("on", 10_000), ("off", 80_000)), "add up to 90000"),
            ((("on", 60_000), ("off", 50_000)), "add up to 110000"),
        ],
    )
    def test_rejects_splits_that_dont_cover_every_bucket_once(
        self, weights: tuple[tuple[str, int], ...], message: str
    ) -> None:
        with pytest.raises(InvalidFlagError, match=message):
            split(*weights)

    @pytest.mark.parametrize("weight", [-1, BUCKET_COUNT + 1])
    def test_rejects_weights_outside_the_bucket_range(self, weight: int) -> None:
        with pytest.raises(InvalidFlagError, match="weights run from 0"):
            WeightedVariant("on", weight)
