# The two SDK endpoints of a Flagstaff server, in memory, served through httpx's MockTransport.
# Safe to drive from the test's thread while a client reads it on its own thread and loop.
import asyncio
import json
import threading
from collections.abc import AsyncIterator

import httpx

from flagstaff.engine.ruleset import Ruleset
from flagstaff.engine.wire import ruleset_to_document
from tests.client.rulesets import storefront

SDK_KEY = "fs_sdk_test-key"
BASE_URL = "http://flagstaff.test"

type _Stream = tuple[asyncio.AbstractEventLoop, asyncio.Queue[str | None]]


class FakeServer:
    def __init__(self, ruleset: Ruleset | None = None) -> None:
        self.ruleset = ruleset or storefront(1)
        self.reachable = True
        self.requests: list[httpx.Request] = []
        self._streams: list[_Stream] = []
        self._lock = threading.Lock()

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    @property
    def open_streams(self) -> int:
        with self._lock:
            return len(self._streams)

    def requests_to(self, path: str) -> list[httpx.Request]:
        return [request for request in self.requests if request.url.path == path]

    def publish(self, ruleset: Ruleset) -> None:
        self.ruleset = ruleset
        self._send_to_streams(_event(ruleset))

    def send_raw(self, text: str) -> None:
        self._send_to_streams(text)

    # Ends every open stream, as a server instance shutting down would.
    def drop_streams(self) -> None:
        self._send_to_streams(None)

    def _send_to_streams(self, item: str | None) -> None:
        with self._lock:
            streams = list(self._streams)
        for loop, queue in streams:
            loop.call_soon_threadsafe(queue.put_nowait, item)

    async def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self.reachable:
            raise httpx.ConnectError("connection refused", request=request)
        if request.headers.get("Authorization") != f"Bearer {SDK_KEY}":
            return httpx.Response(401, json={"detail": "API key is missing, unknown or revoked"})
        etag = f'"{self.ruleset.version}"'
        if request.url.path == "/sdk/ruleset":
            if request.headers.get("If-None-Match") == etag:
                return httpx.Response(304, headers={"ETag": etag})
            return httpx.Response(
                200, json=ruleset_to_document(self.ruleset), headers={"ETag": etag}
            )
        if request.url.path == "/sdk/stream":
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                content=self._events(request.headers.get("Last-Event-ID")),
            )
        return httpx.Response(404)

    async def _events(self, last_event_id: str | None) -> AsyncIterator[bytes]:
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        stream = (asyncio.get_running_loop(), queue)
        with self._lock:
            self._streams.append(stream)
        try:
            yield b"retry: 1000\n\n"
            if last_event_id != str(self.ruleset.version):
                yield _event(self.ruleset).encode()
            while (item := await queue.get()) is not None:
                yield item.encode()
        finally:
            with self._lock:
                self._streams.remove(stream)


def _event(ruleset: Ruleset) -> str:
    document = json.dumps(ruleset_to_document(ruleset), separators=(",", ":"))
    return f"id: {ruleset.version}\nevent: ruleset\ndata: {document}\n\n"
