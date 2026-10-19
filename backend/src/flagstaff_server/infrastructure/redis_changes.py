import asyncio
import json
import logging
from collections.abc import AsyncIterator, Collection
from typing import Final
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from flagstaff_server.application.errors import ChangeFeedLostError
from flagstaff_server.application.rulesets import RulesetChange
from flagstaff_server.domain.ids import EnvironmentId

logger = logging.getLogger(__name__)

CHANNEL: Final = "flagstaff:ruleset-changes"
# A publish that takes longer than this is abandoned rather than holding up the API response
# for a change that has already committed.
_PUBLISH_TIMEOUT_SECONDS: Final = 2.0


# Pub/sub rather than a stream: a change only matters to instances listening right now, and an
# instance that missed some catches up from the database instead of replaying history.
class RedisRulesetChanges:
    def __init__(self, redis: Redis, *, channel: str = CHANNEL) -> None:
        self._redis = redis
        self._channel = channel

    async def announce(self, changes: Collection[RulesetChange]) -> None:
        if not changes:
            return
        try:
            async with asyncio.timeout(_PUBLISH_TIMEOUT_SECONDS):
                async with self._redis.pipeline(transaction=False) as pipeline:
                    for change in changes:
                        pipeline.publish(self._channel, _encode(change))
                    await pipeline.execute()
        except (RedisError, OSError, TimeoutError):
            logger.warning(
                "could not announce ruleset changes; streams will pick them up on resync",
                exc_info=True,
                extra={"environments": [str(change.environment_id) for change in changes]},
            )

    async def listen(self) -> AsyncIterator[RulesetChange]:
        pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
        try:
            await pubsub.subscribe(self._channel)
            async for message in pubsub.listen():
                change = _decode(message.get("data"))
                if change is not None:
                    yield change
        except (RedisError, OSError) as error:
            raise ChangeFeedLostError(f"lost the subscription to {self._channel}") from error
        finally:
            await pubsub.aclose()  # type: ignore[no-untyped-call]  # redis-py leaves it unannotated


def _encode(change: RulesetChange) -> str:
    return json.dumps({"environment_id": str(change.environment_id), "version": change.version})


# Anything else on the channel, such as a message from a newer server during a rolling deploy,
# is skipped rather than allowed to stop the listener.
def _decode(data: object) -> RulesetChange | None:
    change = _parse(data) if isinstance(data, str | bytes) else None
    if change is None:
        logger.warning("skipped a malformed ruleset change", extra={"payload": repr(data)})
    return change


def _parse(data: str | bytes) -> RulesetChange | None:
    try:
        payload = json.loads(data)
        environment_id = EnvironmentId(UUID(payload["environment_id"]))
        version = payload["version"]
    except (TypeError, ValueError, KeyError):
        return None
    if isinstance(version, bool) or not isinstance(version, int):
        return None
    return RulesetChange(environment_id, version)
