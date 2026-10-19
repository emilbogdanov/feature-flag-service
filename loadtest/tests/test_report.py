from datetime import date

from flagstaff_load.evaluation import EvaluationResult
from flagstaff_load.fanout import FanoutResult
from flagstaff_load.machine import Machine
from flagstaff_load.poll import PollResult, PollSettings
from flagstaff_load.report import Results, render
from flagstaff_load.stats import Summary


def latencies(*milliseconds: float) -> Summary:
    return Summary.of([ms / 1000 for ms in milliseconds])


RESULTS = Results(
    measured_on=date(2026, 10, 19),
    machine=Machine(
        os="Windows-11",
        cpu="AMD Ryzen 7 7840HS",
        logical_cores=16,
        python="3.13.9",
        docker="29.0.1, with 16 CPUs and 15.6 GiB for containers",
    ),
    flags=20,
    evaluation=EvaluationResult(calls=1_200_000, seconds=3.0),
    poll_settings=PollSettings(workers=4, connections=10, seconds=10.0),
    unchanged=PollResult(
        seconds=10.0, latency=latencies(*[4.0] * 30_000), statuses={304: 30_000}, errors=0
    ),
    full=PollResult(
        seconds=10.0, latency=latencies(*[8.5] * 15_000), statuses={200: 15_000}, errors=0
    ),
    fanout=FanoutResult(
        streams=1000,
        edits=20,
        open_seconds=2.25,
        delivery=latencies(12.0, 20.0, 35.0),
        last_delivery=latencies(35.0),
    ),
)


def test_reports_each_measurement_in_its_own_section() -> None:
    report = render(RESULTS)

    assert "- **400,000 evaluations a second**, 2.5 µs each" in report
    assert (
        "| Rules unchanged, answered `304` | 3,000 | 4.0 ms | 4.0 ms | 4.0 ms | 4.0 ms | 0 |"
        in report
    )
    assert "| Whole ruleset, answered `200` | 1,500 | 8.5 ms |" in report
    assert "| Each stream | 20.0 ms | 35.0 ms | 35.0 ms | 35.0 ms |" in report
    assert "Opening all 1,000 streams, each with its first ruleset, took 2.2 s." in report
    assert "| CPU | AMD Ryzen 7 7840HS, 16 logical cores |" in report


def test_is_clean_markdown_for_the_repository() -> None:
    report = render(RESULTS)

    assert report.endswith("\n")
    assert not report.endswith("\n\n")
    assert all(line == line.rstrip() for line in report.splitlines())
