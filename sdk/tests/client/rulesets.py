# Rulesets for client tests, built the way the server builds them.
from flagstaff.engine.conditions import UserListCondition
from flagstaff.engine.flag import Flag, Rule
from flagstaff.engine.ruleset import Ruleset
from flagstaff.engine.serving import FixedVariant
from flagstaff.engine.variants import FlagKind, JSONValue, Variant


def flag(
    key: str,
    kind: FlagKind,
    values: tuple[JSONValue, JSONValue],
    *,
    enabled: bool = True,
    testers: frozenset[str] = frozenset(),
) -> Flag:
    on, off = values
    rules = (
        (Rule(id="testers", conditions=(UserListCondition(testers),), serve=FixedVariant("on")),)
        if testers
        else ()
    )
    return Flag(
        key=key,
        kind=kind,
        variants=(Variant("on", value=on), Variant("off", value=off)),
        enabled=enabled,
        off_variant="off",
        fallthrough=FixedVariant("off" if testers else "on"),
        rules=rules,
    )


def storefront(version: int = 1, *, checkout_enabled: bool = True) -> Ruleset:
    return Ruleset.of(
        version,
        [
            flag(
                "new-checkout",
                FlagKind.BOOLEAN,
                (True, False),
                enabled=checkout_enabled,
                testers=frozenset({"user-7"}),
            ),
            flag("checkout-theme", FlagKind.STRING, ("spruce", "classic")),
            flag("search-results-per-page", FlagKind.NUMBER, (48, 24)),
            flag(
                "upload-limits",
                FlagKind.JSON,
                ({"per_day": 500, "formats": ["png", "webp"]}, {"per_day": 50, "formats": ["png"]}),
            ),
        ],
    )
