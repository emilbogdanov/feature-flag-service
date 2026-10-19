from __future__ import annotations

import secrets
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING, Final
from uuid import uuid4

from flagstaff_server.application.audit import audit_entry
from flagstaff_server.application.errors import ApiKeyNotFoundError, InvalidApiKeyError
from flagstaff_server.application.lookups import require_environment, require_project
from flagstaff_server.domain.api_keys import ApiKey, ApiKeyKind
from flagstaff_server.domain.audit import AuditAction
from flagstaff_server.domain.ids import ApiKeyId

if TYPE_CHECKING:
    from flagstaff_server.application.ports import Clock, UnitOfWork
    from flagstaff_server.domain.audit import Actor, AuditEntry
    from flagstaff_server.domain.projects import Environment, Project
    from flagstaff_server.domain.values import Name, Slug

# Tells secret scanners and anyone reading a config file what the string is, and which kind:
# an admin key turning up in an app's environment variables is a mistake worth spotting.
SECRET_PREFIXES: Final = {ApiKeyKind.ADMIN: "fs_admin_", ApiKeyKind.SDK: "fs_sdk_"}


# A key with the project and environment it reads, so a listing can say "storefront / prod"
# instead of an id. Both are None for an admin key.
@dataclass(frozen=True, slots=True)
class ScopedApiKey:
    key: ApiKey
    project: Project | None = None
    environment: Environment | None = None


@dataclass(frozen=True, slots=True)
class IssuedApiKey:
    scoped: ScopedApiKey
    # Shown once. Only its hash is stored, so a lost secret is replaced, not recovered.
    secret: str

    @property
    def key(self) -> ApiKey:
        return self.scoped.key


# A secret carries 256 random bits, so unlike a password there is nothing to guess and a fast
# hash is enough: a slow one would only add latency to every SDK request.
def hash_secret(secret: str) -> str:
    return sha256(secret.encode()).hexdigest()


class ApiKeyService:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    async def issue_admin_key(self, actor: Actor, *, name: Name) -> IssuedApiKey:
        key = ApiKey.admin(key_id=ApiKeyId(uuid4()), name=name, at=self._clock.now())
        async with self._uow as uow:
            secret = await self._store(uow, key)
            await uow.audit.add(self._entry(AuditAction.API_KEY_ISSUED, actor, key))
            await uow.commit()
        return IssuedApiKey(ScopedApiKey(key), secret)

    async def issue_sdk_key(
        self, actor: Actor, project_key: Slug, environment_key: Slug, *, name: Name
    ) -> IssuedApiKey:
        async with self._uow as uow:
            project = await require_project(uow, project_key)
            environment = await require_environment(uow, project, environment_key)
            key = ApiKey.sdk(
                key_id=ApiKeyId(uuid4()),
                name=name,
                environment_id=environment.id,
                at=self._clock.now(),
            )
            secret = await self._store(uow, key)
            await uow.audit.add(self._entry(AuditAction.API_KEY_ISSUED, actor, key, environment))
            await uow.commit()
        return IssuedApiKey(ScopedApiKey(key, project, environment), secret)

    async def authenticate(self, secret: str) -> ApiKey:
        async with self._uow as uow:
            key = await uow.api_keys.find_by_secret_hash(hash_secret(secret))
        if key is None or not key.is_active:
            raise InvalidApiKeyError
        return key

    async def revoke(self, actor: Actor, key_id: ApiKeyId) -> ApiKey:
        async with self._uow as uow:
            key = await uow.api_keys.get(key_id)
            if key is None:
                raise ApiKeyNotFoundError(key_id)
            if key.revoke(at=self._clock.now()):
                environment = (
                    await uow.environments.get(key.environment_id) if key.environment_id else None
                )
                await uow.api_keys.update(key)
                await uow.audit.add(
                    self._entry(AuditAction.API_KEY_REVOKED, actor, key, environment)
                )
                await uow.commit()
        return key

    async def list_keys(self) -> list[ScopedApiKey]:
        async with self._uow as uow:
            keys = await uow.api_keys.list()
            environments = await uow.environments.get_many(
                {key.environment_id for key in keys if key.environment_id is not None}
            )
            projects = await uow.projects.get_many(
                {environment.project_id for environment in environments.values()}
            )
        listed = []
        for key in keys:
            environment = environments.get(key.environment_id) if key.environment_id else None
            project = projects.get(environment.project_id) if environment else None
            listed.append(ScopedApiKey(key, project, environment))
        return listed

    async def _store(self, uow: UnitOfWork, key: ApiKey) -> str:
        secret = SECRET_PREFIXES[key.kind] + secrets.token_urlsafe(32)
        await uow.api_keys.add(key, secret_hash=hash_secret(secret))
        return secret

    def _entry(
        self,
        action: AuditAction,
        actor: Actor,
        key: ApiKey,
        environment: Environment | None = None,
    ) -> AuditEntry:
        return audit_entry(
            action,
            actor=actor,
            at=key.revoked_at or key.created_at,
            subject=str(key.name),
            project_id=environment.project_id if environment else None,
            environment_id=environment.id if environment else None,
            changes={"key_id": str(key.id), "kind": key.kind.value},
        )
