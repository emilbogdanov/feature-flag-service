import pytest

from flagstaff._sse import ServerSentEvent, SseDecoder


def decode(*lines: str) -> list[ServerSentEvent]:
    decoder = SseDecoder()
    return [event for line in lines if (event := decoder.feed(line)) is not None]


def test_decodes_the_events_the_server_sends() -> None:
    events = decode(
        "retry: 1000",
        "",
        "id: 7",
        "event: ruleset",
        'data: {"format":1,"version":7,"flags":[]}',
        "",
        ": keep-alive",
        "",
    )

    assert events == [ServerSentEvent("ruleset", '{"format":1,"version":7,"flags":[]}', "7")]


def test_remembers_the_reconnect_delay() -> None:
    decoder = SseDecoder()

    decoder.feed("retry: 2500")

    assert decoder.retry_ms == 2500


def test_joins_multi_line_data_with_newlines() -> None:
    assert decode("data: first", "data: second", "") == [
        ServerSentEvent("message", "first\nsecond", None)
    ]


def test_an_id_carries_over_to_later_events() -> None:
    events = decode("id: 3", "data: a", "", "data: b", "")

    assert [event.id for event in events] == ["3", "3"]


@pytest.mark.parametrize(
    "lines",
    [
        (": keep-alive", ""),
        ("event: ruleset", ""),
        ("id: 9", ""),
    ],
    ids=["comment", "event without data", "id without data"],
)
def test_a_block_without_data_dispatches_nothing(lines: tuple[str, ...]) -> None:
    assert decode(*lines) == []


def test_a_field_without_a_colon_has_an_empty_value() -> None:
    assert decode("data", "") == [ServerSentEvent("message", "", None)]


def test_ignores_fields_it_does_not_know_and_malformed_retries() -> None:
    decoder = SseDecoder()

    events = [decoder.feed(line) for line in ("colour: blue", "retry: soon", "data: x", "")]

    assert events[-1] == ServerSentEvent("message", "x", None)
    assert decoder.retry_ms is None
