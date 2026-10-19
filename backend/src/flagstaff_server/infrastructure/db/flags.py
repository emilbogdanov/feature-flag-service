from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from flagstaff.engine.wire import variants_from_document, variants_to_document
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from flagstaff_server.application.errors import StaleFlagError
from flagstaff_server.domain.errors import FlagKeyTakenError
from flagstaff_server.domain.flags import Flag, Targeting
from flagstaff_server.domain.ids import EnvironmentId, FlagId, ProjectId
from flagstaff_server.domain.values import Description, Name, Slug
from flagstaff_server.infrastructure.db.tables import FlagRow, FlagTargetingRow, ProjectRow

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


class SqlFlagRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, flag: Flag) -> None:
        inserted = await self._session.scalar(
            insert(FlagRow)
            .values(
                id=flag.id,
                project_id=flag.project_id,
                key=flag.key,
                version=flag.version,
                **_flag_columns(flag),
            )
            .on_conflict_do_nothing(index_elements=[FlagRow.project_id, FlagRow.key])
            .returning(FlagRow.id)
        )
        if inserted is None:
            project_key = (
                await self._session.execute(
                    select(ProjectRow.key).where(ProjectRow.id == flag.project_id)
                )
            ).scalar_one()
            raise FlagKeyTakenError(Slug(project_key), flag.key)
        await self._save_targeting(flag)

    async def get(self, project_id: ProjectId, key: str) -> Flag | None:
        row = await self._session.scalar(
            select(FlagRow).where(FlagRow.project_id == project_id, FlagRow.key == key)
        )
        if row is None:
            return None
        [flag] = await self._with_targeting([row])
        return flag

    async def list_active(self, project_id: ProjectId) -> list[Flag]:
        rows = await self._session.scalars(
            select(FlagRow)
            .where(FlagRow.project_id == project_id, FlagRow.archived_at.is_(None))
            .order_by(FlagRow.key)
        )
        return await self._with_targeting(rows.all())

    # The WHERE on version makes the save conditional. Under READ COMMITTED, an UPDATE that
    # waited for a competing one re-checks the condition against the row that one committed,
    # so of two saves from the same version exactly one goes through.
    async def update(self, flag: Flag) -> None:
        saved = await self._session.scalar(
            update(FlagRow)
            .where(FlagRow.id == flag.id, FlagRow.version == flag.version)
            .values(version=flag.version + 1, **_flag_columns(flag))
            .returning(FlagRow.id)
        )
        if saved is None:
            actual = await self._session.scalar(
                select(FlagRow.version).where(FlagRow.id == flag.id)
            )
            raise StaleFlagError(flag.key, expected=flag.version, actual=actual)
        await self._save_targeting(flag)
        flag.mark_saved()

    async def _save_targeting(self, flag: Flag) -> None:
        if not flag.targeting:
            return
        statement = insert(FlagTargetingRow).values(
            [
                {
                    "flag_id": flag.id,
                    "environment_id": environment_id,
                    "targeting": targeting.to_document(),
                }
                for environment_id, targeting in flag.targeting.items()
            ]
        )
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[FlagTargetingRow.flag_id, FlagTargetingRow.environment_id],
                set_={"targeting": statement.excluded.targeting},
            )
        )

    # One query for the targeting of every flag at once, however many flags there are.
    async def _with_targeting(self, rows: Sequence[FlagRow]) -> list[Flag]:
        if not rows:
            return []
        targeting_rows = await self._session.scalars(
            select(FlagTargetingRow).where(FlagTargetingRow.flag_id.in_([row.id for row in rows]))
        )
        targeting: defaultdict[UUID, list[FlagTargetingRow]] = defaultdict(list)
        for targeting_row in targeting_rows:
            targeting[targeting_row.flag_id].append(targeting_row)
        return [_to_flag(row, targeting[row.id]) for row in rows]


def _flag_columns(flag: Flag) -> dict[str, object]:
    return {
        "name": str(flag.name),
        "description": str(flag.description),
        "kind": flag.kind,
        "variants": variants_to_document(flag.variants),
        "initial_targeting": flag.initial_targeting.to_document(),
        "created_at": flag.created_at,
        "updated_at": flag.updated_at,
        "archived_at": flag.archived_at,
    }


def _to_flag(row: FlagRow, targeting: Iterable[FlagTargetingRow]) -> Flag:
    return Flag(
        flag_id=FlagId(row.id),
        project_id=ProjectId(row.project_id),
        key=row.key,
        name=Name(row.name),
        description=Description(row.description),
        kind=row.kind,
        variants=variants_from_document(row.variants),
        initial_targeting=Targeting.from_document(row.initial_targeting),
        targeting={
            EnvironmentId(stored.environment_id): Targeting.from_document(stored.targeting)
            for stored in targeting
        },
        created_at=row.created_at,
        updated_at=row.updated_at,
        archived_at=row.archived_at,
        version=row.version,
    )
