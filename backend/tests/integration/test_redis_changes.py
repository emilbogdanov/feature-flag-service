import asyncio
import logging
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from flagstaff_server.application.errors import ChangeFeedLostError
from flagstaff_server.application.rulesets import RulesetChange
from flagstaff_server.domain.ids import EnvironmentId
from flagstaff_server.infrastructure.redis_changes import CHANNEL, RedisRulesetChanges

PROD = EnvironmentId(uuid4())
DEV = EnvironmentId(uuid4())


async def first(feed: AsyncIterator[RulesetChange], count: int) -> list[RulesetChange]:
    received = []
    async for change in feed:
        received.append(change)
        if len(received) == count:
            break
    return received


async def until_subscribed(redis: Redis, listeners: int) -> None:
    async with asyncio.timeout(5):
        while dict(await redis.pubsub_numsub(CHANNEL)).get(CHANNEL.encode(), 0) < listeners:
            await asyncio.sleep(0.01)


async def test_every_listening_instance_hears_every_change(redis_url: str, redis: Redis) -> None:
    # One client per instance, as two API processes would have.
    instances = [Redis.from_url(redis_url) for _ in range(2)]
    feeds = [RedisRulesetChanges(client) for client in instances]
    listening = [asyncio.create_task(first(feed.listen(), 2)) for feed in feeds]
    await until_subscribed(redis, 2)

    await RedisRulesetChanges(redis).announce([RulesetChange(PROD, 7), RulesetChange(DEV, 3)])

    async with asyncio.timeout(5):
        heard = await asyncio.gather(*listening)
    assert heard == [[RulesetChange(PROD, 7), RulesetChange(DEV, 3)]] * 2
    for client in instances:
        await client.aclose()


async def test_skips_messages_it_cannot_read(redis: Redis, redis_url: str) -> None:
    listener = Redis.from_url(redis_url)
    listening = asyncio.create_task(first(RedisRulesetChanges(listener).listen(), 1))
    await until_subscribed(redis, 1)

    await redis.publish(CHANNEL, "not json")
    await redis.publish(CHANNEL, '{"environment_id": "prod", "version": 7}')
    await redis.publish(CHANNEL, f'{{"environment_id": "{PROD}", "version": true}}')
    await RedisRulesetChanges(redis).announce([RulesetChange(PROD, 8)])

    async with asyncio.timeout(5):
        assert await listening == [RulesetChange(PROD, 8)]
    await listener.aclose()


async def test_a_dropped_connection_ends_the_feed_with_a_clear_error(
    redis: Redis, redis_url: str
) -> None:
    listener = Redis.from_url(redis_url)
    listening = asyncio.create_task(first(RedisRulesetChanges(listener).listen(), 1))
    await until_subscribed(redis, 1)

    await redis.client_kill_filter(_type="pubsub")

    with pytest.raises(ChangeFeedLostError):
        async with asyncio.timeout(5):
            await listening
    await listener.aclose()


async def test_announcing_without_redis_logs_instead_of_failing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    unreachable = Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.5)

    with caplog.at_level(logging.WARNING):
        await RedisRulesetChanges(unreachable).announce([RulesetChange(PROD, 7)])

    assert "could not announce ruleset changes" in caplog.text
    await unreachable.aclose()
