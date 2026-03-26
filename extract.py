#!/usr/bin/env python3
"""
extract.py — Extract Claude Code conversation transcripts from ~/.claude/projects/
for a given date and write one structured JSON file per day to ./output/.
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone


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


def discover_sessions(source_dir: str) -> list[dict]:
    """Scan source_dir/projects/*/*.jsonl and return session metadata dicts.

    Each entry: {file_path, session_id, project_dir}
    """
    projects_dir = os.path.join(source_dir, "projects")
    sessions = []
    try:
        project_entries = os.scandir(projects_dir)
    except FileNotFoundError:
        print(f"ERROR: source directory not found: {projects_dir}", file=sys.stderr)
        sys.exit(1)
    except PermissionError as e:
        print(f"ERROR: permission denied accessing {projects_dir}: {e}", file=sys.stderr)
        sys.exit(1)

    for project_entry in project_entries:
        if not project_entry.is_dir():
            continue
        try:
            for file_entry in os.scandir(project_entry.path):
                if file_entry.is_file() and file_entry.name.endswith(".jsonl"):
                    session_id = file_entry.name[:-6]  # strip .jsonl
                    sessions.append({
                        "file_path": file_entry.path,
                        "session_id": session_id,
                        "project_dir": project_entry.name,
                    })
        except PermissionError as e:
            print(f"WARNING: permission denied scanning {project_entry.path}: {e}", file=sys.stderr)

    return sessions


def build_empty_output(target_date: date) -> dict:
    """Build the output JSON structure with zero stats and empty projects list."""
    now = datetime.now().astimezone()
    return {
        "date": target_date.isoformat(),
        "extracted_at": now.isoformat(),
        "stats": {
            "session_count": 0,
            "project_count": 0,
            "message_count": 0,
            "estimated_tokens": 0,
        },
        "projects": [],
    }


def write_output(data: dict, output_dir: str, target_date: date) -> str:
    """Write output JSON to output_dir/YYYY-MM-DD.json. Returns the file path."""
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{target_date.isoformat()}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return out_path


def main(argv=None):
    args = parse_args(argv)
    dates = get_target_dates(args)
    for d in dates:
        print(f"Extracting for: {d}", file=sys.stderr)
        data = build_empty_output(d)
        out_path = write_output(data, args.output_dir, d)
        print(f"Written: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
