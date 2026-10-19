from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Self

from flagstaff._connection import ConnectionOptions, RulesetUpdater
from flagstaff._store import RulesetStore
from flagstaff.reader import FlagReader

if TYPE_CHECKING:
    from types import TracebackType

    import httpx

    from flagstaff.engine.ruleset import Ruleset


# For asyncio apps. Updates run as a task on the app's own event loop; evaluations never await
# and never touch the network.
class AsyncFlagstaffClient(FlagReader):
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
        self._updating: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._updating is None:
            self._updating = asyncio.create_task(self._updater.run(), name="flagstaff-updater")

    async def wait_until_ready(self, timeout: float | None = None) -> bool:
        if self.is_ready:
            return True
        loop = asyncio.get_running_loop()
        arrived: asyncio.Future[None] = loop.create_future()

        def resolve() -> None:
            if not arrived.done():
                arrived.set_result(None)

        def on_ruleset(_: Ruleset) -> None:
            loop.call_soon_threadsafe(resolve)

        self._store.add_listener(on_ruleset)
        try:
            # Checked again now that the listener is in place, so a ruleset that arrived in
            # between isn't missed.
            if self._store.ruleset is None:
                async with asyncio.timeout(timeout):
                    await arrived
        except TimeoutError:
            return False
        else:
            return True
        finally:
            self._store.remove_listener(on_ruleset)

    async def aclose(self) -> None:
        updating, self._updating = self._updating, None
        if updating is not None:
            updating.cancel()
            with suppress(asyncio.CancelledError):
                await updating

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
