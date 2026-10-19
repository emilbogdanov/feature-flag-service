from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import uuid4

from flagstaff.engine.wire import variants_to_document

from flagstaff_server.application.audit import audit_entry
from flagstaff_server.application.errors import StaleFlagError
from flagstaff_server.application.lookups import (
    require_environment,
    require_flag,
    require_project,
)
from flagstaff_server.domain.audit import AuditAction
from flagstaff_server.domain.errors import FlagKeyTakenError
from flagstaff_server.domain.flags import Flag
from flagstaff_server.domain.ids import FlagId

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable, Mapping

    from flagstaff.engine.variants import FlagKind, JSONValue, Variant

    from flagstaff_server.application.ports import Clock, UnitOfWork
    from flagstaff_server.domain.audit import Actor, AuditEntry
    from flagstaff_server.domain.flags import Targeting
    from flagstaff_server.domain.ids import EnvironmentId
    from flagstaff_server.domain.projects import Environment, Project
    from flagstaff_server.domain.values import Description, Name, Slug


# Edits take the version the caller last read. None skips the check, which is what a kill
# switch wants: turning a flag off must work even if someone edited it a second ago.
class FlagService:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

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
            await uow.environments.bump_ruleset_versions(await self._environment_ids(uow, project))
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
        async with self._editing(project_key, key, expected_version) as edit:
            flag, now = edit.flag, self._clock.now()
            changes = {
                field_name: _before_and_after(str(before), str(after))
                for field_name, before, after in [
                    ("name", flag.name, name),
                    ("description", flag.description, description),
                ]
                if before != after
            }
            flag.change_details(name=name, description=description, at=now)
            if changes:
                # Names and descriptions never reach an SDK, so no ruleset moves on.
                entry = self._entry(edit, AuditAction.FLAG_DETAILS_CHANGED, actor, changes)
                edit.record(entry, affects=())
        return edit.flag

    async def change_variants(
        self,
        actor: Actor,
        project_key: Slug,
        key: str,
        *,
        variants: tuple[Variant, ...],
        expected_version: int | None = None,
    ) -> Flag:
        async with self._editing(project_key, key, expected_version) as edit:
            before = variants_to_document(edit.flag.variants)
            edit.flag.change_variants(variants, at=self._clock.now())
            changes = {"variants": _before_and_after(before, variants_to_document(variants))}
            edit.record(
                self._entry(edit, AuditAction.FLAG_VARIANTS_CHANGED, actor, changes),
                affects=await self._environment_ids(edit.uow, edit.project),
            )
        return edit.flag

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
        async with self._editing(project_key, key, expected_version) as edit:
            environment = await require_environment(edit.uow, edit.project, environment_key)
            before = edit.flag.targeting_in(environment.id).to_document()
            edit.flag.change_targeting(environment.id, targeting, at=self._clock.now())
            changes = {"targeting": _before_and_after(before, targeting.to_document())}
            entry = self._entry(
                edit, AuditAction.FLAG_TARGETING_CHANGED, actor, changes, environment=environment
            )
            edit.record(entry, affects=[environment.id])
        return edit.flag

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
        async with self._editing(project_key, key, expected_version) as edit:
            edit.flag.archive(at=self._clock.now())
            edit.record(
                self._entry(edit, AuditAction.FLAG_ARCHIVED, actor, {}),
                affects=await self._environment_ids(edit.uow, edit.project),
            )
        return edit.flag

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
        async with self._editing(project_key, key, expected_version) as edit:
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
        return edit.flag

    # Loads the flag for an edit, then saves it, moves the affected rulesets on and writes the
    # audit entries in one transaction, but only if the edit recorded a change.
    @asynccontextmanager
    async def _editing(
        self, project_key: Slug, key: str, expected_version: int | None
    ) -> AsyncIterator[_Edit]:
        async with self._uow as uow:
            project = await require_project(uow, project_key)
            flag = await require_flag(uow, project, key)
            if expected_version is not None and flag.version != expected_version:
                raise StaleFlagError(key, expected=expected_version, actual=flag.version)
            edit = _Edit(uow, project, flag)
            yield edit
            if not edit.entries:
                return
            await uow.flags.update(flag)
            if edit.affected:
                await uow.environments.bump_ruleset_versions(edit.affected)
            for entry in edit.entries:
                await uow.audit.add(entry)
            await uow.commit()

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


def _before_and_after(before: JSONValue, after: JSONValue) -> JSONValue:
    return {"before": before, "after": after}
