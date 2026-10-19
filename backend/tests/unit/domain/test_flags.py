from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from flagstaff.engine.conditions import AttributeCondition, Operator, UserListCondition
from flagstaff.engine.context import EvaluationContext
from flagstaff.engine.evaluation import EvaluationReason
from flagstaff.engine.flag import Rule
from flagstaff.engine.serving import FixedVariant, Rollout, WeightedVariant
from flagstaff.engine.variants import FlagKind, Variant

from flagstaff_server.domain.errors import (
    ArchivedFlagError,
    InvalidTargetingError,
    InvalidValueError,
)
from flagstaff_server.domain.flags import Flag, Targeting
from flagstaff_server.domain.ids import EnvironmentId, FlagId, ProjectId
from flagstaff_server.domain.values import Description, Name

CREATED_AT = datetime(2026, 10, 19, 9, 30, tzinfo=UTC)
LATER = CREATED_AT + timedelta(hours=2)
DEV = EnvironmentId(uuid4())
PROD = EnvironmentId(uuid4())
ON = Variant("on", value=True)
OFF = Variant("off", value=False)

BETA_TESTERS = Rule(
    id="beta-testers",
    conditions=(UserListCondition(frozenset({"user-7", "user-1042"})),),
    serve=FixedVariant("on"),
)
EU_ROLLOUT = Rule(
    id="eu-rollout",
    conditions=(
        AttributeCondition(attribute="country", operator=Operator.IN, values=("BG", "DE")),
    ),
    serve=Rollout((WeightedVariant("on", 10_000), WeightedVariant("off", 90_000))),
)


def new_checkout(variants: tuple[Variant, ...] = (ON, OFF), off_variant: str = "off") -> Flag:
    return Flag.create(
        flag_id=FlagId(uuid4()),
        project_id=ProjectId(uuid4()),
        key="new-checkout",
        name=Name("New checkout"),
        description=Description("Two-step checkout with saved cards"),
        kind=FlagKind.BOOLEAN,
        variants=variants,
        off_variant=off_variant,
        on_variant="on",
        at=CREATED_AT,
    )


def targeting(*rules: Rule, enabled: bool = True) -> Targeting:
    return Targeting(
        enabled=enabled, off_variant="off", fallthrough=FixedVariant("off"), rules=rules
    )


class TestCreate:
    def test_starts_off_everywhere(self) -> None:
        flag = new_checkout()

        evaluation = flag.compile_for(PROD).evaluate(EvaluationContext("user-7"))

        assert evaluation.variant == OFF
        assert evaluation.reason is EvaluationReason.DISABLED
        assert flag.version == 1
        assert flag.updated_at == CREATED_AT

    def test_serves_the_on_variant_to_everyone_once_switched_on(self) -> None:
        flag = new_checkout()

        flag.enable(PROD, at=LATER)

        assert flag.compile_for(PROD).evaluate(EvaluationContext("user-7")).variant == ON
        assert flag.compile_for(DEV).evaluate(EvaluationContext("user-7")).variant == OFF

    def test_rejects_a_key_sdks_could_not_ask_for(self) -> None:
        with pytest.raises(InvalidValueError, match="flag key 'new checkout'"):
            Flag.create(
                flag_id=FlagId(uuid4()),
                project_id=ProjectId(uuid4()),
                key="new checkout",
                name=Name("New checkout"),
                description=Description(),
                kind=FlagKind.BOOLEAN,
                variants=(ON, OFF),
                off_variant="off",
                on_variant="on",
                at=CREATED_AT,
            )

    def test_rejects_starting_variants_it_does_not_have(self) -> None:
        with pytest.raises(InvalidTargetingError, match=r"new environments: .*\['disabled'\]"):
            new_checkout(off_variant="disabled")

    def test_rejects_variants_of_the_wrong_kind(self) -> None:
        with pytest.raises(InvalidTargetingError, match="boolean flag, but variant 'on' is 'yes'"):
            new_checkout(variants=(Variant("on", value="yes"), OFF))


class TestTargeting:
    def test_each_environment_keeps_its_own_rules(self) -> None:
        flag = new_checkout()

        flag.change_targeting(PROD, targeting(BETA_TESTERS), at=LATER)

        assert (
            flag.compile_for(PROD).evaluate(EvaluationContext("user-7")).rule_id == "beta-testers"
        )
        assert flag.compile_for(DEV).evaluate(EvaluationContext("user-7")).rule_id is None
        assert flag.targeting == {PROD: targeting(BETA_TESTERS)}
        assert flag.updated_at == LATER

    def test_rejects_rules_that_serve_a_variant_the_flag_lacks(self) -> None:
        flag = new_checkout()
        legacy = Rule(id="legacy", conditions=BETA_TESTERS.conditions, serve=FixedVariant("legacy"))

        with pytest.raises(InvalidTargetingError, match=r"rule 'legacy'.*\['legacy'\]"):
            flag.change_targeting(PROD, targeting(legacy), at=LATER)

        assert flag.targeting_in(PROD) == flag.initial_targeting

    def test_switching_reports_whether_anything_changed(self) -> None:
        flag = new_checkout()

        assert flag.enable(PROD, at=LATER) is True
        assert flag.enable(PROD, at=LATER) is False
        assert flag.disable(PROD, at=LATER) is True
        assert flag.disable(PROD, at=LATER) is False
        assert flag.disable(DEV, at=LATER) is False

    def test_switching_keeps_the_rules(self) -> None:
        flag = new_checkout()
        flag.change_targeting(PROD, targeting(BETA_TESTERS, enabled=False), at=LATER)

        flag.enable(PROD, at=LATER)

        assert flag.targeting_in(PROD) == targeting(BETA_TESTERS, enabled=True)


class TestVariants:
    def test_can_add_a_variant(self) -> None:
        flag = new_checkout()
        holdout = Variant("holdout", value=False)

        flag.change_variants((ON, OFF, holdout), at=LATER)

        assert flag.variants == (ON, OFF, holdout)

    def test_refuses_to_drop_a_variant_an_environment_still_serves(self) -> None:
        flag = new_checkout(variants=(ON, OFF, Variant("holdout", value=False)))
        flag.change_targeting(
            PROD,
            Targeting(enabled=True, off_variant="holdout", fallthrough=FixedVariant("off")),
            at=LATER,
        )

        with pytest.raises(InvalidTargetingError, match=r"^the off variant") as raised:
            flag.change_variants((ON, OFF), at=LATER)

        assert raised.value.environment_id == PROD
        assert len(flag.variants) == 3

    def test_refuses_to_drop_a_variant_new_environments_start_with(self) -> None:
        flag = new_checkout()

        with pytest.raises(InvalidTargetingError, match="new environments"):
            flag.change_variants((OFF,), at=LATER)


class TestArchive:
    def test_an_archived_flag_cannot_change(self) -> None:
        flag = new_checkout()
        flag.archive(at=LATER)

        assert flag.is_archived
        assert flag.archived_at == LATER
        with pytest.raises(ArchivedFlagError, match="new-checkout"):
            flag.enable(PROD, at=LATER)
        with pytest.raises(ArchivedFlagError):
            flag.change_details(name=Name("Checkout v3"), description=Description(), at=LATER)
        with pytest.raises(ArchivedFlagError):
            flag.archive(at=LATER)


def test_saving_moves_the_version_on() -> None:
    flag = new_checkout()

    flag.mark_saved()

    assert flag.version == 2


def test_targeting_round_trips_through_its_document() -> None:
    original = targeting(BETA_TESTERS, EU_ROLLOUT)

    assert Targeting.from_document(original.to_document()) == original
