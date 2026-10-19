import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import uvicorn
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from flagstaff_server.api.app import create_app, openapi_schema
from flagstaff_server.application.api_keys import ApiKeyService
from flagstaff_server.config import Settings
from flagstaff_server.domain.audit import Actor
from flagstaff_server.domain.errors import InvalidValueError
from flagstaff_server.domain.values import Name
from flagstaff_server.infrastructure.clock import SystemClock
from flagstaff_server.infrastructure.db.engine import database_engine
from flagstaff_server.infrastructure.db.unit_of_work import SqlUnitOfWork
from flagstaff_server.infrastructure.logs import configure_logging
from flagstaff_server.main import build_container
from flagstaff_server.server import DrainingServer

_FAILED = 1
_USAGE_ERROR = 2


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        match args.command:
            case "serve":
                _serve(host=args.host, port=args.port, graceful_timeout=args.graceful_timeout)
            case "create-admin-key":
                _create_admin_key(Name(args.name))
            case "openapi":
                _write_openapi(args.output)
    except (InvalidValueError, ValidationError) as error:
        return _fail(args.command, str(error), _USAGE_ERROR)
    # A database that is down or refuses the login is the operator's to fix: one line, no traceback.
    except (OSError, DBAPIError) as error:
        return _fail(args.command, f"database error: {error}", _FAILED)
    return 0


def _fail(command: str, message: str, status: int) -> int:
    sys.stderr.write(f"flagstaff-server {command}: {message}\n")
    return status


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flagstaff-server")
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser(
        "serve",
        help="run the API server",
        description="Run the API server, configured by its FLAGSTAFF_ environment variables.",
    )
    serve.add_argument("--host", default="127.0.0.1", help="address to listen on")
    serve.add_argument("--port", type=int, default=8000, help="port to listen on")
    serve.add_argument(
        "--graceful-timeout",
        type=int,
        default=10,
        metavar="SECONDS",
        help="how long requests in flight get to finish on shutdown (default: 10)",
    )

    # The API only issues keys to an admin, so the first admin key has to come from here.
    create_admin_key = commands.add_parser(
        "create-admin-key",
        help="issue an admin key and print its secret",
        description="Issue an admin key and print its secret, which is not stored and is shown"
        " only once. Reads the server's FLAGSTAFF_ settings to reach the database.",
    )
    create_admin_key.add_argument("--name", required=True, help="who or what the key is for")

    openapi = commands.add_parser(
        "openapi",
        help="write the API's OpenAPI schema",
        description="Write the API's OpenAPI schema as JSON. Needs no database or settings.",
    )
    openapi.add_argument("--output", type=Path, help="file to write instead of standard output")
    return parser


def _serve(*, host: str, port: int, graceful_timeout: int) -> None:
    settings = Settings()
    configure_logging(settings.log_level, settings.log_format)
    container = build_container(settings)
    config = uvicorn.Config(
        create_app(container),
        host=host,
        port=port,
        # Logging is already set up, uvicorn's messages included, and the app logs each request.
        log_config=None,
        access_log=False,
        timeout_graceful_shutdown=graceful_timeout,
    )
    DrainingServer(config, end_streams=container.broadcaster.close).run()


def _create_admin_key(name: Name) -> None:
    secret = asyncio.run(_issue_admin_key(Settings(), name))
    # The secret alone on standard output, so a script can capture it; the note goes to stderr.
    sys.stdout.write(f"{secret}\n")
    sys.stderr.write("Admin key issued. Store the secret now: it cannot be shown again.\n")


async def _issue_admin_key(settings: Settings, name: Name) -> str:
    engine = database_engine(str(settings.database_url))
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        keys = ApiKeyService(SqlUnitOfWork(session_factory), SystemClock())
        issued = await keys.issue_admin_key(Actor.command_line(), name=name)
    finally:
        await engine.dispose()
    return issued.secret


def _write_openapi(output: Path | None) -> None:
    document = json.dumps(openapi_schema(), indent=2) + "\n"
    if output is None:
        sys.stdout.write(document)
    else:
        output.write_text(document, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
