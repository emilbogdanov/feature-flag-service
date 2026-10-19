from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final
from uuid import uuid4

from flagstaff.engine.wire import variants_to_document

from flagstaff_server.application.audit import audit_entry
from flagstaff_server.application.errors import StaleFlagError
from flagstaff_server.application.lookups import (
    require_environment,
    require_flag,
    require_project,
)
from flagstaff_server.application.rulesets import RulesetChange
from flagstaff_server.domain.audit import AuditAction
from flagstaff_server.domain.errors import FlagKeyTakenError, InvalidTargetingError
from flagstaff_server.domain.flags import Flag
from flagstaff_server.domain.ids import FlagId

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable, Mapping

    from flagstaff.engine.variants import FlagKind, JSONValue, Variant

    from flagstaff_server.application.ports import Clock, RulesetChangePublisher, UnitOfWork
    from flagstaff_server.domain.audit import Actor, AuditEntry
    from flagstaff_server.domain.flags import Targeting
    from flagstaff_server.domain.ids import EnvironmentId
    from flagstaff_server.domain.projects import Environment, Project
    from flagstaff_server.domain.values import Description, Name, Slug


# Enough to ride out a burst of concurrent saves to one flag without spinning on a hot one.
UNVERSIONED_EDIT_ATTEMPTS: Final = 3


# Edits take the version the caller last read. None skips the check, which is what a kill
# switch wants: turning a flag off must work even if someone edited it a second ago.
class FlagService:
    def __init__(self, uow: UnitOfWork, clock: Clock, changes: RulesetChangePublisher) -> None:
        self._uow = uow
        self._clock = clock
        self._changes = changes

    async def create_flag(
        self,
        actor: Actor,
        project_key: Slug,
        *,
        key: str,
        name: Name,
        description: Description,
        kind: FlagKind,
        variants: tuple[Variant, ...],
        off_variant: str,
        on_variant: str,
    ) -> Flag:
        now = self._clock.now()
        async with self._uow as uow:
            project = await require_project(uow, project_key)
            if await uow.flags.get(project.id, key) is not None:
                raise FlagKeyTakenError(project_key, key)
            flag = Flag.create(
                flag_id=FlagId(uuid4()),
                project_id=project.id,
                key=key,
                name=name,
                description=description,
                kind=kind,
                variants=variants,
                off_variant=off_variant,
                on_variant=on_variant,
                at=now,
            )
            await uow.flags.add(flag)
            # A new flag shows up, switched off, in every environment's ruleset.
            versions = await uow.environments.bump_ruleset_versions(
                await self._environment_ids(uow, project)
            )
            await uow.audit.add(
                audit_entry(
                    AuditAction.FLAG_CREATED,
                    actor=actor,
                    at=now,
                    subject=key,
                    project_id=project.id,
                    changes={
                        "name": str(name),
                        "description": str(description),
                        "kind": kind.value,
                        "variants": variants_to_document(variants),
                        "off_variant": off_variant,
                        "on_variant": on_variant,
                    },
                )
            )
            await uow.commit()
        await self._announce(versions)
        return flag

    async def get_flag(self, project_key: Slug, key: str) -> Flag:
        async with self._uow as uow:
            project = await require_project(uow, project_key)
            return await require_flag(uow, project, key)

    async def list_flags(self, project_key: Slug) -> list[Flag]:
        async with self._uow as uow:
            project = await require_project(uow, project_key)
            return await uow.flags.list_active(project.id)

    async def change_details(
        self,
        actor: Actor,
        project_key: Slug,
        key: str,
        *,
        name: Name,
        description: Description,
        expected_version: int | None = None,
    ) -> Flag:
        async def change(edit: _Edit) -> None:
            flag = edit.flag
            changes = {
                field_name: _before_and_after(str(before), str(after))
                for field_name, before, after in [
                    ("name", flag.name, name),
                    ("description", flag.description, description),
                ]
                if before != after
            }
            flag.change_details(name=name, description=description, at=self._clock.now())
            if changes:
                # Names and descriptions never reach an SDK, so no ruleset moves on.
                entry = self._entry(edit, AuditAction.FLAG_DETAILS_CHANGED, actor, changes)
                edit.record(entry, affects=())

        return await self._edit(project_key, key, expected_version, change)

    async def change_variants(
        self,
        actor: Actor,
        project_key: Slug,
        key: str,
        *,
        variants: tuple[Variant, ...],
        expected_version: int | None = None,
    ) -> Flag:
        async def change(edit: _Edit) -> None:
            before = variants_to_document(edit.flag.variants)
            try:
                edit.flag.change_variants(variants, at=self._clock.now())
            except InvalidTargetingError as error:
                if error.environment_id is None:
                    raise
                # The caller named no environment, so say which one the variants would break.
                broken = await edit.uow.environments.get(error.environment_id)
                where = broken.key if broken else error.environment_id
                raise InvalidTargetingError(f"{where}: {error.reason}") from error
            changes = {"variants": _before_and_after(before, variants_to_document(variants))}
            edit.record(
                self._entry(edit, AuditAction.FLAG_VARIANTS_CHANGED, actor, changes),
                affects=await self._environment_ids(edit.uow, edit.project),
            )

        return await self._edit(project_key, key, expected_version, change)

    async def change_targeting(
        self,
        actor: Actor,
        project_key: Slug,
        key: str,
        environment_key: Slug,
        *,
        targeting: Targeting,
        expected_version: int | None = None,
    ) -> Flag:
        async def change(edit: _Edit) -> None:
            environment = await require_environment(edit.uow, edit.project, environment_key)
            before = edit.flag.targeting_in(environment.id).to_document()
            edit.flag.change_targeting(environment.id, targeting, at=self._clock.now())
            changes = {"targeting": _before_and_after(before, targeting.to_document())}
            entry = self._entry(
                edit, AuditAction.FLAG_TARGETING_CHANGED, actor, changes, environment=environment
            )
            edit.record(entry, affects=[environment.id])

        return await self._edit(project_key, key, expected_version, change)

    async def enable(
        self,
        actor: Actor,
        project_key: Slug,
        key: str,
        environment_key: Slug,
        *,
        expected_version: int | None = None,
    ) -> Flag:
        return await self._switch(
            actor, project_key, key, environment_key, on=True, expected_version=expected_version
        )

    async def disable(
        self,
        actor: Actor,
        project_key: Slug,
        key: str,
        environment_key: Slug,
        *,
        expected_version: int | None = None,
    ) -> Flag:
        return await self._switch(
            actor, project_key, key, environment_key, on=False, expected_version=expected_version
        )

    async def archive(
        self, actor: Actor, project_key: Slug, key: str, *, expected_version: int | None = None
    ) -> Flag:
        async def change(edit: _Edit) -> None:
            edit.flag.archive(at=self._clock.now())
            edit.record(
                self._entry(edit, AuditAction.FLAG_ARCHIVED, actor, {}),
                affects=await self._environment_ids(edit.uow, edit.project),
            )

        return await self._edit(project_key, key, expected_version, change)

    async def _switch(
        self,
        actor: Actor,
        project_key: Slug,
        key: str,
        environment_key: Slug,
        *,
        on: bool,
        expected_version: int | None,
    ) -> Flag:
        async def change(edit: _Edit) -> None:
            environment = await require_environment(edit.uow, edit.project, environment_key)
            now = self._clock.now()
            switched = (
                edit.flag.enable(environment.id, at=now)
                if on
                else edit.flag.disable(environment.id, at=now)
            )
            if switched:
                action = AuditAction.FLAG_ENABLED if on else AuditAction.FLAG_DISABLED
                entry = self._entry(edit, action, actor, {}, environment=environment)
                edit.record(entry, affects=[environment.id])

        return await self._edit(project_key, key, expected_version, change)

    # An edit with no expected version, such as a kill switch, that loses a race to another
    # save is run again on the flag as that save left it. With an expected version the caller
    # decided against whatever they last saw, so the conflict is theirs to resolve.
    async def _edit(
        self, project_key: Slug, key: str, expected_version: int | None, change: _Change
    ) -> Flag:
        attempt = 1
        while True:
            try:
                return await self._edit_once(project_key, key, expected_version, change)
            except StaleFlagError:
                if expected_version is not None or attempt == UNVERSIONED_EDIT_ATTEMPTS:
                    raise
                attempt += 1

    # Loads the flag, applies the change, then saves it, moves the affected rulesets on and
    # writes the audit entries in one transaction, but only if the change recorded anything.
    async def _edit_once(
        self, project_key: Slug, key: str, expected_version: int | None, change: _Change
    ) -> Flag:
        async with self._uow as uow:
            project = await require_project(uow, project_key)
            flag = await require_flag(uow, project, key)
            if expected_version is not None and flag.version != expected_version:
                raise StaleFlagError(key, expected=expected_version, actual=flag.version)
            edit = _Edit(uow, project, flag)
            await change(edit)
            if not edit.entries:
                return flag
            await uow.flags.update(flag)
            versions = await uow.environments.bump_ruleset_versions(edit.affected)
            for entry in edit.entries:
                await uow.audit.add(entry)
            await uow.commit()
        await self._announce(versions)
        return flag

    # Only after the commit: an instance that hears of a version must find it in the database.
    async def _announce(self, versions: Mapping[EnvironmentId, int]) -> None:
        await self._changes.announce(
            [RulesetChange(environment_id, version) for environment_id, version in versions.items()]
        )

    def _entry(
        self,
        edit: _Edit,
        action: AuditAction,
        actor: Actor,
        changes: Mapping[str, JSONValue],
        *,
        environment: Environment | None = None,
    ) -> AuditEntry:
        return audit_entry(
            action,
            actor=actor,
            at=edit.flag.updated_at,
            subject=edit.flag.key,
            project_id=edit.project.id,
            environment_id=environment.id if environment else None,
            changes=changes,
        )

    async def _environment_ids(self, uow: UnitOfWork, project: Project) -> list[EnvironmentId]:
        return [
            environment.id for environment in await uow.environments.list_for_project(project.id)
        ]


@dataclass
class _Edit:
    uow: UnitOfWork
    project: Project
    flag: Flag
    entries: list[AuditEntry] = field(default_factory=list)
    affected: set[EnvironmentId] = field(default_factory=set)

    def record(self, entry: AuditEntry, *, affects: Iterable[EnvironmentId]) -> None:
        self.entries.append(entry)
        self.affected.update(affects)


type _Change = Callable[[_Edit], Awaitable[None]]


def _before_and_after(before: JSONValue, after: JSONValue) -> JSONValue:
    return {"before": before, "after": after}
