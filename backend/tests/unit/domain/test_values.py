import pytest

from flagstaff_server.domain.errors import InvalidValueError
from flagstaff_server.domain.values import Description, Name, Slug


@pytest.mark.parametrize("key", ["storefront", "prod", "eu-west-2", "a", "x" * 50])
def test_accepts_url_safe_keys(key: str) -> None:
    assert str(Slug(key)) == key


@pytest.mark.parametrize(
    "key", ["", "Storefront", "eu_west", "-prod", "prod-", "mobile app", "x" * 51, "prod\n"]
)
def test_rejects_keys_that_would_need_escaping_or_case_rules(key: str) -> None:
    with pytest.raises(InvalidValueError, match="lowercase letters, digits or hyphens"):
        Slug(key)


def test_accepts_a_plain_name() -> None:
    assert str(Name("Storefront (EU)")) == "Storefront (EU)"


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("", "blank"),
        ("   ", "blank"),
        ("x" * 101, "at most 100"),
        ("Checkout\nv2", "single line"),
    ],
)
def test_rejects_names_that_dont_fit_on_one_line_of_a_list(name: str, message: str) -> None:
    with pytest.raises(InvalidValueError, match=message):
        Name(name)


def test_a_description_may_be_empty_but_not_endless() -> None:
    assert str(Description()) == ""

    with pytest.raises(InvalidValueError, match="at most 1000"):
        Description("x" * 1_001)
