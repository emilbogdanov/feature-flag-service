import copy
import json
from collections.abc import Callable
from typing import Any

import pytest
from hypothesis import given

from flagstaff.engine.conditions import AttributeCondition, Operator, UserListCondition
from flagstaff.engine.context import EvaluationContext
from flagstaff.engine.flag import Flag, Rule
from flagstaff.engine.serving import FixedVariant, Rollout, WeightedVariant
from flagstaff.engine.variants import FlagKind, Variant
from flagstaff.engine.wire import WireFormatError, flag_from_document, flag_to_document
from tests.engine.strategies import flags

NEW_CHECKOUT: dict[str, Any] = {
    "key": "new-checkout",
    "kind": "boolean",
    "enabled": True,
    "variants": [{"key": "on", "value": True}, {"key": "off", "value": False}],
    "off_variant": "off",
    "rules": [
        {
            "id": "beta-testers",
            "conditions": [{"type": "user_list", "user_keys": ["user-1042", "user-7"]}],
            "serve": {"variant": "on"},
        },
        {
            "id": "eu-pro",
            "conditions": [
                {
                    "type": "attribute",
                    "attribute": "country",
                    "operator": "in",
                    "values": ["BG", "DE"],
                    "negate": False,
                },
                {
                    "type": "attribute",
                    "attribute": "seats",
                    "operator": "gte",
                    "values": [5],
                    "negate": False,
                },
            ],
            "serve": {
                "rollout": [
                    {"variant": "on", "weight": 25_000},
                    {"variant": "off", "weight": 75_000},
                ]
            },
        },
    ],
    "fallthrough": {"variant": "off"},
}


def test_reads_a_flag_document() -> None:
    flag = flag_from_document(NEW_CHECKOUT)

    assert flag == Flag(
        key="new-checkout",
        kind=FlagKind.BOOLEAN,
        enabled=True,
        variants=(Variant("on", value=True), Variant("off", value=False)),
        off_variant="off",
        rules=(
            Rule(
                id="beta-testers",
                conditions=(UserListCondition(frozenset({"user-7", "user-1042"})),),
                serve=FixedVariant("on"),
            ),
            Rule(
                id="eu-pro",
                conditions=(
                    AttributeCondition(
                        attribute="country", operator=Operator.IN, values=("BG", "DE")
                    ),
                    AttributeCondition(
                        attribute="seats", operator=Operator.GREATER_THAN_OR_EQUAL, values=(5,)
                    ),
                ),
                serve=Rollout((WeightedVariant("on", 25_000), WeightedVariant("off", 75_000))),
            ),
        ),
        fallthrough=FixedVariant("off"),
    )
    assert flag.evaluate(EvaluationContext("user-7")).rule_id == "beta-testers"


# The user list in the document is already sorted; a writer that didn't sort would hand it
# back in set order, which changes from one process to the next.
def test_writes_the_same_document_it_reads() -> None:
    assert flag_to_document(flag_from_document(NEW_CHECKOUT)) == NEW_CHECKOUT


@given(flag=flags())
def test_any_flag_survives_a_trip_through_json(flag: Flag) -> None:
    document = json.loads(json.dumps(flag_to_document(flag)))

    assert flag_from_document(document) == flag


def test_ignores_fields_it_does_not_know() -> None:
    document = copy.deepcopy(NEW_CHECKOUT)
    document["description"] = "Two-step checkout with saved cards"
    document["rules"][0]["created_by"] = "mira"

    assert flag_from_document(document) == flag_from_document(NEW_CHECKOUT)


def changed(change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    document = copy.deepcopy(NEW_CHECKOUT)
    change(document)
    return document


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ([], "flag must be an object"),
        (changed(lambda d: d.pop("off_variant")), "flag.off_variant is missing"),
        (changed(lambda d: d.update(kind="date")), "flag.kind is 'date'; expected one of"),
        (changed(lambda d: d.update(enabled="yes")), "flag.enabled must be true or false"),
        (changed(lambda d: d.update(rules={})), "flag.rules must be an array"),
        (
            changed(lambda d: d["rules"][1]["conditions"][0].update(operator="between")),
            r"flag.rules\[1\].conditions\[0\].operator is 'between'",
        ),
        (
            changed(lambda d: d["rules"][1]["conditions"][0].update(values=[["BG"]])),
            r"flag.rules\[1\].conditions\[0\].values\[0\] must be a string, number or boolean",
        ),
        (
            changed(lambda d: d["rules"][0]["conditions"][0].update(type="segment")),
            r"flag.rules\[0\].conditions\[0\].type is 'segment'",
        ),
        (
            changed(lambda d: d["rules"][0]["serve"].update(rollout=[])),
            r"flag.rules\[0\].serve must have exactly one of",
        ),
        (
            changed(lambda d: d["rules"][1]["serve"]["rollout"][0].update(weight=True)),
            r"flag.rules\[1\].serve.rollout\[0\].weight must be an integer",
        ),
        (
            changed(lambda d: d["rules"][1]["serve"]["rollout"][0].update(weight=20_000)),
            r"flag.rules\[1\].serve: rollout weights add up to 95000",
        ),
        (
            changed(lambda d: d["rules"][1]["conditions"][1].update(values=[5, 10])),
            r"flag.rules\[1\].conditions\[1\]: operator gte takes exactly one finite number",
        ),
        (
            changed(lambda d: d["variants"][0].update(value=float("nan"))),
            r"flag.variants\[0\].value is not a JSON value",
        ),
        (
            changed(lambda d: d.update(fallthrough={"variant": "holdout"})),
            r"flag: the fallthrough of flag 'new-checkout' serves variants it doesn't define",
        ),
    ],
)
def test_says_where_a_malformed_document_goes_wrong(document: object, message: str) -> None:
    with pytest.raises(WireFormatError, match=message):
        flag_from_document(document)
