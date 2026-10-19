import math

import pytest

from flagstaff.engine.errors import InvalidFlagError
from flagstaff.engine.variants import FlagKind, JSONValue, Variant


@pytest.mark.parametrize(
    ("kind", "accepted", "refused"),
    [
        (FlagKind.BOOLEAN, [True, False], [1, "true", None]),
        (FlagKind.STRING, ["", "blue"], [1, True, None]),
        (FlagKind.NUMBER, [0, 25, 0.5, -3], [True, "25", math.nan, math.inf, None]),
        (
            FlagKind.JSON,
            [None, True, 3, "x", [1, "two"], {"limits": {"daily": 50, "tiers": ["pro"]}}],
            [{"ratio": math.nan}, {1: "numeric key"}, [object()], ("tuple",)],
        ),
    ],
)
def test_each_kind_accepts_only_its_own_values(
    kind: FlagKind, accepted: list[JSONValue], refused: list[object]
) -> None:
    assert all(kind.accepts(value) for value in accepted)
    assert not any(kind.accepts(value) for value in refused)  # type: ignore[arg-type]


@pytest.mark.parametrize("key", ["", "has space", "-leading-dash", "a:b", "x" * 129])
def test_rejects_malformed_variant_keys(key: str) -> None:
    with pytest.raises(InvalidFlagError, match="variant key"):
        Variant(key, value=True)


@pytest.mark.parametrize("key", ["on", "treatment-b", "v2.1", "control_2026", "x" * 128])
def test_accepts_well_formed_variant_keys(key: str) -> None:
    assert Variant(key, value=True).key == key
