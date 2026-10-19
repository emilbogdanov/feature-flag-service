# The JSON shape flags travel in: from the server's database to its API, and from the API into
# every SDK. Readers ignore fields they don't know, so an older SDK keeps working when a newer
# server starts sending more.
from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, cast

from flagstaff.engine.conditions import AttributeCondition, Operator, UserListCondition
from flagstaff.engine.errors import InvalidFlagError
from flagstaff.engine.flag import Flag, Rule
from flagstaff.engine.ruleset import Ruleset
from flagstaff.engine.serving import FixedVariant, Rollout, WeightedVariant
from flagstaff.engine.variants import FlagKind, Variant

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from flagstaff.engine.conditions import Condition
    from flagstaff.engine.context import AttributeValue
    from flagstaff.engine.serving import Serve
    from flagstaff.engine.variants import JSONValue

type Document = dict[str, JSONValue]

# Bumped only for a change an older reader would get wrong rather than ignore; new optional
# fields don't need it.
RULESET_FORMAT = 1


class WireFormatError(InvalidFlagError):
    pass


def ruleset_to_document(ruleset: Ruleset) -> Document:
    return {
        "format": RULESET_FORMAT,
        "version": ruleset.version,
        # Sorted, so one ruleset version always serialises to the same bytes.
        "flags": [flag_to_document(ruleset.flags[key]) for key in sorted(ruleset.flags)],
    }


def ruleset_from_document(document: object) -> Ruleset:
    fields = _Object(document, "ruleset")
    format_ = fields.integer("format")
    if format_ != RULESET_FORMAT:
        raise WireFormatError(
            f"ruleset.format is {format_}; this version of the engine reads format {RULESET_FORMAT}"
        )
    flags = [
        flag_from_document(item, path=item_path)
        for item, item_path in _items(fields.field("flags"), fields.path_of("flags"))
    ]
    with _reported_at("ruleset"):
        return Ruleset.of(fields.integer("version"), flags)


def flag_to_document(flag: Flag) -> Document:
    return {
        "key": flag.key,
        "kind": flag.kind.value,
        "enabled": flag.enabled,
        "variants": variants_to_document(flag.variants),
        "off_variant": flag.off_variant,
        "rules": rules_to_document(flag.rules),
        "fallthrough": serve_to_document(flag.fallthrough),
    }


def flag_from_document(document: object, *, path: str = "flag") -> Flag:
    fields = _Object(document, path)
    with _reported_at(path):
        return Flag(
            key=fields.text("key"),
            kind=_member(FlagKind, fields.text("kind"), fields.path_of("kind")),
            enabled=fields.boolean("enabled"),
            variants=variants_from_document(
                fields.field("variants"), path=fields.path_of("variants")
            ),
            off_variant=fields.text("off_variant"),
            rules=rules_from_document(fields.field("rules"), path=fields.path_of("rules")),
            fallthrough=serve_from_document(
                fields.field("fallthrough"), path=fields.path_of("fallthrough")
            ),
        )


def variants_to_document(variants: Iterable[Variant]) -> list[JSONValue]:
    return [{"key": variant.key, "value": variant.value} for variant in variants]


def variants_from_document(document: object, *, path: str = "variants") -> tuple[Variant, ...]:
    variants = []
    for item, item_path in _items(document, path):
        fields = _Object(item, item_path)
        value = fields.field("value")
        if not FlagKind.JSON.accepts(value):
            raise WireFormatError(f"{fields.path_of('value')} is not a JSON value")
        with _reported_at(item_path):
            variants.append(Variant(fields.text("key"), value=cast("JSONValue", value)))
    return tuple(variants)


def rules_to_document(rules: Iterable[Rule]) -> list[JSONValue]:
    return [
        {
            "id": rule.id,
            "conditions": [_condition_to_document(condition) for condition in rule.conditions],
            "serve": serve_to_document(rule.serve),
        }
        for rule in rules
    ]


def rules_from_document(document: object, *, path: str = "rules") -> tuple[Rule, ...]:
    rules = []
    for item, item_path in _items(document, path):
        fields = _Object(item, item_path)
        conditions = tuple(
            _condition_from_document(condition, condition_path)
            for condition, condition_path in _items(
                fields.field("conditions"), fields.path_of("conditions")
            )
        )
        serve = serve_from_document(fields.field("serve"), path=fields.path_of("serve"))
        with _reported_at(item_path):
            rules.append(Rule(id=fields.text("id"), conditions=conditions, serve=serve))
    return tuple(rules)


def serve_to_document(serve: Serve) -> Document:
    match serve:
        case FixedVariant():
            return {"variant": serve.variant_key}
        case Rollout():
            return {
                "rollout": [
                    {"variant": weighted.variant_key, "weight": weighted.weight}
                    for weighted in serve.weights
                ]
            }
    raise TypeError(f"{type(serve).__name__} has no wire format")


def serve_from_document(document: object, *, path: str = "serve") -> Serve:
    fields = _Object(document, path)
    if fields.has("variant") == fields.has("rollout"):
        raise WireFormatError(f"{path} must have exactly one of 'variant' and 'rollout'")
    if fields.has("variant"):
        return FixedVariant(fields.text("variant"))
    weights = []
    for item, item_path in _items(fields.field("rollout"), fields.path_of("rollout")):
        weighted = _Object(item, item_path)
        with _reported_at(item_path):
            weights.append(WeightedVariant(weighted.text("variant"), weighted.integer("weight")))
    with _reported_at(path):
        return Rollout(tuple(weights))


def _condition_to_document(condition: Condition) -> Document:
    match condition:
        case AttributeCondition():
            return {
                "type": "attribute",
                "attribute": condition.attribute,
                "operator": condition.operator.value,
                "values": list(condition.values),
                "negate": condition.negate,
            }
        case UserListCondition():
            # Sorted so the same list always produces the same document, and the same ETag.
            return {"type": "user_list", "user_keys": [*sorted(condition.user_keys)]}
    raise TypeError(f"{type(condition).__name__} has no wire format")


def _condition_from_document(document: object, path: str) -> Condition:
    fields = _Object(document, path)
    condition_type = fields.text("type")
    with _reported_at(path):
        if condition_type == "attribute":
            return AttributeCondition(
                attribute=fields.text("attribute"),
                operator=_member(Operator, fields.text("operator"), fields.path_of("operator")),
                values=tuple(
                    _attribute_value(value, value_path)
                    for value, value_path in _items(
                        fields.field("values"), fields.path_of("values")
                    )
                ),
                negate=fields.boolean("negate"),
            )
        if condition_type == "user_list":
            return UserListCondition(
                frozenset(
                    _text(key, key_path)
                    for key, key_path in _items(
                        fields.field("user_keys"), fields.path_of("user_keys")
                    )
                )
            )
    raise WireFormatError(
        f"{fields.path_of('type')} is {condition_type!r}; expected 'attribute' or 'user_list'"
    )


def _attribute_value(value: object, path: str) -> AttributeValue:
    if not isinstance(value, str | int | float):
        raise WireFormatError(f"{path} must be a string, number or boolean")
    return value


def _text(value: object, path: str) -> str:
    if not isinstance(value, str):
        raise WireFormatError(f"{path} must be a string")
    return value


def _member[E: (FlagKind, Operator)](enum: type[E], value: str, path: str) -> E:
    try:
        return enum(value)
    except ValueError:
        allowed = ", ".join(repr(member.value) for member in enum)
        raise WireFormatError(f"{path} is {value!r}; expected one of {allowed}") from None


def _items(value: object, path: str) -> Iterator[tuple[object, str]]:
    if not isinstance(value, list):
        raise WireFormatError(f"{path} must be an array")
    for index, item in enumerate(cast("list[object]", value)):
        yield item, f"{path}[{index}]"


# A flag the engine rejects is reported with the path of the part it rejected, so a 422 from
# the server or a log line from an SDK says where in the document to look.
@contextmanager
def _reported_at(path: str) -> Iterator[None]:
    try:
        yield
    except WireFormatError:
        raise
    except InvalidFlagError as error:
        raise WireFormatError(f"{path}: {error}") from error


class _Object:
    def __init__(self, value: object, path: str) -> None:
        if not isinstance(value, dict):
            raise WireFormatError(f"{path} must be an object")
        self._fields = cast("dict[str, object]", value)
        self._path = path

    def path_of(self, name: str) -> str:
        return f"{self._path}.{name}"

    def has(self, name: str) -> bool:
        return name in self._fields

    def field(self, name: str) -> object:
        if name not in self._fields:
            raise WireFormatError(f"{self.path_of(name)} is missing")
        return self._fields[name]

    def text(self, name: str) -> str:
        return _text(self.field(name), self.path_of(name))

    def boolean(self, name: str) -> bool:
        value = self.field(name)
        if not isinstance(value, bool):
            raise WireFormatError(f"{self.path_of(name)} must be true or false")
        return value

    def integer(self, name: str) -> int:
        value = self.field(name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise WireFormatError(f"{self.path_of(name)} must be an integer")
        return value
