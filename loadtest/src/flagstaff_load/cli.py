import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx

from flagstaff_load.evaluation import measure_evaluation
from flagstaff_load.fanout import measure_fanout
from flagstaff_load.machine import describe_machine
from flagstaff_load.poll import PollSettings, measure_polling
from flagstaff_load.report import Results, render
from flagstaff_load.target import prepare


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.admin_key:
        sys.stderr.write("flagstaff-load: pass --admin-key or set FLAGSTAFF_LOAD_ADMIN_KEY\n")
        return 2
    report = render(asyncio.run(_run(args)))
    if args.output is None:
        sys.stdout.write(report)
    else:
        args.output.write_text(report, encoding="utf-8", newline="\n")
        _progress(f"wrote {args.output}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flagstaff-load",
        description="Measure a running Flagstaff stack and write the results as Markdown. Each"
        " run creates a project of its own, so it never touches anything else on the server.",
    )
    parser.add_argument(
        "--url", required=True, help="where the API answers, e.g. http://localhost:8080"
    )
    parser.add_argument(
        "--admin-key",
        default=os.environ.get("FLAGSTAFF_LOAD_ADMIN_KEY"),
        help="an admin key's secret (default: $FLAGSTAFF_LOAD_ADMIN_KEY)",
    )
    parser.add_argument("--flags", type=int, default=20, help="flags in the ruleset (default: 20)")
    parser.add_argument("--evaluation-seconds", type=float, default=3.0)
    parser.add_argument("--poll-seconds", type=float, default=10.0)
    parser.add_argument("--workers", type=int, default=4, help="polling processes (default: 4)")
    parser.add_argument(
        "--connections", type=int, default=10, help="connections per polling process (default: 10)"
    )
    parser.add_argument("--streams", type=int, default=1000, help="SDK streams (default: 1000)")
    parser.add_argument("--edits", type=int, default=20, help="edits to time (default: 20)")
    parser.add_argument("--output", type=Path, help="Markdown file to write instead of stdout")
    return parser


async def _run(args: argparse.Namespace) -> Results:
    url: str = args.url
    headers = {"Authorization": f"Bearer {args.admin_key}"}
    async with httpx.AsyncClient(base_url=url, headers=headers, timeout=30.0) as admin:
        _progress(f"creating a project with {args.flags} flags")
        target = await prepare(admin, flag_count=args.flags)

        _progress("evaluating flags in the SDK")
        evaluation = await measure_evaluation(url, target.sdk_key, seconds=args.evaluation_seconds)

        settings = PollSettings(args.workers, args.connections, args.poll_seconds)
        _progress("polling with the current ETag, then for whole rulesets")
        unchanged = await measure_polling(url, target.sdk_key, settings, revalidate=True)
        full = await measure_polling(url, target.sdk_key, settings, revalidate=False)

        _progress(f"opening {args.streams} streams and timing {args.edits} edits")
        fanout = await measure_fanout(url, admin, target, streams=args.streams, edits=args.edits)
    return Results(
        measured_on=datetime.now(UTC).date(),
        machine=describe_machine(),
        flags=args.flags,
        evaluation=evaluation,
        poll_settings=settings,
        unchanged=unchanged,
        full=full,
        fanout=fanout,
    )


def _progress(message: str) -> None:
    sys.stderr.write(f"flagstaff-load: {message}\n")
