from __future__ import annotations

import json
import logging
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, Literal, TextIO, override

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

type LogFormat = Literal["json", "text"]

# Fields bound for the unit of work running now, a request say, and stamped on every record
# logged while it runs, whichever module logs it.
_bound_fields: ContextVar[Mapping[str, object] | None] = ContextVar("log_fields", default=None)

# Whatever else a record carries came from extra= or a bound field. uvicorn attaches an
# ANSI-coloured copy of its message as color_message, which is no use outside a terminal.
_NOT_FIELDS: Final = frozenset(vars(logging.makeLogRecord({}))) | {
    "message",
    "asctime",
    "color_message",
}


@contextmanager
def log_context(**fields: object) -> Iterator[None]:
    token = _bound_fields.set({**(_bound_fields.get() or {}), **fields})
    try:
        yield
    finally:
        _bound_fields.reset(token)


class _BoundFieldsFilter(logging.Filter):
    @override
    def filter(self, record: logging.LogRecord) -> bool:
        for name, value in (_bound_fields.get() or {}).items():
            # A field passed in extra= says more about this one record than the bound one.
            record.__dict__.setdefault(name, value)
        return True


def _fields(record: logging.LogRecord) -> dict[str, object]:
    return {
        name: value
        for name, value in vars(record).items()
        if name not in _NOT_FIELDS and not name.startswith("_")
    }


# One JSON object per line, so a log shipper needs no parsing rules for this service.
class JsonFormatter(logging.Formatter):
    @override
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for name, value in _fields(record).items():
            entry.setdefault(name, value)
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            entry["stack"] = self.formatStack(record.stack_info)
        # A UUID or a datetime passed in extra= is logged as text rather than failing the line.
        return json.dumps(entry, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    @override
    def formatMessage(self, record: logging.LogRecord) -> str:
        fields = "".join(f" {name}={value}" for name, value in _fields(record).items())
        return super().formatMessage(record) + fields


def configure_logging(level: str, log_format: LogFormat, *, stream: TextIO | None = None) -> None:
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter() if log_format == "json" else TextFormatter())
    handler.addFilter(_BoundFieldsFilter())
    logging.basicConfig(level=level, handlers=[handler], force=True)

    # uvicorn sets up its own loggers before it loads the app. Its server messages go through
    # the same handler and level as everything else.
    for name in ("uvicorn", "uvicorn.error"):
        server_logger = logging.getLogger(name)
        server_logger.handlers.clear()
        server_logger.setLevel(logging.NOTSET)
        server_logger.propagate = True
    # The API logs each request itself, with its id and duration, in place of this line.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False
    access_logger.disabled = True
