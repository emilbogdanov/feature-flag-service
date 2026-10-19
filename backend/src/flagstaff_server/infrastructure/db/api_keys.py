from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select, update

from flagstaff_server.domain.api_keys import ApiKey
from flagstaff_server.domain.ids import ApiKeyId, EnvironmentId
from flagstaff_server.domain.values import Name
from flagstaff_server.infrastructure.db.tables import ApiKeyRow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class SqlApiKeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, key: ApiKey, *, secret_hash: str) -> None:
        self._session.add(
            ApiKeyRow(
                id=key.id,
                kind=key.kind,
                name=str(key.name),
                environment_id=key.environment_id,
                secret_hash=secret_hash,
                created_at=key.created_at,
                revoked_at=key.revoked_at,
            )
        )

    async def find_by_secret_hash(self, secret_hash: str) -> ApiKey | None:
        row = await self._session.scalar(
            select(ApiKeyRow).where(ApiKeyRow.secret_hash == secret_hash)
        )
        return _to_api_key(row) if row is not None else None

    async def get(self, key_id: ApiKeyId) -> ApiKey | None:
        row = await self._session.get(ApiKeyRow, key_id)
        return _to_api_key(row) if row is not None else None

    async def list(self) -> list[ApiKey]:
        rows = await self._session.scalars(
            select(ApiKeyRow).order_by(ApiKeyRow.created_at.desc(), ApiKeyRow.id)
        )
        return [_to_api_key(row) for row in rows]

    # Only the revocation time ever changes; name and kind are fixed when the key is issued.
    async def update(self, key: ApiKey) -> None:
        await self._session.execute(
            update(ApiKeyRow).where(ApiKeyRow.id == key.id).values(revoked_at=key.revoked_at)
        )


def _to_api_key(row: ApiKeyRow) -> ApiKey:
    return ApiKey(
        key_id=ApiKeyId(row.id),
        kind=row.kind,
        name=Name(row.name),
        environment_id=EnvironmentId(row.environment_id) if row.environment_id else None,
        created_at=row.created_at,
        revoked_at=row.revoked_at,
    )
