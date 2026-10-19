from __future__ import annotations

import asyncio
import threading
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Self

from flagstaff._connection import ConnectionOptions, RulesetUpdater
from flagstaff._store import RulesetStore
from flagstaff.reader import FlagReader

if TYPE_CHECKING:
    from types import TracebackType

    import httpx


# For apps without an event loop of their own: Django, Flask, workers, scripts. Updates run on
# a daemon thread with its own loop, so they never block a request and never need the app's
# cooperation; evaluations read the shared rules from any thread.
#
# A process that forks after creating a client, such as a preloading gunicorn master, leaves
# the thread behind in the parent; create clients in each worker instead.
class FlagstaffClient(FlagReader):
    def __init__(
        self,
        sdk_key: str,
        *,
        base_url: str,
        streaming: bool = True,
        poll_interval: float = 60.0,
        cache_path: str | Path | None = None,
        connect_timeout: float = 5.0,
        read_timeout: float = 45.0,
        initial_reconnect_delay: float = 0.5,
        max_reconnect_delay: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(RulesetStore())
        self._updater = RulesetUpdater(
            ConnectionOptions(
                sdk_key=sdk_key,
                base_url=base_url,
                streaming=streaming,
                poll_interval=poll_interval,
                cache_path=Path(cache_path) if cache_path is not None else None,
                connect_timeout=connect_timeout,
                read_timeout=read_timeout,
                initial_reconnect_delay=initial_reconnect_delay,
                max_reconnect_delay=max_reconnect_delay,
                transport=transport,
            ),
            self._store,
        )
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop: asyncio.Event | None = None
        self._started = threading.Event()
        self._thread = threading.Thread(target=self._run, name="flagstaff-updater", daemon=True)
        self._thread.start()
        self._started.wait()

    def wait_until_ready(self, timeout: float | None = None) -> bool:
        return self._store.wait_until_ready(timeout)

    def close(self, timeout: float = 5.0) -> None:
        if self._loop is not None and self._stop is not None and self._thread.is_alive():
            self._loop.call_soon_threadsafe(self._stop.set)
        self._thread.join(timeout)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _run(self) -> None:
        asyncio.run(self._update_until_stopped())

    async def _update_until_stopped(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        self._started.set()
        updating = asyncio.create_task(self._updater.run())
        await self._stop.wait()
        updating.cancel()
        with suppress(asyncio.CancelledError):
            await updating
