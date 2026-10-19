from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from importlib.metadata import version
from typing import TYPE_CHECKING

import httpx

from flagstaff._backoff import Backoff
from flagstaff._cache import RulesetFile
from flagstaff._sse import SseDecoder
from flagstaff.engine.errors import InvalidFlagError
from flagstaff.engine.wire import ruleset_from_document

if TYPE_CHECKING:
    from pathlib import Path

    from flagstaff._store import RulesetStore
    from flagstaff.engine.ruleset import Ruleset

logger = logging.getLogger("flagstaff")

_USER_AGENT = f"flagstaff-python/{version('flagstaff')}"


@dataclass(frozen=True, slots=True, kw_only=True)
class ConnectionOptions:
    sdk_key: str
    base_url: str
    streaming: bool
    poll_interval: float
    cache_path: Path | None
    connect_timeout: float
    # How long a stream may go without sending anything, keep-alives included, before it is
    # taken for dead. The server sends one every 15 seconds by default.
    read_timeout: float
    initial_reconnect_delay: float
    max_reconnect_delay: float
    transport: httpx.AsyncBaseTransport | None


class _KeyRejectedError(Exception):
    pass


# Keeps the store current until cancelled. Every failure short of a rejected key is retried
# with backoff, and none of them touch the rules already in the store: an app keeps evaluating
# what it last received for as long as the server stays away.
class RulesetUpdater:
    def __init__(self, options: ConnectionOptions, store: RulesetStore) -> None:
        self._options = options
        self._store = store
        self._cache = RulesetFile(options.cache_path) if options.cache_path else None
        self._backoff = Backoff(
            base_seconds=options.initial_reconnect_delay, max_seconds=options.max_reconnect_delay
        )

    async def run(self) -> None:
        if self._cache is not None and (cached := await asyncio.to_thread(self._cache.load)):
            self._store.replace(cached)
        async with self._http_client() as http:
            while True:
                try:
                    if self._options.streaming:
                        await self._stream(http)
                    else:
                        await self._poll(http)
                        await asyncio.sleep(self._options.poll_interval)
                        continue
                except _KeyRejectedError:
                    break
                except (httpx.HTTPError, InvalidFlagError, ValueError) as error:
                    delay = self._backoff.next_delay()
                    logger.warning(
                        "lost the connection to the flag server (%s); retrying in %.1fs",
                        error,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                # The server ended the stream, as it does when an instance shuts down.
                await asyncio.sleep(self._backoff.next_delay())
        # A rejected key won't start working on its own, and retrying would only hammer the
        # server; the rules already held keep being served.
        logger.error("the server rejected the SDK key; no more updates will arrive")

    # The first event is the current ruleset, unless Last-Event-ID says this app holds it.
    async def _stream(self, http: httpx.AsyncClient) -> None:
        headers = {"Accept": "text/event-stream"}
        if (held := self._store.ruleset) is not None:
            headers["Last-Event-ID"] = str(held.version)
        async with http.stream("GET", "/sdk/stream", headers=headers) as response:
            _raise_for_status(response)
            self._backoff.reset()
            decoder = SseDecoder()
            async for line in response.aiter_lines():
                event = decoder.feed(line)
                if event is not None and event.event == "ruleset":
                    await self._receive(event.data)

    async def _poll(self, http: httpx.AsyncClient) -> None:
        headers = {}
        if (held := self._store.ruleset) is not None:
            headers["If-None-Match"] = f'"{held.version}"'
        response = await http.get("/sdk/ruleset", headers=headers)
        _raise_for_status(response)
        self._backoff.reset()
        if response.status_code != httpx.codes.NOT_MODIFIED:
            await self._receive(response.text)

    async def _receive(self, document: str) -> None:
        try:
            ruleset = ruleset_from_document(json.loads(document))
        except (ValueError, InvalidFlagError):
            # One bad document, say from a newer server mid-deploy, shouldn't cost the stream.
            logger.warning("ignored a ruleset this SDK could not read", exc_info=True)
            return
        if self._store.replace(ruleset) and self._cache is not None:
            # Shielded: cancelling a to_thread call that hasn't started yet drops it, and a client
            # closed right after a change would then restart on the version before it.
            await asyncio.shield(asyncio.to_thread(self._save, ruleset))

    def _save(self, ruleset: Ruleset) -> None:
        if self._cache is not None:
            self._cache.save(ruleset)

    def _http_client(self) -> httpx.AsyncClient:
        options = self._options
        return httpx.AsyncClient(
            base_url=options.base_url,
            headers={"Authorization": f"Bearer {options.sdk_key}", "User-Agent": _USER_AGENT},
            timeout=httpx.Timeout(options.read_timeout, connect=options.connect_timeout),
            transport=options.transport,
        )


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code in {httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN}:
        raise _KeyRejectedError
    if response.status_code != httpx.codes.NOT_MODIFIED:
        response.raise_for_status()
