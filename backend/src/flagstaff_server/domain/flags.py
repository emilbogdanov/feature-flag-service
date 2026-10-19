from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from flagstaff.engine.errors import InvalidFlagError
from flagstaff.engine.flag import Flag as CompiledFlag
from flagstaff.engine.keys import require_key
from flagstaff.engine.serving import FixedVariant
from flagstaff.engine.wire import (
    WireFormatError,
    rules_from_document,
    rules_to_document,
    serve_from_document,
    serve_to_document,
)

from flagstaff_server.domain.errors import (
    ArchivedFlagError,
    InvalidTargetingError,
    InvalidValueError,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from datetime import datetime

    from flagstaff.engine.flag import Rule
    from flagstaff.engine.serving import Serve
    from flagstaff.engine.variants import FlagKind, JSONValue, Variant

    from flagstaff_server.domain.ids import EnvironmentId, FlagId, ProjectId
    from flagstaff_server.domain.values import Description, Name


# How one environment evaluates a flag. The variants it names belong to the flag, so whether a
# Targeting makes sense is only known once it is compiled against the flag it sits on.
@dataclass(frozen=True, slots=True, kw_only=True)
class Targeting:
    enabled: bool
    off_variant: str
    fallthrough: Serve
    rules: tuple[Rule, ...] = ()

    # Stored and audited in the engine's own wire format, so a rule reads the same in the
    # database, in the audit log and in what SDKs download.
    def to_document(self) -> dict[str, JSONValue]:
        return {
            "enabled": self.enabled,
            "off_variant": self.off_variant,
            "rules": rules_to_document(self.rules),
            "fallthrough": serve_to_document(self.fallthrough),
        }

    @classmethod
    def from_document(cls, document: Mapping[str, JSONValue]) -> Targeting:
        enabled, off_variant = document.get("enabled"), document.get("off_variant")
        if not isinstance(enabled, bool) or not isinstance(off_variant, str):
            raise WireFormatError("targeting needs a boolean 'enabled' and a string 'off_variant'")
        return cls(
            enabled=enabled,
            off_variant=off_variant,
            rules=rules_from_document(document.get("rules")),
            fallthrough=serve_from_document(document.get("fallthrough"), path="fallthrough"),
        )


class Flag:
    # The constructor rebuilds a flag as stored; new flags go through create() so they are
    # checked before anything holds them.
    def __init__(
        self,
        *,
        flag_id: FlagId,
        project_id: ProjectId,
        key: str,
        name: Name,
        description: Description,
        kind: FlagKind,
        variants: tuple[Variant, ...],
        initial_targeting: Targeting,
        targeting: Mapping[EnvironmentId, Targeting],
        created_at: datetime,
        updated_at: datetime,
        archived_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        self._id = flag_id
        self._project_id = project_id
        self._key = key
        self._name = name
        self._description = description
        self._kind = kind
        self._variants = variants
        self._initial_targeting = initial_targeting
        self._targeting = dict(targeting)
        self._created_at = created_at
        self._updated_at = updated_at
        self._archived_at = archived_at
        self._version = version

    # off_variant and on_variant set how every environment starts out, including ones added to
    # the project later: off, and serving on_variant to everyone once switched on.
    @classmethod
    def create(
        cls,
        *,
        flag_id: FlagId,
        project_id: ProjectId,
        key: str,
        name: Name,
        description: Description,
        kind: FlagKind,
        variants: tuple[Variant, ...],
        off_variant: str,
        on_variant: str,
        at: datetime,
    ) -> Flag:
        try:
            require_key("flag", key)
        except InvalidFlagError as error:
            raise InvalidValueError(str(error)) from error
        initial = Targeting(
            enabled=False, off_variant=off_variant, fallthrough=FixedVariant(on_variant)
        )
        flag = cls(
            flag_id=flag_id,
            project_id=project_id,
            key=key,
            name=name,
            description=description,
            kind=kind,
            variants=variants,
            initial_targeting=initial,
            targeting={},
            created_at=at,
            updated_at=at,
        )
        flag._compile_or_reject(variants, initial)
        return flag

    @property
    def id(self) -> FlagId:
        return self._id

    @property
    def project_id(self) -> ProjectId:
        return self._project_id

    @property
    def key(self) -> str:
        return self._key

    @property
    def name(self) -> Name:
        return self._name

    @property
    def description(self) -> Description:
        return self._description

    @property
    def kind(self) -> FlagKind:
        return self._kind

    @property
    def variants(self) -> tuple[Variant, ...]:
        return self._variants

    @property
    def initial_targeting(self) -> Targeting:
        return self._initial_targeting

    # Only environments whose targeting was ever changed; the rest use initial_targeting.
    @property
    def targeting(self) -> Mapping[EnvironmentId, Targeting]:
        return dict(self._targeting)

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    @property
    def archived_at(self) -> datetime | None:
        return self._archived_at

    @property
    def is_archived(self) -> bool:
        return self._archived_at is not None

    # The version this flag was read at. Saving checks it, so two people editing the same flag
    # can't silently overwrite each other.
    @property
    def version(self) -> int:
        return self._version

    def targeting_in(self, environment_id: EnvironmentId) -> Targeting:
        return self._targeting.get(environment_id, self._initial_targeting)

    def compile_for(self, environment_id: EnvironmentId) -> CompiledFlag:
        return self._compile(self._variants, self.targeting_in(environment_id))

    def change_details(self, *, name: Name, description: Description, at: datetime) -> None:
        self._require_not_archived()
        self._name = name
        self._description = description
        self._updated_at = at

    # Every environment's targeting must still compile against the new variants, so removing a
    # variant that some rule still serves is refused rather than breaking that environment.
    def change_variants(self, variants: tuple[Variant, ...], *, at: datetime) -> None:
        self._require_not_archived()
        self._compile_or_reject(variants, self._initial_targeting)
        for environment_id, targeting in self._targeting.items():
            self._compile_or_reject(variants, targeting, environment_id=environment_id)
        self._variants = variants
        self._updated_at = at

    def change_targeting(
        self, environment_id: EnvironmentId, targeting: Targeting, *, at: datetime
    ) -> None:
        self._require_not_archived()
        self._compile_or_reject(self._variants, targeting, environment_id=environment_id)
        self._targeting[environment_id] = targeting
        self._updated_at = at

    # Returns whether anything changed, so flipping a switch that is already in place leaves no
    # audit entry and doesn't make every SDK fetch the same rules again.
    def enable(self, environment_id: EnvironmentId, *, at: datetime) -> bool:
        return self._switch(environment_id, on=True, at=at)

    def disable(self, environment_id: EnvironmentId, *, at: datetime) -> bool:
        return self._switch(environment_id, on=False, at=at)

    # Archived flags drop out of every ruleset, so SDKs fall back to the default in the code
    # that asks for them. The key stays taken: reusing it would revive old call sites.
    def archive(self, *, at: datetime) -> None:
        self._require_not_archived()
        self._archived_at = at
        self._updated_at = at

    def mark_saved(self) -> None:
        self._version += 1

    def _switch(self, environment_id: EnvironmentId, *, on: bool, at: datetime) -> bool:
        self._require_not_archived()
        current = self.targeting_in(environment_id)
        if current.enabled is on:
            return False
        self._targeting[environment_id] = replace(current, enabled=on)
        self._updated_at = at
        return True

    def _require_not_archived(self) -> None:
        if self.is_archived:
            raise ArchivedFlagError(self._key)

    # Without an environment id the targeting is the one new environments start with.
    def _compile_or_reject(
        self,
        variants: Iterable[Variant],
        targeting: Targeting,
        *,
        environment_id: EnvironmentId | None = None,
    ) -> CompiledFlag:
        try:
            return self._compile(variants, targeting)
        except InvalidFlagError as error:
            if environment_id is None:
                raise InvalidTargetingError(f"new environments: {error}") from error
            raise InvalidTargetingError(str(error), environment_id=environment_id) from error

    def _compile(self, variants: Iterable[Variant], targeting: Targeting) -> CompiledFlag:
        return CompiledFlag(
            key=self._key,
            kind=self._kind,
            variants=tuple(variants),
            enabled=targeting.enabled,
            off_variant=targeting.off_variant,
            fallthrough=targeting.fallthrough,
            rules=targeting.rules,
        )
