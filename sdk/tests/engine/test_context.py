import pytest

from flagstaff.engine.context import EvaluationContext
from flagstaff.engine.errors import InvalidContextError


def test_keeps_its_own_copy_of_the_attributes() -> None:
    attributes: dict[str, str | int | float | bool] = {"country": "BG"}
    context = EvaluationContext("user-1", attributes)

    attributes["country"] = "DE"

    assert context.attribute("country") == "BG"


def test_attributes_cannot_be_changed_through_the_context() -> None:
    context = EvaluationContext("user-1", {"country": "BG"})

    with pytest.raises(TypeError):
        context.attributes["country"] = "DE"  # type: ignore[index]


def test_a_missing_attribute_reads_as_none() -> None:
    assert EvaluationContext("user-1").attribute("plan") is None


def test_requires_a_user_key() -> None:
    with pytest.raises(InvalidContextError, match="user_key"):
        EvaluationContext("")


@pytest.mark.parametrize("value", [None, ["pro"], {"name": "pro"}])
def test_rejects_attribute_values_rules_cannot_compare(value: object) -> None:
    with pytest.raises(InvalidContextError, match="'plan'"):
        EvaluationContext("user-1", {"plan": value})  # type: ignore[dict-item]
