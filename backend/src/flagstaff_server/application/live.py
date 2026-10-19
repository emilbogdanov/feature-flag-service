from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from flagstaff.engine.wire import ruleset_to_document

from flagstaff_server.application.errors import ChangeFeedLostError, ChangeFeedUnavailableError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Collection

    from flagstaff_server.application.ports import RulesetChangeFeed
    from flagstaff_server.application.rulesets import RulesetService
    from flagstaff_server.domain.ids import EnvironmentId

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PublishedRuleset:
    version: int
    # The ruleset as JSON, built once per version for every stream that sends it.
    document: str


class StreamClosedError(Exception):
    pass


# Each environment's ruleset version as this instance last heard it, from the change feed or
# the database. The feed normally keeps it current within milliseconds; trusting an entry for
# no more than max_age seconds bounds how far behind it can be when a notification is lost.
class KnownVersions:
    def __init__(self, *, max_age: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._max_age = max_age
        self._clock = clock
        self._versions: dict[EnvironmentId, tuple[int, float]] = {}

    def get(self, environment_id: EnvironmentId) -> int | None:
        known = self._versions.get(environment_id)
        if known is None or self._clock() - known[1] >= self._max_age:
            return None
        return known[0]

    # Versions only move forward, so a late notification for an older one changes nothing.
    def record(self, environment_id: EnvironmentId, version: int) -> None:
        known = self._versions.get(environment_id)
        if known is None or version >= known[0]:
            self._versions[environment_id] = (version, self._clock())


# Running totals for this instance, read on every metrics scrape.
@dataclass(slots=True)
class BroadcastStats:
    rulesets_built: int = 0
    feed_interruptions: int = 0
    load_failures: int = 0


# One SSE stream's view of its environment. It only ever holds the newest ruleset it hasn't
# sent yet, so a client that reads slowly skips versions instead of piling them up in memory.
class RulesetSubscription:
    def __init__(self, environment_id: EnvironmentId, *, known_version: int | None) -> None:
        self.environment_id = environment_id
        self._sent_version = known_version
        self._pending: PublishedRuleset | None = None
        self._changed = asyncio.Event()
        self._closed = False

    def offer(self, ruleset: PublishedRuleset) -> None:
        newest = self._pending.version if self._pending else self._sent_version
        if newest is None or ruleset.version > newest:
            self._pending = ruleset
            self._changed.set()

    # Waits for a version newer than the last one sent; raises StreamClosedError at shutdown.
    async def next(self) -> PublishedRuleset:
        while True:
            if self._closed:
                raise StreamClosedError
            if self._pending is not None:
                ruleset, self._pending = self._pending, None
                self._sent_version = ruleset.version
                return ruleset
            self._changed.clear()
            await self._changed.wait()

    def close(self) -> None:
        self._closed = True
        self._changed.set()


# Fans each environment's ruleset out to this instance's streams. Changes arrive two ways: the
# feed, usually within milliseconds of a commit on any instance, and a resync that compares
# versions with the database on a timer, which catches whatever the feed missed while it was
# down. Either way the ruleset is built once per version, however many streams want it.
class RulesetBroadcaster:
    def __init__(
        self,
        rulesets: Callable[[], RulesetService],
        feed: RulesetChangeFeed,
        *,
        resync_interval: float,
        feed_retry_delay: float = 1.0,
        versions: KnownVersions | None = None,
    ) -> None:
        self._rulesets = rulesets
        self._feed = feed
        # Without a cache, every version question goes to the database.
        self._versions = versions or KnownVersions(max_age=0)
        self._resync_interval = resync_interval
        self._feed_retry_delay = feed_retry_delay
        self._subscriptions: defaultdict[EnvironmentId, set[RulesetSubscription]] = defaultdict(set)
        self._published: dict[EnvironmentId, PublishedRuleset] = {}
        self._building: defaultdict[EnvironmentId, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.stats = BroadcastStats()
        self._closed = False

    # What a poll checks its ETag against. The answer comes from memory while the feed keeps it
    # fresh, and from the database otherwise.
    async def current_versions(
        self, environment_ids: Collection[EnvironmentId]
    ) -> dict[EnvironmentId, int]:
        known = {i: v for i in environment_ids if (v := self._versions.get(i)) is not None}
        missing = [i for i in environment_ids if i not in known]
        if missing:
            looked_up = await self._rulesets().current_versions(missing)
            for environment_id, version in looked_up.items():
                self._versions.record(environment_id, version)
            known.update(looked_up)
        return known

    @property
    def stream_count(self) -> int:
        return sum(len(subscriptions) for subscriptions in self._subscriptions.values())

    # known_version is what the client already holds, from SSE's Last-Event-ID; the first
    # ruleset sent is the current one unless that is it.
    @asynccontextmanager
    async def subscribe(
        self, environment_id: EnvironmentId, *, known_version: int | None
    ) -> AsyncIterator[RulesetSubscription]:
        subscription = RulesetSubscription(environment_id, known_version=known_version)
        # A stream that slips in while the server shuts down ends at once, like the rest.
        if self._closed:
            subscription.close()
        self._subscriptions[environment_id].add(subscription)
        try:
            # Checked against the database rather than taken from the cache, which may be
            # behind if the feed missed a change.
            versions = await self._rulesets().current_versions([environment_id])
            await self._publish(environment_id, versions.get(environment_id))
            yield subscription
        finally:
            self._unsubscribe(subscription)

    async def run(self) -> None:
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(self._follow_feed())
            tasks.create_task(self._resync_periodically())

    async def resync(self) -> None:
        watched = [environment for environment, subs in self._subscriptions.items() if subs]
        if not watched:
            return
        for environment_id, version in (await self._rulesets().current_versions(watched)).items():
            self._versions.record(environment_id, version)
            await self._publish(environment_id, version)

    def close(self) -> None:
        self._closed = True
        for subscriptions in self._subscriptions.values():
            for subscription in subscriptions:
                subscription.close()

    # While Redis is down every resubscribe fails, once per retry delay. Only the first failure
    # of an outage is a warning; a feed that subscribed and then dropped starts a new one.
    async def _follow_feed(self) -> None:
        outage_reported = False
        while True:
            try:
                async for change in self._feed.listen():
                    self._versions.record(change.environment_id, change.version)
                    if self._subscriptions.get(change.environment_id):
                        await self._publish_safely(change.environment_id, change.version)
            except ChangeFeedUnavailableError as error:
                self.stats.feed_interruptions += 1
                logger.log(
                    logging.DEBUG if outage_reported else logging.WARNING,
                    "cannot subscribe to the ruleset change feed; retrying",
                    extra={"error": _cause(error)},
                )
                outage_reported = True
            except ChangeFeedLostError as error:
                self.stats.feed_interruptions += 1
                logger.warning(
                    "lost the ruleset change feed; resubscribing", extra={"error": _cause(error)}
                )
                outage_reported = True
            await asyncio.sleep(self._feed_retry_delay)

    async def _resync_periodically(self) -> None:
        while True:
            await asyncio.sleep(self._resync_interval)
            try:
                await self.resync()
            # A background loop that dies leaves streams silently stale, so a database outage
            # is logged and retried on the next tick instead.
            except Exception:
                self.stats.load_failures += 1
                logger.warning("ruleset resync failed; retrying next interval", exc_info=True)

    async def _publish_safely(self, environment_id: EnvironmentId, version: int) -> None:
        try:
            await self._publish(environment_id, version)
        except Exception:
            self.stats.load_failures += 1
            logger.warning(
                "could not load a changed ruleset; the next resync retries it",
                exc_info=True,
                extra={"environment_id": str(environment_id), "version": version},
            )

    # Builds the ruleset unless the cached one is already at least at version, then offers it
    # to every stream on the environment. The lock keeps a burst of announcements for one
    # environment from building the same ruleset many times over.
    async def _publish(self, environment_id: EnvironmentId, version: int | None) -> None:
        async with self._building[environment_id]:
            cached = self._published.get(environment_id)
            if cached is None or version is None or cached.version < version:
                ruleset = await self._rulesets().ruleset_for(environment_id)
                self.stats.rulesets_built += 1
                built = PublishedRuleset(
                    ruleset.version, json.dumps(ruleset_to_document(ruleset), separators=(",", ":"))
                )
                if cached is None or built.version > cached.version:
                    self._published[environment_id] = cached = built
        for subscription in self._subscriptions.get(environment_id, ()):
            subscription.offer(cached)

    def _unsubscribe(self, subscription: RulesetSubscription) -> None:
        environment_id = subscription.environment_id
        subscriptions = self._subscriptions.get(environment_id)
        if subscriptions is None:
            return
        subscriptions.discard(subscription)
        if not subscriptions:
            # Nobody here watches the environment any more, so the cached copy would only go
            # stale; the next stream to arrive builds a fresh one.
            del self._subscriptions[environment_id]
            self._published.pop(environment_id, None)
            self._building.pop(environment_id, None)


# Redis errors say what went wrong in one line; their tracebacks only ever show redis-py.
def _cause(error: Exception) -> str:
    return str(error.__cause__ or error)
