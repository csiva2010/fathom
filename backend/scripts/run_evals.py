"""Run the evaluation golden sets (INN-02) and write a Markdown + JSON report.

    python -m scripts.run_evals                          # offline: what CI checks
    python -m scripts.run_evals --live                   # real retrieval, LLMs, LLM judge
    python -m scripts.run_evals --live --suite answers --case ans-01 ans-04 --pause 4

Offline needs no keys and is deterministic. Live uses backend/.env and calls the configured
models (about 150 calls for every suite); `--pause` spaces calls out for free-tier limits.
Reports go to var/evals/ by default. `--gate` exits 1 if an offline metric is below its
floor (tests/eval/harness.py OFFLINE_FLOORS).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path

import httpx

from src.core.config import get_settings, resolve_path
from src.core.tracing import configure_langsmith
from tests.eval.harness import OFFLINE_FLOORS, SUITES, build_system, run_suites, write_reports


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--suite", nargs="+", choices=SUITES, default=list(SUITES))
    parser.add_argument("--live", action="store_true", help="use the real models and data")
    parser.add_argument("--no-judge", action="store_true", help="skip the faithfulness judge")
    parser.add_argument("--case", nargs="+", default=None, help="only these case ids")
    parser.add_argument("--pause", type=float, default=0.0, help="seconds between cases")
    parser.add_argument("--out", default="var/evals", help="report directory")
    parser.add_argument("--gate", action="store_true", help="fail below the offline floors")
    return parser.parse_args(argv)


async def run(args: argparse.Namespace) -> int:
    async def pause() -> None:
        await asyncio.sleep(args.pause)

    if args.live and (project := configure_langsmith(get_settings(), "-evals")):
        print(f"LangSmith tracing to project {project}")

    with tempfile.TemporaryDirectory() as scratch:
        async with httpx.AsyncClient() as client:
            system = build_system(args.live, Path(scratch), client, judge=not args.no_judge)
            reports = await run_suites(
                system, args.suite, case_ids=args.case, pause=pause if args.pause else None
            )

    markdown, raw = write_reports(reports, resolve_path(args.out))
    for report in reports:
        print(report.to_markdown())
    print(f"Report: {markdown}\nRaw results: {raw}")

    if args.gate and not args.live:
        below = {
            report.suite: missed
            for report in reports
            if (missed := report.below_floor(OFFLINE_FLOORS[report.suite]))
        }
        if below:
            print(f"Below the offline floors: {below}", file=sys.stderr)
            return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
