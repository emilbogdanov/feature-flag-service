import io
import json
import logging
from uuid import UUID

import pytest

from flagstaff_server.infrastructure.logs import (
    configure_logging,
    log_context,
)

ENVIRONMENT_ID = UUID("5f0c6f0e-3a51-4c3e-9a3b-1f2d1c4b7e90")


pytestmark = pytest.mark.usefixtures("restore_logging")


@pytest.fixture
def output() -> io.StringIO:
    return io.StringIO()


def log_lines(output: io.StringIO) -> list[str]:
    return output.getvalue().splitlines()


def json_lines(output: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in log_lines(output)]


def test_writes_one_json_object_per_record(output: io.StringIO) -> None:
    configure_logging("INFO", "json", stream=output)

    logging.getLogger("flagstaff_server.live").warning(
        "lost %s", "the feed", extra={"environment_id": ENVIRONMENT_ID, "version": 7}
    )

    [entry] = json_lines(output)
    assert entry.pop("time")
    assert entry == {
        "level": "warning",
        "logger": "flagstaff_server.live",
        "message": "lost the feed",
        "environment_id": str(ENVIRONMENT_ID),
        "version": 7,
    }


def test_keeps_the_traceback_inside_the_json_line(output: io.StringIO) -> None:
    configure_logging("INFO", "json", stream=output)

    try:
        _ = 1 / 0
    except ZeroDivisionError:
        logging.getLogger("flagstaff_server").exception("resync failed")

    [line] = log_lines(output)
    assert "ZeroDivisionError" in str(json.loads(line)["exception"])


def test_stamps_bound_fields_on_every_record_until_the_context_ends(
    output: io.StringIO,
) -> None:
    configure_logging("INFO", "json", stream=output)
    logger = logging.getLogger("flagstaff_server")

    with log_context(request_id="r-1"):
        logger.info("outer")
        with log_context(environment="prod"):
            logger.info("inner")
        logger.info("named", extra={"request_id": "explicit"})
    logger.info("after")

    assert [
        (entry["message"], entry.get("request_id"), entry.get("environment"))
        for entry in json_lines(output)
    ] == [
        ("outer", "r-1", None),
        ("inner", "r-1", "prod"),
        ("named", "explicit", None),
        ("after", None, None),
    ]


def test_writes_fields_after_the_message_as_text(output: io.StringIO) -> None:
    configure_logging("INFO", "text", stream=output)

    with log_context(request_id="r-1"):
        logging.getLogger("flagstaff_server").info("request finished", extra={"status": 200})

    [line] = log_lines(output)
    assert line.endswith("INFO    flagstaff_server: request finished status=200 request_id=r-1")


def test_leaves_out_records_below_the_level(output: io.StringIO) -> None:
    configure_logging("WARNING", "json", stream=output)

    logging.getLogger("flagstaff_server").info("quiet")
    logging.getLogger("flagstaff_server").warning("loud")

    assert [entry["message"] for entry in json_lines(output)] == ["loud"]


def test_routes_uvicorn_server_messages_through_the_same_handler(
    output: io.StringIO,
) -> None:
    # What uvicorn has set up by the time it loads the app.
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.addHandler(logging.NullHandler())
    uvicorn_logger.propagate = False

    configure_logging("INFO", "json", stream=output)
    logging.getLogger("uvicorn.error").info(
        "Started server process", extra={"color_message": "\x1b[36mStarted\x1b[0m"}
    )
    logging.getLogger("uvicorn.access").info("GET / 200")

    [entry] = json_lines(output)
    assert (entry["logger"], entry["message"]) == ("uvicorn.error", "Started server process")
    assert "color_message" not in entry
