import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

BACKEND_ROOT = Path(__file__).resolve().parents[2]
POSTGRES_IMAGE = "postgres:18-alpine"
REDIS_IMAGE = "redis:8-alpine"
TABLES = "projects, environments, flags, flag_targeting, api_keys, audit_entries"


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    # Set FLAGSTAFF_TEST_DATABASE_URL to run against a database you already have. The tests
    # drop and recreate its schema, so never point it at one whose data you want to keep.
    configured = os.environ.get("FLAGSTAFF_TEST_DATABASE_URL")
    if configured:
        yield configured
        return
    with PostgresContainer(POSTGRES_IMAGE, driver="asyncpg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    # Same deal as the database: FLAGSTAFF_TEST_REDIS_URL reuses a Redis you already run, and
    # the tests flush it, so point it at nothing you care about.
    configured = os.environ.get("FLAGSTAFF_TEST_REDIS_URL")
    if configured:
        yield configured
        return
    with RedisContainer(REDIS_IMAGE) as redis:
        yield f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0"


@pytest.fixture
async def redis(redis_url: str) -> AsyncIterator[Redis]:
    client = Redis.from_url(redis_url)
    await client.flushdb()
    yield client
    await client.aclose()


@pytest.fixture(scope="session")
def alembic_config(database_url: str) -> Config:
    config = Config(BACKEND_ROOT / "alembic.ini")
    # The .ini parser treats % as interpolation; URL-encoded passwords contain it.
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="session", autouse=True)
def migrated_schema(alembic_config: Config) -> None:
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url)
    yield engine
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {TABLES}"))
    await engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
