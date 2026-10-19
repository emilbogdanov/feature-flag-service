import logging
from collections.abc import Iterator

import pytest

# configure_logging replaces the root handlers and rewires uvicorn's loggers for the whole
# process; tests that call it put everything back afterwards.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


@pytest.fixture
def restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    saved_root = (root.handlers[:], root.level)
    saved = {
        name: (logger.handlers[:], logger.level, logger.propagate, logger.disabled)
        for name in _UVICORN_LOGGERS
        for logger in [logging.getLogger(name)]
    }
    yield
    root.handlers[:], root.level = saved_root
    for name, (handlers, level, propagate, disabled) in saved.items():
        logger = logging.getLogger(name)
        logger.handlers[:], logger.level = handlers, level
        logger.propagate, logger.disabled = propagate, disabled
