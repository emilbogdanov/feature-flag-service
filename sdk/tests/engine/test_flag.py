import pytest

from flagstaff.engine.bucketing import BUCKET_COUNT, bucket
from flagstaff.engine.conditions import AttributeCondition, Operator, UserListCondition
from flagstaff.engine.context import AttributeValue, EvaluationContext
from flagstaff.engine.errors import InvalidFlagError
from flagstaff.engine.evaluation import EvaluationReason
from flagstaff.engine.flag import Flag, Rule
from flagstaff.engine.serving import FixedVariant, Rollout, Serve, WeightedVariant
from flagstaff.engine.variants import FlagKind, Variant

ON = Variant("on", value=True)
OFF = Variant("off", value=False)
SERVE_OFF = FixedVariant("off")

STAFF = Rule(
    id="staff",
    conditions=(
        AttributeCondition(
            attribute="email", operator=Operator.ENDS_WITH, values=("@flagstaff.dev",)
        ),
    ),
    serve=FixedVariant("on"),
)
BETA_TESTERS = Rule(
    id="beta-testers",
    conditions=(UserListCondition(frozenset({"user-7", "user-1042"})),),
    serve=FixedVariant("on"),
)
EU_PRO = Rule(
    id="eu-pro",
    conditions=(
        AttributeCondition(attribute="country", operator=Operator.IN, values=("BG", "DE", "FR")),
        AttributeCondition(attribute="plan", operator=Operator.IN, values=("pro", "enterprise")),
    ),
    serve=Rollout((WeightedVariant("on", 25_000), WeightedVariant("off", 75_000))),
)


def new_checkout(
    *,
    enabled: bool = True,
    rules: tuple[Rule, ...] = (STAFF, BETA_TESTERS, EU_PRO),
    fallthrough: Serve = SERVE_OFF,
) -> Flag:
    return Flag(
        key="new-checkout",
        kind=FlagKind.BOOLEAN,
        variants=(ON, OFF),
        enabled=enabled,
        off_variant="off",
        fallthrough=fallthrough,
        rules=rules,
    )


def user(key: str = "user-310", **attributes: AttributeValue) -> EvaluationContext:
    return EvaluationContext(key, attributes)


class TestEvaluate:
    def test_a_disabled_flag_serves_its_off_variant_whatever_the_rules_say(self) -> None:
        evaluation = new_checkout(enabled=False).evaluate(user(email="mira@flagstaff.dev"))

        assert evaluation.variant == OFF
        assert evaluation.reason is EvaluationReason.DISABLED
        assert evaluation.rule_id is None

    def test_serves_the_first_rule_that_matches(self) -> None:
        evaluation = new_checkout().evaluate(user("user-7", email="mira@flagstaff.dev"))

        assert evaluation.value is True
        assert evaluation.reason is EvaluationReason.RULE_MATCH
        assert evaluation.rule_id == "staff"

    def test_rule_order_decides_between_matching_rules(self) -> None:
        excluded_testers = Rule(
            id="excluded",
            conditions=(UserListCondition(frozenset({"user-7"})),),
            serve=FixedVariant("off"),
        )
        flag = new_checkout(rules=(excluded_testers, BETA_TESTERS))

        assert flag.evaluate(user("user-7")).rule_id == "excluded"
        assert flag.evaluate(user("user-1042")).rule_id == "beta-testers"

    def test_a_rule_matches_only_when_all_its_conditions_do(self) -> None:
        flag = new_checkout(rules=(EU_PRO,))

        assert flag.evaluate(user(country="BG", plan="pro")).rule_id == "eu-pro"
        assert flag.evaluate(user(country="BG", plan="free")).reason is EvaluationReason.FALLTHROUGH
        assert flag.evaluate(user(country="US", plan="pro")).reason is EvaluationReason.FALLTHROUGH

    def test_falls_through_when_no_rule_matches(self) -> None:
        evaluation = new_checkout().evaluate(user(country="US", plan="free"))

        assert evaluation.variant == OFF
        assert evaluation.reason is EvaluationReason.FALLTHROUGH
        assert evaluation.rule_id is None

    def test_rollouts_bucket_on_the_flags_own_key(self) -> None:
        position = bucket("new-checkout", "user-310")
        just_includes_user = Rollout(
            (
                WeightedVariant("on", position + 1),
                WeightedVariant("off", BUCKET_COUNT - position - 1),
            )
        )

        evaluation = new_checkout(rules=(), fallthrough=just_includes_user).evaluate(user())

        assert evaluation.variant == ON

    def test_gives_the_same_answer_every_time(self) -> None:
        flag = new_checkout()
        contexts = [user(f"user-{n}", country="DE", plan="pro") for n in range(500)]

        first = [flag.evaluate(context) for context in contexts]
        second = [flag.evaluate(context) for context in contexts]

        assert first == second
        assert {evaluation.variant for evaluation in first} == {ON, OFF}


class TestDefinition:
    @pytest.mark.parametrize("key", ["", "new checkout", "checkout:v2", "_private"])
    def test_rejects_malformed_flag_keys(self, key: str) -> None:
        with pytest.raises(InvalidFlagError, match="flag key"):
            Flag(
                key=key,
                kind=FlagKind.BOOLEAN,
                variants=(ON, OFF),
                enabled=True,
                off_variant="off",
                fallthrough=SERVE_OFF,
            )

    def test_needs_a_variant(self) -> None:
        with pytest.raises(InvalidFlagError, match="at least one variant"):
            Flag(
                key="new-checkout",
                kind=FlagKind.BOOLEAN,
                variants=(),
                enabled=True,
                off_variant="off",
                fallthrough=SERVE_OFF,
            )

    def test_rejects_repeated_variant_keys(self) -> None:
        with pytest.raises(InvalidFlagError, match=r"variants more than once: \['on'\]"):
            Flag(
                key="new-checkout",
                kind=FlagKind.BOOLEAN,
                variants=(ON, OFF, Variant("on", value=False)),
                enabled=True,
                off_variant="off",
                fallthrough=SERVE_OFF,
            )

    def test_rejects_variants_of_the_wrong_kind(self) -> None:
        with pytest.raises(InvalidFlagError, match="number flag, but variant 'wide' is 'wide'"):
            Flag(
                key="sidebar-width",
                kind=FlagKind.NUMBER,
                variants=(Variant("narrow", value=240), Variant("wide", value="wide")),
                enabled=True,
                off_variant="narrow",
                fallthrough=FixedVariant("narrow"),
            )

    def test_rejects_an_unknown_off_variant(self) -> None:
        with pytest.raises(InvalidFlagError, match="off variant"):
            Flag(
                key="new-checkout",
                kind=FlagKind.BOOLEAN,
                variants=(ON, OFF),
                enabled=False,
                off_variant="disabled",
                fallthrough=SERVE_OFF,
            )

    def test_rejects_a_fallthrough_to_an_unknown_variant(self) -> None:
        with pytest.raises(InvalidFlagError, match=r"fallthrough .* \['holdout'\]"):
            new_checkout(
                fallthrough=Rollout(
                    (WeightedVariant("on", 50_000), WeightedVariant("holdout", 50_000))
                )
            )

    def test_rejects_a_rule_serving_an_unknown_variant(self) -> None:
        legacy = Rule(id="legacy", conditions=STAFF.conditions, serve=FixedVariant("legacy"))

        with pytest.raises(InvalidFlagError, match=r"rule 'legacy' .* \['legacy'\]"):
            new_checkout(rules=(legacy,))

    def test_rejects_repeated_rule_ids(self) -> None:
        with pytest.raises(InvalidFlagError, match=r"rule ids more than once: \['staff'\]"):
            new_checkout(rules=(STAFF, BETA_TESTERS, STAFF))

    def test_a_rule_needs_a_condition(self) -> None:
        with pytest.raises(InvalidFlagError, match="at least one condition"):
            Rule(id="everyone", conditions=(), serve=FixedVariant("on"))

    def test_a_rule_needs_a_well_formed_id(self) -> None:
        with pytest.raises(InvalidFlagError, match="rule key"):
            Rule(id="", conditions=STAFF.conditions, serve=FixedVariant("on"))

    def test_json_flags_serve_structured_values(self) -> None:
        limits = Variant("generous", value={"uploads_per_day": 500, "formats": ["png", "webp"]})
        flag = Flag(
            key="upload-limits",
            kind=FlagKind.JSON,
            variants=(Variant("default", value={"uploads_per_day": 50}), limits),
            enabled=True,
            off_variant="default",
            fallthrough=FixedVariant("generous"),
        )

        assert flag.evaluate(user()).value == {"uploads_per_day": 500, "formats": ["png", "webp"]}
