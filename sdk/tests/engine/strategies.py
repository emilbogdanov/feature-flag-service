from itertools import pairwise

from hypothesis import strategies as st

from flagstaff.engine.bucketing import BUCKET_COUNT
from flagstaff.engine.conditions import (
    AttributeCondition,
    Condition,
    Operator,
    UserListCondition,
)
from flagstaff.engine.context import AttributeValue, EvaluationContext
from flagstaff.engine.flag import Flag, Rule
from flagstaff.engine.serving import FixedVariant, Rollout, Serve, WeightedVariant
from flagstaff.engine.variants import FlagKind, JSONValue, Variant

VARIANT_KEYS = ["control", "treatment-a", "treatment-b", "holdout"]
KNOWN_USERS = [f"user-{n}" for n in range(1, 10)]
COUNTRIES = ["BG", "DE", "FR", "US", "JP"]
PLANS = ["free", "pro", "enterprise"]

flag_keys = st.from_regex(r"[A-Za-z0-9][A-Za-z0-9._-]{0,40}", fullmatch=True)
user_keys = st.text(min_size=1, max_size=40)
weights = st.integers(min_value=0, max_value=BUCKET_COUNT)


@st.composite
def splits(draw: st.DrawFn, *, variants: int) -> list[int]:
    cuts = sorted(draw(st.lists(weights, min_size=variants - 1, max_size=variants - 1)))
    return [upper - lower for lower, upper in pairwise([0, *cuts, BUCKET_COUNT])]


def rollout(keys: list[str], split: list[int]) -> Rollout:
    return Rollout(
        tuple(WeightedVariant(key, weight) for key, weight in zip(keys, split, strict=True))
    )


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
        AttributeCondition,
        attribute=st.just("email"),
        operator=st.sampled_from([Operator.CONTAINS, Operator.STARTS_WITH, Operator.ENDS_WITH]),
        values=st.lists(st.text(min_size=1, max_size=12), min_size=1, max_size=3).map(tuple),
        negate=st.booleans(),
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


json_values: st.SearchStrategy[JSONValue] = st.recursive(
    st.none()
    | st.booleans()
    | st.integers()
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(max_size=20),
    lambda children: (
        st.lists(children, max_size=4) | st.dictionaries(st.text(max_size=8), children, max_size=4)
    ),
    max_leaves=12,
)

_VALUES_BY_KIND: dict[FlagKind, st.SearchStrategy[JSONValue]] = {
    FlagKind.BOOLEAN: st.booleans(),
    FlagKind.STRING: st.text(max_size=30),
    FlagKind.NUMBER: st.integers() | st.floats(allow_nan=False, allow_infinity=False),
    FlagKind.JSON: json_values,
}


@st.composite
def flags(draw: st.DrawFn) -> Flag:
    kind = draw(st.sampled_from(FlagKind))
    variant_keys = draw(st.lists(st.sampled_from(VARIANT_KEYS), min_size=1, unique=True))
    variants = tuple(Variant(key, value=draw(_VALUES_BY_KIND[kind])) for key in variant_keys)
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
        kind=kind,
        variants=variants,
        enabled=draw(st.booleans()),
        off_variant=draw(st.sampled_from(variant_keys)),
        fallthrough=draw(serves(variant_keys)),
        rules=tuple(rules),
    )


attribute_values: st.SearchStrategy[AttributeValue] = st.one_of(
    st.sampled_from(COUNTRIES + PLANS),
    st.integers(min_value=0, max_value=600),
    st.booleans(),
    st.text(max_size=20),
)
contexts = st.builds(
    EvaluationContext,
    user_key=st.one_of(st.sampled_from(KNOWN_USERS), user_keys),
    attributes=st.dictionaries(
        st.sampled_from(["country", "plan", "seats", "email"]), attribute_values
    ),
)
