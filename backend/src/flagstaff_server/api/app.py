import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from importlib.metadata import version
from typing import Any, override

from fastapi import FastAPI
from starlette.types import ASGIApp, Lifespan

from flagstaff_server.api.container import Container
from flagstaff_server.api.errors import register_error_handlers
from flagstaff_server.api.routes import api_keys, audit, flags, projects, rulesets, stream
from flagstaff_server.api.tracing import RequestTracing


def create_app(container: Container) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        broadcasting = asyncio.create_task(container.broadcaster.run())
        yield
        # Streams end first, so every SDK reconnects, most likely to another instance.
        container.broadcaster.close()
        broadcasting.cancel()
        with suppress(asyncio.CancelledError):
            await broadcasting
        await container.close()

    app = _routed_app(lifespan)
    app.state.container = container
    return app


def openapi_schema() -> dict[str, Any]:
    # Routes resolve the container per request, so the schema can be built without a database
    # or any other setting; the dashboard's API types are generated from it.
    return _routed_app().openapi()


# add_middleware would put request tracing inside Starlette's error middleware, where a crash
# is only logged after the request's context is gone.
class _TracedFastAPI(FastAPI):
    @override
    def build_middleware_stack(self) -> ASGIApp:
        return RequestTracing(super().build_middleware_stack())


def _routed_app(lifespan: Lifespan[FastAPI] | None = None) -> FastAPI:
    app = _TracedFastAPI(title="Flagstaff", version=version("flagstaff-server"), lifespan=lifespan)
    register_error_handlers(app)
    for router in (
        projects.router,
        flags.router,
        rulesets.router,
        stream.router,
        api_keys.router,
        audit.router,
    ):
        app.include_router(router)

    # Liveness only: answers as long as the process serves requests. It deliberately doesn't
    # touch the database, so a database outage doesn't get every API container restarted.
    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
