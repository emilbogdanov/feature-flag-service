from datetime import UTC

from flagstaff_server.infrastructure.clock import SystemClock


# Naive datetimes would be read back from timestamptz columns as UTC whatever they meant.
def test_tells_the_time_in_utc() -> None:
    assert SystemClock().now().tzinfo is UTC
