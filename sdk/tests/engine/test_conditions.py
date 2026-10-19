import math

import pytest

from flagstaff.engine.conditions import AttributeCondition, Operator, UserListCondition
from flagstaff.engine.context import AttributeValue, EvaluationContext
from flagstaff.engine.errors import InvalidFlagError


def user(**attributes: AttributeValue) -> EvaluationContext:
    return EvaluationContext("user-1042", attributes)


def condition(
    attribute: str, operator: Operator, *values: AttributeValue, negate: bool = False
) -> AttributeCondition:
    return AttributeCondition(attribute=attribute, operator=operator, values=values, negate=negate)


class TestIn:
    def test_matches_any_listed_value(self) -> None:
        eu = condition("country", Operator.IN, "BG", "DE", "FR")

        assert eu.matches(user(country="DE"))
        assert not eu.matches(user(country="US"))

    def test_compares_text_exactly(self) -> None:
        assert not condition("country", Operator.IN, "BG").matches(user(country="bg"))

    def test_treats_whole_and_fractional_numbers_alike(self) -> None:
        assert condition("seats", Operator.IN, 10).matches(user(seats=10.0))

    def test_does_not_confuse_booleans_with_numbers(self) -> None:
        beta = AttributeCondition(attribute="beta", operator=Operator.IN, values=(True,))

        assert not beta.matches(user(beta=1))
        assert beta.matches(user(beta=True))
        assert not condition("seats", Operator.IN, 1).matches(user(seats=True))

    def test_negated_matches_everything_not_listed(self) -> None:
        not_eu = condition("country", Operator.IN, "BG", "DE", negate=True)

        assert not_eu.matches(user(country="US"))
        assert not not_eu.matches(user(country="BG"))


class TestText:
    def test_contains(self) -> None:
        staff = condition("email", Operator.CONTAINS, "@flagstaff.", "@flagstaff-contractors.")

        assert staff.matches(user(email="mira@flagstaff.dev"))
        assert not staff.matches(user(email="mira@example.com"))

    def test_starts_with(self) -> None:
        beta = condition("app_version", Operator.STARTS_WITH, "4.2.", "4.3.")

        assert beta.matches(user(app_version="4.3.1"))
        assert not beta.matches(user(app_version="4.1.9"))

    def test_ends_with(self) -> None:
        bulgarian = condition("email", Operator.ENDS_WITH, ".bg")

        assert bulgarian.matches(user(email="ivan@abv.bg"))
        assert not bulgarian.matches(user(email="ivan@abv.bg.example.com"))

    @pytest.mark.parametrize(
        "operator", [Operator.CONTAINS, Operator.STARTS_WITH, Operator.ENDS_WITH]
    )
    def test_never_matches_a_non_text_attribute(self, operator: Operator) -> None:
        assert not condition("seats", operator, "1").matches(user(seats=1))

    @pytest.mark.parametrize(
        "operator", [Operator.CONTAINS, Operator.STARTS_WITH, Operator.ENDS_WITH]
    )
    def test_rejects_non_text_values(self, operator: Operator) -> None:
        with pytest.raises(InvalidFlagError, match="compares text"):
            condition("email", operator, ".bg", 7)


class TestComparison:
    @pytest.mark.parametrize(
        ("operator", "seats", "expected"),
        [
            (Operator.LESS_THAN, 9, True),
            (Operator.LESS_THAN, 10, False),
            (Operator.LESS_THAN_OR_EQUAL, 10, True),
            (Operator.LESS_THAN_OR_EQUAL, 10.5, False),
            (Operator.GREATER_THAN, 11, True),
            (Operator.GREATER_THAN, 10, False),
            (Operator.GREATER_THAN_OR_EQUAL, 10.0, True),
            (Operator.GREATER_THAN_OR_EQUAL, 9.99, False),
        ],
    )
    def test_compares_against_the_bound(
        self, operator: Operator, seats: float, *, expected: bool
    ) -> None:
        assert condition("seats", operator, 10).matches(user(seats=seats)) is expected

    @pytest.mark.parametrize("seats", ["50", True, math.nan])
    def test_never_matches_a_value_that_is_not_a_comparable_number(
        self, seats: AttributeValue
    ) -> None:
        assert not condition("seats", Operator.GREATER_THAN, 10).matches(user(seats=seats))

    @pytest.mark.parametrize(
        "values",
        [(10, 20), ("10",), (True,), (math.inf,), (math.nan,)],
        ids=["two numbers", "text", "boolean", "infinity", "nan"],
    )
    def test_rejects_anything_but_one_finite_number(
        self, values: tuple[AttributeValue, ...]
    ) -> None:
        with pytest.raises(InvalidFlagError, match="exactly one finite number"):
            condition("seats", Operator.GREATER_THAN, *values)


def test_a_missing_attribute_fails_even_a_negated_condition() -> None:
    not_enterprise = condition("plan", Operator.IN, "enterprise", negate=True)

    assert not not_enterprise.matches(user(country="BG"))


@pytest.mark.parametrize("operator", list(Operator))
def test_every_operator_needs_a_value(operator: Operator) -> None:
    with pytest.raises(InvalidFlagError, match="at least one value"):
        condition("plan", operator)


def test_needs_an_attribute_name() -> None:
    with pytest.raises(InvalidFlagError, match="attribute name"):
        condition("", Operator.IN, "pro")


class TestUserList:
    def test_matches_only_listed_users(self) -> None:
        testers = UserListCondition(frozenset({"user-1042", "user-7"}))

        assert testers.matches(EvaluationContext("user-1042"))
        assert not testers.matches(EvaluationContext("user-1043"))

    def test_ignores_attributes(self) -> None:
        testers = UserListCondition(frozenset({"user-7"}))

        assert not testers.matches(EvaluationContext("user-8", {"user_key": "user-7"}))

    @pytest.mark.parametrize("user_keys", [frozenset(), frozenset({"user-7", ""})])
    def test_rejects_empty_lists_and_empty_keys(self, user_keys: frozenset[str]) -> None:
        with pytest.raises(InvalidFlagError, match="user"):
            UserListCondition(user_keys)
