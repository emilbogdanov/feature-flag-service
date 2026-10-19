from collections import Counter
from itertools import pairwise

from hypothesis import given, settings
from hypothesis import strategies as st

from flagstaff.engine.bucketing import BUCKET_COUNT, bucket
from flagstaff.engine.conditions import (
    AttributeCondition,
    Condition,
    Operator,
    UserListCondition,
)
from flagstaff.engine.context import AttributeValue, EvaluationContext
from flagstaff.engine.evaluation import EvaluationReason
from flagstaff.engine.flag import Flag, Rule
from flagstaff.engine.serving import FixedVariant, Rollout, Serve, WeightedVariant
from flagstaff.engine.variants import FlagKind, Variant

flag_keys = st.from_regex(r"[A-Za-z0-9][A-Za-z0-9._-]{0,40}", fullmatch=True)
user_keys = st.text(min_size=1, max_size=40)
user_key_lists = st.lists(user_keys, min_size=1, max_size=50, unique=True)
weights = st.integers(min_value=0, max_value=BUCKET_COUNT)


@st.composite
def splits(draw: st.DrawFn, *, variants: int) -> list[int]:
    cuts = sorted(draw(st.lists(weights, min_size=variants - 1, max_size=variants - 1)))
    return [upper - lower for lower, upper in pairwise([0, *cuts, BUCKET_COUNT])]


def rollout(keys: list[str], split: list[int]) -> Rollout:
    return Rollout(
        tuple(WeightedVariant(key, weight) for key, weight in zip(keys, split, strict=True))
    )


def served(serve: Serve, flag_key: str, users: list[str], variant_key: str) -> set[str]:
    return {
        user
        for user in users
        if serve.variant_for(flag_key, EvaluationContext(user)) == variant_key
    }


@given(flag_key=flag_keys, user_key=user_keys)
def test_a_user_always_lands_in_the_same_bucket(flag_key: str, user_key: str) -> None:
    first = bucket(flag_key, user_key)

    assert 0 <= first < BUCKET_COUNT
    assert bucket(flag_key, user_key) == first


@given(
    flag_key=flag_keys, users=user_key_lists, percentages=st.lists(weights, min_size=2, max_size=2)
)
def test_raising_a_rollout_never_removes_anyone(
    flag_key: str, users: list[str], percentages: list[int]
) -> None:
    lower, higher = sorted(percentages)
    before = rollout(["on", "off"], [lower, BUCKET_COUNT - lower])
    after = rollout(["on", "off"], [higher, BUCKET_COUNT - higher])

    assert served(before, flag_key, users, "on") <= served(after, flag_key, users, "on")


@given(
    flag_key=flag_keys,
    users=user_key_lists,
    split=st.integers(min_value=2, max_value=5).flatmap(lambda count: splits(variants=count)),
    data=st.data(),
)
def test_growing_a_variant_from_its_neighbour_keeps_everyone_it_had(
    flag_key: str, users: list[str], split: list[int], data: st.DataObject
) -> None:
    keys = [f"variant-{index}" for index in range(len(split))]
    grown = data.draw(st.integers(min_value=0, max_value=len(split) - 1), label="grown")
    neighbour = data.draw(
        st.sampled_from([index for index in (grown - 1, grown + 1) if 0 <= index < len(split)]),
        label="neighbour",
    )
    moved = data.draw(st.integers(min_value=0, max_value=split[neighbour]), label="moved")
    new_split = list(split)
    new_split[grown] += moved
    new_split[neighbour] -= moved

    before = served(rollout(keys, split), flag_key, users, keys[grown])
    after = served(rollout(keys, new_split), flag_key, users, keys[grown])

    assert before <= after


# Sequential ids are the realistic worst case for a weak hash: the inputs differ in a digit or
# two. Each tenth of the buckets should get 2,000 of the 20,000 users; 12% either way is more
# than five standard deviations, so a failure here means skew, not bad luck.
@settings(max_examples=25)
@given(flag_key=flag_keys)
def test_users_spread_evenly_across_buckets(flag_key: str) -> None:
    deciles = Counter(bucket(flag_key, f"user-{n}") * 10 // BUCKET_COUNT for n in range(20_000))

    assert all(1_760 <= deciles[decile] <= 2_240 for decile in range(10))


VARIANT_KEYS = ["control", "treatment-a", "treatment-b", "holdout"]
KNOWN_USERS = [f"user-{n}" for n in range(1, 10)]
COUNTRIES = ["BG", "DE", "FR", "US", "JP"]
PLANS = ["free", "pro", "enterprise"]

conditions: st.SearchStrategy[Condition] = st.one_of(
    st.builds(
        AttributeCondition,
        attribute=st.just("country"),
        operator=st.just(Operator.IN),
        values=st.lists(st.sampled_from(COUNTRIES), min_size=1, unique=True).map(tuple),
        negate=st.booleans(),
    ),
    st.builds(
        AttributeCondition,
        attribute=st.just("plan"),
        operator=st.just(Operator.IN),
        values=st.lists(st.sampled_from(PLANS), min_size=1, unique=True).map(tuple),
        negate=st.booleans(),
    ),
    st.builds(
        AttributeCondition,
        attribute=st.just("seats"),
        operator=st.sampled_from([Operator.GREATER_THAN, Operator.LESS_THAN_OR_EQUAL]),
        values=st.integers(min_value=1, max_value=500).map(lambda seats: (seats,)),
    ),
    st.builds(
        UserListCondition,
        st.frozensets(st.sampled_from(KNOWN_USERS), min_size=1),
    ),
)


@st.composite
def serves(draw: st.DrawFn, variant_keys: list[str]) -> Serve:
    if draw(st.booleans()):
        return FixedVariant(draw(st.sampled_from(variant_keys)))
    return rollout(variant_keys, draw(splits(variants=len(variant_keys))))


@st.composite
def flags(draw: st.DrawFn) -> Flag:
    variant_keys = draw(st.lists(st.sampled_from(VARIANT_KEYS), min_size=1, unique=True))
    rules = [
        Rule(
            id=f"rule-{index}",
            conditions=tuple(draw(st.lists(conditions, min_size=1, max_size=3))),
            serve=draw(serves(variant_keys)),
        )
        for index in range(draw(st.integers(min_value=0, max_value=5)))
    ]
    return Flag(
        key=draw(flag_keys),
        kind=FlagKind.STRING,
        variants=tuple(Variant(key, value=key) for key in variant_keys),
        enabled=draw(st.booleans()),
        off_variant=draw(st.sampled_from(variant_keys)),
        fallthrough=draw(serves(variant_keys)),
        rules=tuple(rules),
    )


attribute_values: st.SearchStrategy[AttributeValue] = st.one_of(
    st.sampled_from(COUNTRIES + PLANS), st.integers(min_value=0, max_value=600), st.booleans()
)
contexts = st.builds(
    EvaluationContext,
    user_key=st.one_of(st.sampled_from(KNOWN_USERS), user_keys),
    attributes=st.dictionaries(st.sampled_from(["country", "plan", "seats"]), attribute_values),
)


# The reference below restates the evaluation order as plainly as possible; Flag.evaluate has
# to agree with it on every flag and context Hypothesis can come up with.
@given(flag=flags(), context=contexts)
def test_evaluation_serves_the_first_matching_rule_or_the_fallthrough(
    flag: Flag, context: EvaluationContext
) -> None:
    evaluation = flag.evaluate(context)
    matching = [rule for rule in flag.rules if rule.matches(context)]

    assert evaluation.variant in flag.variants
    if not flag.enabled:
        assert evaluation.reason is EvaluationReason.DISABLED
        assert evaluation.variant.key == flag.off_variant
    elif matching:
        assert evaluation.reason is EvaluationReason.RULE_MATCH
        assert evaluation.rule_id == matching[0].id
        assert evaluation.variant.key == matching[0].serve.variant_for(flag.key, context)
    else:
        assert evaluation.reason is EvaluationReason.FALLTHROUGH
        assert evaluation.variant.key == flag.fallthrough.variant_for(flag.key, context)
