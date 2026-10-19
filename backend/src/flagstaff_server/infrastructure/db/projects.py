from collections.abc import Collection

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from flagstaff_server.domain.errors import EnvironmentKeyTakenError, ProjectKeyTakenError
from flagstaff_server.domain.ids import EnvironmentId, ProjectId
from flagstaff_server.domain.projects import Environment, Project
from flagstaff_server.domain.values import Name, Slug
from flagstaff_server.infrastructure.db.tables import EnvironmentRow, ProjectRow


class SqlProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ON CONFLICT DO NOTHING waits for a competing insert of the same key to commit or roll
    # back, so two concurrent creates end with one project and one ProjectKeyTakenError.
    async def add(self, project: Project) -> None:
        inserted = await self._session.scalar(
            insert(ProjectRow)
            .values(
                id=project.id,
                key=str(project.key),
                name=str(project.name),
                created_at=project.created_at,
            )
            .on_conflict_do_nothing(index_elements=[ProjectRow.key])
            .returning(ProjectRow.id)
        )
        if inserted is None:
            raise ProjectKeyTakenError(project.key)

    async def get_by_key(self, key: Slug) -> Project | None:
        row = await self._session.scalar(select(ProjectRow).where(ProjectRow.key == str(key)))
        return _to_project(row) if row is not None else None

    async def get_many(self, project_ids: Collection[ProjectId]) -> dict[ProjectId, Project]:
        if not project_ids:
            return {}
        rows = await self._session.scalars(select(ProjectRow).where(ProjectRow.id.in_(project_ids)))
        return {ProjectId(row.id): _to_project(row) for row in rows}

    async def list(self) -> list[Project]:
        rows = await self._session.scalars(select(ProjectRow).order_by(ProjectRow.key))
        return [_to_project(row) for row in rows]


class SqlEnvironmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, environment: Environment) -> None:
        inserted = await self._session.scalar(
            insert(EnvironmentRow)
            .values(
                id=environment.id,
                project_id=environment.project_id,
                key=str(environment.key),
                name=str(environment.name),
                created_at=environment.created_at,
                ruleset_version=environment.ruleset_version,
            )
            .on_conflict_do_nothing(index_elements=[EnvironmentRow.project_id, EnvironmentRow.key])
            .returning(EnvironmentRow.id)
        )
        if inserted is None:
            project_key = (
                await self._session.execute(
                    select(ProjectRow.key).where(ProjectRow.id == environment.project_id)
                )
            ).scalar_one()
            raise EnvironmentKeyTakenError(Slug(project_key), environment.key)

    async def get(self, environment_id: EnvironmentId) -> Environment | None:
        row = await self._session.get(EnvironmentRow, environment_id)
        return _to_environment(row) if row is not None else None

    async def get_many(
        self, environment_ids: Collection[EnvironmentId]
    ) -> dict[EnvironmentId, Environment]:
        if not environment_ids:
            return {}
        rows = await self._session.scalars(
            select(EnvironmentRow).where(EnvironmentRow.id.in_(environment_ids))
        )
        return {EnvironmentId(row.id): _to_environment(row) for row in rows}

    async def get_by_key(self, project_id: ProjectId, key: Slug) -> Environment | None:
        row = await self._session.scalar(
            select(EnvironmentRow).where(
                EnvironmentRow.project_id == project_id, EnvironmentRow.key == str(key)
            )
        )
        return _to_environment(row) if row is not None else None

    async def list_for_project(self, project_id: ProjectId) -> list[Environment]:
        rows = await self._session.scalars(
            select(EnvironmentRow)
            .where(EnvironmentRow.project_id == project_id)
            .order_by(EnvironmentRow.created_order)
        )
        return [_to_environment(row) for row in rows]

    # ruleset_version + 1 is evaluated by Postgres under the row lock the UPDATE takes, so
    # concurrent bumps queue up and each one counts.
    async def bump_ruleset_versions(self, environment_ids: Collection[EnvironmentId]) -> None:
        if not environment_ids:
            return
        await self._session.execute(
            update(EnvironmentRow)
            .where(EnvironmentRow.id.in_(environment_ids))
            .values(ruleset_version=EnvironmentRow.ruleset_version + 1)
        )


def _to_project(row: ProjectRow) -> Project:
    return Project(
        id=ProjectId(row.id), key=Slug(row.key), name=Name(row.name), created_at=row.created_at
    )


def _to_environment(row: EnvironmentRow) -> Environment:
    return Environment(
        id=EnvironmentId(row.id),
        project_id=ProjectId(row.project_id),
        key=Slug(row.key),
        name=Name(row.name),
        created_at=row.created_at,
        ruleset_version=row.ruleset_version,
    )
