from typing import Final

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# asyncpg timeouts, in seconds: fail fast when the database is unreachable or a query hangs,
# instead of holding the request, and a pool connection, open indefinitely.
_CONNECT_TIMEOUT: Final = 5
_QUERY_TIMEOUT: Final = 15


def database_engine(url: str) -> AsyncEngine:
    return create_async_engine(
        url,
        pool_pre_ping=True,
        connect_args={"timeout": _CONNECT_TIMEOUT, "command_timeout": _QUERY_TIMEOUT},
    )
