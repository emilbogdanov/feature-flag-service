from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from flagstaff_server.api.app import create_app
from flagstaff_server.api.container import Container
from flagstaff_server.application.live import RulesetBroadcaster
from flagstaff_server.application.rulesets import RulesetService
from flagstaff_server.config import Settings
from flagstaff_server.infrastructure.clock import SystemClock
from flagstaff_server.infrastructure.db.unit_of_work import SqlUnitOfWork
from flagstaff_server.infrastructure.logs import configure_logging
from flagstaff_server.infrastructure.redis_changes import RedisRulesetChanges

# asyncpg timeouts, in seconds: fail fast when the database is unreachable or a query hangs,
# instead of holding the request, and a pool connection, open indefinitely.
_CONNECT_TIMEOUT = 5
_QUERY_TIMEOUT = 15


def build_container(settings: Settings) -> Container:
    engine = create_async_engine(
        str(settings.database_url),
        pool_pre_ping=True,
        connect_args={"timeout": _CONNECT_TIMEOUT, "command_timeout": _QUERY_TIMEOUT},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    # No socket timeout: the change feed blocks on a read for as long as nothing changes. The
    # health check is what notices a connection that died quietly.
    redis = Redis.from_url(
        str(settings.redis_url),
        socket_connect_timeout=_CONNECT_TIMEOUT,
        health_check_interval=30,
    )

    async def close() -> None:
        await redis.aclose()
        await engine.dispose()

    changes = RedisRulesetChanges(redis)
    broadcaster = RulesetBroadcaster(
        lambda: RulesetService(SqlUnitOfWork(session_factory)),
        changes,
        resync_interval=settings.ruleset_resync_seconds,
    )
    return Container(
        uow_factory=lambda: SqlUnitOfWork(session_factory),
        clock=SystemClock(),
        ruleset_changes=changes,
        broadcaster=broadcaster,
        stream_heartbeat_seconds=settings.stream_heartbeat_seconds,
        close=close,
    )


def app() -> FastAPI:
    # Run with: uvicorn --factory flagstaff_server.main:app
    settings = Settings()
    configure_logging(settings.log_level, settings.log_format)
    return create_app(build_container(settings))
