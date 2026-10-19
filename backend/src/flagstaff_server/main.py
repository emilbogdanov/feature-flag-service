from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from flagstaff_server.api.app import create_app
from flagstaff_server.api.container import Container
from flagstaff_server.application.api_keys import ApiKeyService
from flagstaff_server.application.authentication import AuthenticatedKeys
from flagstaff_server.application.live import KnownVersions, RulesetBroadcaster
from flagstaff_server.application.rulesets import RulesetService
from flagstaff_server.config import Settings
from flagstaff_server.infrastructure.clock import SystemClock
from flagstaff_server.infrastructure.db.engine import database_engine
from flagstaff_server.infrastructure.db.unit_of_work import SqlUnitOfWork
from flagstaff_server.infrastructure.logs import configure_logging
from flagstaff_server.infrastructure.redis_changes import RedisRulesetChanges

# Seconds to wait for Redis to accept a connection before giving up on it.
_REDIS_CONNECT_TIMEOUT = 5


def build_container(settings: Settings) -> Container:
    engine = database_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    # No socket timeout: the change feed blocks on a read for as long as nothing changes. The
    # health check is what notices a connection that died quietly.
    redis = Redis.from_url(
        str(settings.redis_url),
        socket_connect_timeout=_REDIS_CONNECT_TIMEOUT,
        health_check_interval=30,
    )

    async def close() -> None:
        await redis.aclose()
        await engine.dispose()

    changes = RedisRulesetChanges(redis)
    clock = SystemClock()
    broadcaster = RulesetBroadcaster(
        lambda: RulesetService(SqlUnitOfWork(session_factory)),
        changes,
        resync_interval=settings.ruleset_resync_seconds,
        versions=KnownVersions(max_age=settings.version_cache_seconds),
    )
    return Container(
        uow_factory=lambda: SqlUnitOfWork(session_factory),
        clock=clock,
        ruleset_changes=changes,
        broadcaster=broadcaster,
        authenticated_keys=AuthenticatedKeys(
            lambda: ApiKeyService(SqlUnitOfWork(session_factory), clock),
            ttl=settings.key_cache_seconds,
        ),
        stream_heartbeat_seconds=settings.stream_heartbeat_seconds,
        close=close,
    )


def app() -> FastAPI:
    # For development: uvicorn --factory --reload flagstaff_server.main:app. Deployments run
    # flagstaff-server serve, which also ends SDK streams promptly on shutdown.
    settings = Settings()
    configure_logging(settings.log_level, settings.log_format)
    return create_app(build_container(settings))
