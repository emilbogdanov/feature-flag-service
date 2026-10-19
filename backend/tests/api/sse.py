# Just enough of an SSE client to read what /sdk/stream sends.
import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import uvicorn
from fastapi import FastAPI
from httpx import Response

from flagstaff_server.server import DrainingServer


@dataclass
class Event:
    event: str = "message"
    data: str = ""
    id: str | None = None
    comments: list[str] = field(default_factory=list)
    retry: str | None = None


async def events(response: Response) -> AsyncIterator[Event]:
    current = Event()
    async for line in response.aiter_lines():
        if not line:
            yield current
            current = Event()
            continue
        name, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if not name:
            current.comments.append(value)
        elif name == "data":
            current.data = value
        elif name in {"event", "id", "retry"}:
            setattr(current, name, value)


async def next_event(stream: AsyncIterator[Event], *, kind: str, within: float = 2.0) -> Event:
    async with asyncio.timeout(within):
        async for event in stream:
            if event.event == kind and event.data:
                return event
    raise AssertionError(f"the stream ended before a {kind} event")


# A real server rather than httpx's ASGI transport, which waits for the whole response body and
# so never returns from an endless stream. It drains like the deployed one, so stopping it ends
# its streams straight away; the graceful timeout is long enough for a test to notice if not.
class RunningServer:
    # Port 0 lets the OS pick; pass a port to bring a server back where clients expect it.
    def __init__(self, app: FastAPI, *, port: int = 0) -> None:
        self._server = DrainingServer(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=port,
                log_level="critical",
                lifespan="on",
                timeout_graceful_shutdown=10,
            ),
            end_streams=app.state.container.broadcaster.close,
        )
        self._task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> str:
        self._task = asyncio.create_task(self._server.serve())
        async with asyncio.timeout(5):
            while not self._server.started:
                await asyncio.sleep(0.01)
        [socket] = self._server.servers[0].sockets
        host, port = socket.getsockname()[:2]
        return f"http://{host}:{port}"

    async def __aexit__(self, *_: object) -> None:
        await self.stop()

    async def stop(self) -> None:
        self._server.should_exit = True
        if self._task is not None:
            await self._task
