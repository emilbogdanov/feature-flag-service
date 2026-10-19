from collections.abc import Iterator
from typing import Final, override

from prometheus_client import (
    CollectorRegistry,
    Counter,
    GCCollector,
    Histogram,
    PlatformCollector,
    ProcessCollector,
    disable_created_metrics,
    generate_latest,
)
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from prometheus_client.metrics_core import Metric
from prometheus_client.registry import Collector

from flagstaff_server.application.live import RulesetBroadcaster

# Any other method, a scanner's invented one say, is counted as OTHER rather than adding series.
_KNOWN_METHODS: Final = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
# Requests for paths no route serves share one label instead of one series per path tried.
UNMATCHED_ROUTE: Final = "unmatched"
# Most answers take a few milliseconds, below the default buckets' 5 ms floor.
_DURATION_BUCKETS: Final = (0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)

# A _created timestamp beside every counter and histogram doubles the series and nothing reads it.
disable_created_metrics()  # type: ignore[no-untyped-call]  # unannotated in prometheus_client


# Each instance is scraped on its own and runs one worker process, so plain in-memory metrics
# are enough; prometheus_client's multiprocess mode would only be needed with several workers.
class Metrics:
    def __init__(self) -> None:
        # Not the process-wide default registry, so every app built, in tests say, starts at zero.
        self.registry = CollectorRegistry()
        ProcessCollector(registry=self.registry)
        PlatformCollector(registry=self.registry)
        GCCollector(registry=self.registry)
        self._requests = Counter(
            "flagstaff_http_requests",
            "HTTP requests answered, by method, route and status.",
            ["method", "route", "status"],
            registry=self.registry,
        )
        self._durations = Histogram(
            "flagstaff_http_request_duration_seconds",
            "Time taken to answer an HTTP request. SDK streams are left out: they last as long"
            " as the SDK stays connected.",
            ["method", "route"],
            buckets=_DURATION_BUCKETS,
            registry=self.registry,
        )

    def observe_request(
        self, *, method: str, route: str | None, status: int, seconds: float | None
    ) -> None:
        method = method if method in _KNOWN_METHODS else "OTHER"
        route = route or UNMATCHED_ROUTE
        self._requests.labels(method, route, str(status)).inc()
        if seconds is not None:
            self._durations.labels(method, route).observe(seconds)

    def watch(self, broadcaster: RulesetBroadcaster) -> None:
        self.registry.register(_BroadcasterCollector(broadcaster))

    def exposition(self) -> bytes:
        return generate_latest(self.registry)


# Reads the broadcaster's totals at scrape time, so the application layer keeps plain counters
# and never imports prometheus_client.
class _BroadcasterCollector(Collector):
    def __init__(self, broadcaster: RulesetBroadcaster) -> None:
        self._broadcaster = broadcaster

    @override
    def collect(self) -> Iterator[Metric]:
        stats = self._broadcaster.stats
        yield GaugeMetricFamily(
            "flagstaff_sdk_streams",
            "SDK streams open on this instance.",
            value=self._broadcaster.stream_count,
        )
        yield CounterMetricFamily(
            "flagstaff_rulesets_built",
            "Rulesets built for SDK streams: one per environment and version, however many"
            " streams send it.",
            value=stats.rulesets_built,
        )
        yield CounterMetricFamily(
            "flagstaff_change_feed_interruptions",
            "Times the Redis change feed dropped or failed to subscribe. While it is down,"
            " streams only catch up on resync.",
            value=stats.feed_interruptions,
        )
        yield CounterMetricFamily(
            "flagstaff_ruleset_load_failures",
            "Rulesets the database couldn't supply for streams, left for the next resync.",
            value=stats.load_failures,
        )
