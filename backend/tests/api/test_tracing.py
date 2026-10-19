import io
import json
import logging
import re
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from flagstaff_server.api.app import create_app
from flagstaff_server.api.container import Container
from flagstaff_server.infrastructure.logs import configure_logging

pytestmark = pytest.mark.usefixtures("restore_logging")

GENERATED_ID = re.compile(r"[0-9a-f]{32}")


@pytest.fixture
def output() -> io.StringIO:
    return io.StringIO()


@pytest.fixture
async def http(container: Container, output: io.StringIO) -> AsyncIterator[AsyncClient]:
    app = create_app(container)

    async def crash() -> None:
        logging.getLogger("flagstaff_server.application").info("about to fail")
        raise RuntimeError("a bug")

    app.add_api_route("/crash", crash)
    configure_logging("INFO", "json", stream=output)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://flagstaff.test") as client:
        yield client


# The server's own lines, without the test client's.
def logged(output: io.StringIO) -> list[dict[str, object]]:
    entries = [json.loads(line) for line in output.getvalue().splitlines()]
    return [entry for entry in entries if str(entry["logger"]).startswith("flagstaff_server")]


async def test_gives_every_response_a_request_id(http: AsyncClient) -> None:
    first, second = await http.get("/projects"), await http.get("/projects")

    assert GENERATED_ID.fullmatch(first.headers["X-Request-ID"])
    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]


async def test_keeps_the_callers_request_id(http: AsyncClient) -> None:
    response = await http.get("/projects", headers={"X-Request-ID": "gateway-7f3a.12"})

    assert response.headers["X-Request-ID"] == "gateway-7f3a.12"


@pytest.mark.parametrize("offered", ["", "two words", "x" * 129, "id;drop"])
async def test_replaces_a_request_id_unfit_for_logs(http: AsyncClient, offered: str) -> None:
    response = await http.get("/projects", headers={"X-Request-ID": offered})

    assert GENERATED_ID.fullmatch(response.headers["X-Request-ID"])


async def test_logs_one_line_per_request_with_its_id(
    http: AsyncClient, output: io.StringIO
) -> None:
    response = await http.get("/projects", headers={"X-Request-ID": "r-1"})

    [entry] = logged(output)
    assert entry.pop("time")
    assert isinstance(entry.pop("duration_ms"), float)
    assert entry == {
        "level": "info",
        "logger": "flagstaff_server.requests",
        "message": "request finished",
        "method": "GET",
        "path": "/projects",
        "status": response.status_code,
        "request_id": "r-1",
    }


async def test_logs_a_crash_with_the_id_of_the_request_that_caused_it(
    http: AsyncClient, output: io.StringIO
) -> None:
    response = await http.get("/crash", headers={"X-Request-ID": "r-2"})

    assert response.status_code == 500
    assert response.json() == {"detail": "internal error", "code": "internal"}
    assert response.headers["X-Request-ID"] == "r-2"
    app_line, crash, finished = logged(output)
    assert (app_line["message"], app_line["request_id"]) == ("about to fail", "r-2")
    assert (crash["message"], crash["request_id"]) == ("unhandled error", "r-2")
    assert "RuntimeError: a bug" in str(crash["exception"])
    assert (finished["status"], finished["request_id"]) == (500, "r-2")


async def test_keeps_health_probes_out_of_the_info_log(
    http: AsyncClient, output: io.StringIO
) -> None:
    await http.get("/health")

    assert logged(output) == []
