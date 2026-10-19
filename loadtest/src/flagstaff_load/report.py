from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

    from flagstaff_load.evaluation import EvaluationResult
    from flagstaff_load.fanout import FanoutResult
    from flagstaff_load.machine import Machine
    from flagstaff_load.poll import PollResult, PollSettings
    from flagstaff_load.stats import Summary


@dataclass(frozen=True, slots=True)
class Results:
    measured_on: date
    machine: Machine
    flags: int
    evaluation: EvaluationResult
    poll_settings: PollSettings
    unchanged: PollResult
    full: PollResult
    fanout: FanoutResult


def render(results: Results) -> str:
    machine = results.machine
    evaluation = results.evaluation
    poll = results.poll_settings
    fanout = results.fanout
    lines = [
        "# Load test results",
        "",
        f"Measured on {results.measured_on.isoformat()} by `flagstaff-load` against the"
        " stack in [compose.yaml](../compose.yaml): nginx in front of two API instances,"
        " Postgres and Redis. The load came from the same machine, so it competed with the stack"
        " for the same cores.",
        "",
        "| Machine | |",
        "| --- | --- |",
        f"| OS | {machine.os} |",
        f"| CPU | {machine.cpu}, {machine.logical_cores} logical cores |",
        f"| Docker | {machine.docker} |",
        f"| Python running the load | {machine.python} |",
        "",
        "## Evaluating a flag in the app",
        "",
        "An SDK holds its environment's rules in memory, so checking a flag never leaves the"
        " process. `bool_value` on a flag with a user-list rule and a two-condition attribute"
        " rule served by a 25% rollout, for a spread of users, on one thread:",
        "",
        f"- **{_count(evaluation.calls_per_second)} evaluations a second**,"
        f" {evaluation.microseconds_per_call:.1f} µs each",
        "",
        "## Polling for rules",
        "",
        "`GET /sdk/ruleset` through nginx, from"
        f" {poll.workers} processes with {poll.connections} connections each, for"
        f" {poll.seconds:.0f} s per row. The ruleset holds {results.flags} flags.",
        "",
        "| | Requests a second | p50 | p95 | p99 | Max | Errors |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        _poll_row("Rules unchanged, answered `304`", results.unchanged),
        _poll_row("Whole ruleset, answered `200`", results.full),
        "",
        "## Pushing an edit to open streams",
        "",
        f"{fanout.streams:,} SDK streams open through nginx, spread over both instances, and"
        f" {fanout.edits} edits made one at a time through the admin API, each landing on"
        " whichever instance nginx picked and reaching the other through Redis. Time from"
        " sending the edit to a stream having the new ruleset:",
        "",
        "| | p50 | p95 | p99 | Max |",
        "| --- | --- | --- | --- | --- |",
        _latency_row("Each stream", fanout.delivery),
        _latency_row("Last stream to get each edit", fanout.last_delivery),
        "",
        f"Opening all {fanout.streams:,} streams, each with its first ruleset, took"
        f" {fanout.open_seconds:.1f} s.",
        "",
    ]
    return "\n".join(lines)


def _poll_row(label: str, result: PollResult) -> str:
    latency = result.latency
    return (
        f"| {label} | {_count(result.requests_per_second)} | {_ms(latency.p50)}"
        f" | {_ms(latency.p95)} | {_ms(latency.p99)} | {_ms(latency.max)} | {result.errors} |"
    )


def _latency_row(label: str, summary: Summary) -> str:
    return (
        f"| {label} | {_ms(summary.p50)} | {_ms(summary.p95)} | {_ms(summary.p99)}"
        f" | {_ms(summary.max)} |"
    )


def _ms(seconds: float) -> str:
    return f"{seconds * 1000:.1f} ms"


def _count(per_second: float) -> str:
    return f"{per_second:,.0f}"
