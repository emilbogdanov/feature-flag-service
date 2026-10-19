from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING, Final
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders

from flagstaff_server.infrastructure.logs import log_context

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

    from flagstaff_server.api.metrics import Metrics

logger = logging.getLogger("flagstaff_server.requests")

REQUEST_ID_HEADER: Final = "X-Request-ID"
# A caller's own id, from a gateway or another service, is kept so one request can be followed
# across systems. It ends up in every log line and back in a header, so only a short, plain one.
_ACCEPTED_REQUEST_ID: Final = re.compile(r"[A-Za-z0-9._:-]{1,128}")
# Probes and scrapes arrive every few seconds and would bury the real traffic at INFO.
_ROUTINE_PATHS: Final = frozenset({"/health", "/metrics"})


# Wraps the whole app, Starlette's error handling included, so every log line a request causes,
# the traceback of a crash among them, carries the request's id. Plain ASGI, so an SDK stream
# passes through untouched and is logged and counted once, when it closes.
class RequestTracing:
    def __init__(self, app: ASGIApp, metrics: Metrics) -> None:
        self._app = app
        self._metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = _request_id(scope)
        started = time.perf_counter()
        status: int | None = None
        streaming = False

        async def send_with_id(message: Message) -> None:
            nonlocal status, streaming
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID_HEADER] = request_id
                streaming = headers.get("content-type", "").startswith("text/event-stream")
            await send(message)

        with log_context(request_id=request_id):
            try:
                await self._app(scope, receive, send_with_id)
            # Starlette has already answered 500 when it still could, and re-raises only so the
            # server logs the error. Logging it here instead puts the request id on it.
            except Exception:
                logger.exception("unhandled error", extra={"path": scope["path"]})
            elapsed = time.perf_counter() - started
            self._finished(scope, status, elapsed, streaming=streaming)

    def _finished(
        self, scope: Scope, status: int | None, seconds: float, *, streaming: bool
    ) -> None:
        path: str = scope["path"]
        logger.log(
            logging.DEBUG if path in _ROUTINE_PATHS else logging.INFO,
            "request finished",
            extra={
                "method": scope["method"],
                "path": path,
                # None when the client went away before any response started.
                "status": status,
                "duration_ms": round(seconds * 1000, 1),
            },
        )
        if status is None:
            return
        self._metrics.observe_request(
            method=scope["method"],
            # FastAPI leaves the matched route in the scope. Its path template, rather than the
            # path asked for, keeps one series per endpoint.
            route=getattr(scope.get("route"), "path", None),
            status=status,
            seconds=None if streaming else seconds,
        )


def _request_id(scope: Scope) -> str:
    offered = Headers(scope=scope).get(REQUEST_ID_HEADER)
    if offered is not None and _ACCEPTED_REQUEST_ID.fullmatch(offered):
        return offered
    return uuid4().hex
