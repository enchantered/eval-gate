"""Command-line interface."""
import argparse
import asyncio
import json
import math
import sys

from .core import FixtureError, evaluate, load_fixture


def _positive_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not math.isfinite(number) or not 0.001 <= number <= 30:
        raise argparse.ArgumentTypeError("must be finite and between 0.001 and 30 seconds")
    return number


def _bounded_int(low: int, high: int):
    def parse(value: str) -> int:
        try:
            number = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("must be an integer") from exc
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f"must be between {low} and {high}")
        return number
    return parse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline scripted fixture evaluation gate")
    parser.add_argument("command", choices=["run"])
    parser.add_argument("fixture")
    parser.add_argument("--concurrency", type=_bounded_int(1, 32), default=4)
    parser.add_argument("--timeout", type=_positive_float, default=5.0)
    parser.add_argument("--retries", type=_bounded_int(0, 3), default=0)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    try:
        fixture = load_fixture(args.fixture)
    except FixtureError as exc:
        print(f"fixture error: {exc}", file=sys.stderr)
        return 2
    report = asyncio.run(evaluate(fixture, concurrency=args.concurrency,
                                  timeout=args.timeout, retries=args.retries))
    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    else:
        for row in report["cases"]:
            print(f"{row['case_id']}: {row['status']} ({row['attempts']} attempt(s), {row['duration_ms']} ms)")
        summary = report["summary"]
        print(f"Valid: {summary['valid_count']}  Failed: {summary['failed_count']}  Peak active: {summary['peak_active_attempts']}")
    return 0 if report["summary"]["failed_count"] == 0 else 1
