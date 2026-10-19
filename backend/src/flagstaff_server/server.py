import socket
from collections.abc import Callable
from typing import override

import uvicorn


# uvicorn waits for every open connection to finish before it runs the app's shutdown, and an
# SDK stream never finishes by itself: each instance would hold its streams until the graceful
# timeout ran out, then cut them. Ending them as shutdown begins sends every SDK to reconnect,
# through the proxy, to an instance that is staying up, straight away.
class DrainingServer(uvicorn.Server):
    def __init__(self, config: uvicorn.Config, *, end_streams: Callable[[], None]) -> None:
        super().__init__(config)
        self._end_streams = end_streams

    @override
    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        self._end_streams()
        await super().shutdown(sockets)
