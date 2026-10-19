import asyncio
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse

from flagstaff_server.api.dependencies import ContainerDep, SdkEnvironment
from flagstaff_server.api.errors import error_responses
from flagstaff_server.application.live import RulesetBroadcaster, StreamClosedError
from flagstaff_server.domain.ids import EnvironmentId

router = APIRouter(tags=["rulesets"], responses=error_responses(401, 403))

_STREAM: dict[int | str, dict[str, Any]] = {
    200: {
        "content": {"text/event-stream": {}},
        "description": (
            "Server-sent events. Each `ruleset` event carries the whole ruleset document, with"
            " its version as the event id; comment lines are keep-alives."
        ),
    }
}
# What an SSE client waits before reconnecting after the connection drops, in milliseconds.
_RECONNECT_AFTER_MS = 1_000


@router.get("/sdk/stream", response_class=StreamingResponse, responses=_STREAM)
async def sdk_stream(
    environment: SdkEnvironment,
    container: ContainerDep,
    last_event_id: Annotated[
        str | None,
        Header(description="The version the SDK already holds; it isn't sent again."),
    ] = None,
) -> StreamingResponse:
    events = _events(
        container.broadcaster,
        environment,
        known_version=_version(last_event_id),
        heartbeat_seconds=container.stream_heartbeat_seconds,
    )
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        # X-Accel-Buffering stops nginx from holding events back until its buffer fills.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _events(
    broadcaster: RulesetBroadcaster,
    environment_id: EnvironmentId,
    *,
    known_version: int | None,
    heartbeat_seconds: float,
) -> AsyncIterator[str]:
    yield f"retry: {_RECONNECT_AFTER_MS}\n\n"
    async with broadcaster.subscribe(environment_id, known_version=known_version) as subscription:
        while True:
            try:
                async with asyncio.timeout(heartbeat_seconds):
                    ruleset = await subscription.next()
            except TimeoutError:
                # A comment line: clients ignore it, proxies see a connection that is alive.
                yield ": keep-alive\n\n"
                continue
            except StreamClosedError:
                return
            # The document is compact JSON, so it always fits on the one data line.
            yield f"id: {ruleset.version}\nevent: ruleset\ndata: {ruleset.document}\n\n"


# Anything that isn't a version, such as an id from some other event source, is ignored and the
# client simply gets the current rules.
def _version(last_event_id: str | None) -> int | None:
    if last_event_id is None or not last_event_id.strip().isdigit():
        return None
    return int(last_event_id.strip())
