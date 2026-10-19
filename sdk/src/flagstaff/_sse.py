from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ServerSentEvent:
    event: str
    data: str
    id: str | None


# Follows the WHATWG event-stream rules rather than whatever the server happens to send today:
# data lines are joined with newlines, comments are dropped, a blank line dispatches, the last
# id carries over to later events, and a block without data dispatches nothing.
class SseDecoder:
    def __init__(self) -> None:
        self._event = ""
        self._data: list[str] = []
        self._last_id: str | None = None
        self.retry_ms: int | None = None

    def feed(self, line: str) -> ServerSentEvent | None:
        if not line:
            return self._dispatch()
        if line.startswith(":"):
            return None
        name, colon, value = line.partition(":")
        if colon:
            value = value.removeprefix(" ")
        if name == "data":
            self._data.append(value)
        elif name == "event":
            self._event = value
        elif name == "id" and "\0" not in value:
            self._last_id = value
        elif name == "retry" and value.isdigit():
            self.retry_ms = int(value)
        return None

    def _dispatch(self) -> ServerSentEvent | None:
        event, data = self._event or "message", self._data
        self._event, self._data = "", []
        if not data:
            return None
        return ServerSentEvent(event, "\n".join(data), self._last_id)
