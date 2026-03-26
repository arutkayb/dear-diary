#!/usr/bin/env python3
"""
extract.py — Extract Claude Code conversation transcripts from ~/.claude/projects/
for a given date and write one structured JSON file per day to ./output/.
"""

import argparse
import sys
from datetime import date, datetime, timedelta


def resolve_date(date_str: str | None) -> date:
    """Return the target date. Defaults to yesterday in host local TZ."""
    if date_str:
        return date.fromisoformat(date_str)
    local_now = datetime.now().astimezone()
    return (local_now - timedelta(days=1)).date()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Extract Claude Code conversation transcripts for a given date."
    )

    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Single date to extract (default: yesterday)",
    )
    date_group.add_argument(
        "--from",
        dest="from_date",
        metavar="YYYY-MM-DD",
        help="Start date of range (inclusive)",
    )

    parser.add_argument(
        "--to",
        metavar="YYYY-MM-DD",
        dest="to_date",
        help="End date of range (inclusive, requires --from)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print stats to stderr without writing files",
    )
    parser.add_argument(
        "--output-dir",
        default="./output",
        metavar="DIR",
        help="Output directory (default: ./output)",
    )
    parser.add_argument(
        "--source-dir",
        default=None,
        metavar="DIR",
        help="Claude storage directory (default: ~/.claude)",
    )

    args = parser.parse_args(argv)

    if args.to_date and not args.from_date:
        parser.error("--to requires --from")

    return args


def get_target_dates(args) -> list[date]:
    """Return the list of dates to process based on parsed args."""
    if args.from_date:
        start = date.fromisoformat(args.from_date)
        end = date.fromisoformat(args.to_date) if args.to_date else start
        if end < start:
            print("ERROR: --to date must be >= --from date", file=sys.stderr)
            sys.exit(1)
        result = []
        current = start
        while current <= end:
            result.append(current)
            current += timedelta(days=1)
        return result
    else:
        return [resolve_date(args.date)]


def main(argv=None):
    args = parse_args(argv)
    dates = get_target_dates(args)
    for d in dates:
        print(f"Extracting for: {d}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
