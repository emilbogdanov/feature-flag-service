import json
from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from flagstaff.engine.context import EvaluationContext
from flagstaff.engine.errors import InvalidFlagError
from flagstaff.engine.flag import Flag
from flagstaff.engine.ruleset import Ruleset
from flagstaff.engine.serving import FixedVariant
from flagstaff.engine.variants import FlagKind, Variant
from flagstaff.engine.wire import (
    WireFormatError,
    flag_to_document,
    ruleset_from_document,
    ruleset_to_document,
)
from tests.engine.strategies import flags


def boolean_flag(key: str, *, enabled: bool = True) -> Flag:
    return Flag(
        key=key,
        kind=FlagKind.BOOLEAN,
        variants=(Variant("on", value=True), Variant("off", value=False)),
        enabled=enabled,
        off_variant="off",
        fallthrough=FixedVariant("on"),
    )


def test_evaluates_the_flags_it_holds() -> None:
    ruleset = Ruleset.of(
        7, [boolean_flag("new-checkout"), boolean_flag("dark-mode", enabled=False)]
    )
    user = EvaluationContext("user-1042")

    checkout, dark_mode = (
        ruleset.evaluate("new-checkout", user),
        ruleset.evaluate("dark-mode", user),
    )

    assert checkout is not None
    assert checkout.value is True
    assert dark_mode is not None
    assert dark_mode.value is False


def test_knows_nothing_about_flags_it_does_not_hold() -> None:
    assert (
        Ruleset.of(7, [boolean_flag("new-checkout")]).evaluate("search-v2", EvaluationContext("u"))
        is None
    )


def test_holds_each_flag_once() -> None:
    with pytest.raises(InvalidFlagError, match=r"more than once: \['new-checkout'\]"):
        Ruleset.of(7, [boolean_flag("new-checkout"), boolean_flag("new-checkout")])


def test_versions_count_up_from_zero() -> None:
    with pytest.raises(InvalidFlagError, match="negative"):
        Ruleset.of(-1, [])


@given(
    version=st.integers(min_value=0, max_value=2**53),
    flag_list=st.lists(flags(), max_size=5, unique_by=lambda flag: flag.key),
)
def test_any_ruleset_survives_a_trip_through_json(version: int, flag_list: list[Flag]) -> None:
    ruleset = Ruleset.of(version, flag_list)

    document = json.loads(json.dumps(ruleset_to_document(ruleset)))

    assert ruleset_from_document(document) == ruleset


def test_the_same_ruleset_always_writes_the_same_document() -> None:
    flags_in_one_order = [boolean_flag("search-v2"), boolean_flag("dark-mode")]

    first = ruleset_to_document(Ruleset.of(3, flags_in_one_order))
    second = ruleset_to_document(Ruleset.of(3, reversed(flags_in_one_order)))

    assert json.dumps(first) == json.dumps(second)


def test_refuses_a_format_it_does_not_read() -> None:
    document = ruleset_to_document(Ruleset.of(3, [boolean_flag("dark-mode")]))

    with pytest.raises(WireFormatError, match=r"ruleset\.format is 2"):
        ruleset_from_document({**document, "format": 2})


def test_says_which_flag_of_the_ruleset_is_malformed() -> None:
    broken = {**flag_to_document(boolean_flag("search-v2")), "kind": "date"}
    document = {"format": 1, "version": 3, "flags": [flag_to_document(boolean_flag("a")), broken]}

    with pytest.raises(WireFormatError, match=r"ruleset.flags\[1\].kind is 'date'"):
        ruleset_from_document(document)


def test_two_flags_with_one_key_are_reported_against_the_ruleset() -> None:
    flag = flag_to_document(boolean_flag("dark-mode"))

    with pytest.raises(WireFormatError, match="ruleset: ruleset has flags more than once"):
        ruleset_from_document({"format": 1, "version": 3, "flags": [flag, flag]})


def test_a_ruleset_is_equal_to_one_with_the_same_flags() -> None:
    ruleset = Ruleset.of(3, [boolean_flag("dark-mode")])

    assert ruleset == Ruleset.of(3, [boolean_flag("dark-mode")])
    assert ruleset != replace(ruleset, version=4)
