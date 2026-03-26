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


def _get_session_last_timestamp(file_path: str) -> datetime | None:
    """Return the timestamp of the last message with a timestamp field."""
    last_ts = None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_str = msg.get("timestamp")
                if ts_str:
                    try:
                        last_ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    except ValueError:
                        pass
    except (OSError, PermissionError) as e:
        print(f"WARNING: could not read {file_path}: {e}", file=sys.stderr)
    return last_ts


def filter_sessions_by_date(
    sessions: list[dict], target_date: date, local_tz
) -> list[dict]:
    """Return sessions whose last-activity date (in local TZ) matches target_date."""
    matched = []
    for session in sessions:
        last_ts = _get_session_last_timestamp(session["file_path"])
        if last_ts is None:
            continue
        local_dt = last_ts.astimezone(local_tz)
        if local_dt.date() == target_date:
            matched.append(session)
    return matched


_SKIP_TYPES = frozenset({
    "tool_use", "tool_result", "thinking",
    "file-history-snapshot", "progress", "last-prompt",
})


def _extract_text_blocks(content) -> str | None:
    """Extract and join text from content (str or list of blocks). Returns None if no text."""
    if isinstance(content, str):
        text = content.strip()
        return text if text else None
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "").strip()
                if text:
                    parts.append(text)
        return "\n".join(parts) if parts else None
    return None


def extract_messages(session_file: str):
    """Parse JSONL line-by-line, yielding {role, text, timestamp, cwd, git_branch}.

    Skips:
    - Messages where isMeta is truthy
    - Messages whose type is not 'user' or 'assistant'
    - Content blocks of type tool_use, tool_result, thinking, file-history-snapshot,
      progress, last-prompt
    - Messages with no text content after filtering
    - Malformed JSON lines (warns to stderr)
    """
    try:
        f = open(session_file, "r", encoding="utf-8")
    except (OSError, PermissionError) as e:
        print(f"WARNING: cannot open {session_file}: {e}", file=sys.stderr)
        return

    with f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError as e:
                print(
                    f"WARNING: malformed JSON in {session_file}:{lineno}: {e}",
                    file=sys.stderr,
                )
                continue

            if msg.get("isMeta"):
                continue

            message_body = msg.get("message")
            if not isinstance(message_body, dict):
                continue

            role = message_body.get("role")
            if role not in ("user", "assistant"):
                continue

            content = message_body.get("content")
            text = _extract_text_blocks(content)
            if text is None:
                continue

            yield {
                "role": role,
                "text": text,
                "timestamp": msg.get("timestamp"),
                "cwd": msg.get("cwd"),
                "git_branch": msg.get("gitBranch"),
            }


def assemble_output(target_date: date, matched_sessions: list[dict]) -> dict:
    """Extract messages from matched sessions and assemble the output JSON structure.

    Groups sessions by project (using cwd from messages). Each session includes
    session_id, time_range, git_branch, summary, and messages array.
    """
    now = datetime.now().astimezone()

    # project_path -> list of session dicts
    projects_map: dict[str, list[dict]] = {}

    total_sessions = 0
    total_messages = 0
    total_chars = 0

    for session_meta in matched_sessions:
        messages = list(extract_messages(session_meta["file_path"]))
        if not messages:
            continue

        # Derive project path from first message cwd, fallback to directory name
        cwd = None
        for m in messages:
            if m.get("cwd"):
                cwd = m["cwd"]
                break
        project_key = cwd or session_meta["project_dir"]

        # Time range: first and last message timestamps
        timestamps = [m["timestamp"] for m in messages if m.get("timestamp")]
        time_start = timestamps[0] if timestamps else None
        time_end = timestamps[-1] if timestamps else None

        # Git branch: first message that has one
        git_branch = None
        for m in messages:
            if m.get("git_branch"):
                git_branch = m["git_branch"]
                break

        # Summary: first user message text, truncated to 200 chars
        summary = None
        for m in messages:
            if m["role"] == "user":
                summary = m["text"][:200]
                break

        session_out = {
            "session_id": session_meta["session_id"],
            "time_range": {"start": time_start, "end": time_end},
            "git_branch": git_branch,
            "summary": summary,
            "messages": [
                {"role": m["role"], "text": m["text"], "timestamp": m["timestamp"]}
                for m in messages
            ],
        }

        projects_map.setdefault(project_key, []).append(session_out)
        total_sessions += 1
        total_messages += len(messages)
        total_chars += sum(len(m["text"]) for m in messages)

    projects_list = [
        {"project": proj, "sessions": sessions}
        for proj, sessions in sorted(projects_map.items())
    ]

    return {
        "date": target_date.isoformat(),
        "extracted_at": now.isoformat(),
        "stats": {
            "session_count": total_sessions,
            "project_count": len(projects_map),
            "message_count": total_messages,
            "estimated_tokens": total_chars // 4,
        },
        "projects": projects_list,
    }


def write_output(data: dict, output_dir: str, target_date: date) -> str:
    """Write output JSON to output_dir/YYYY-MM-DD.json. Returns the file path."""
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{target_date.isoformat()}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        output = json.dumps(data, indent=2, ensure_ascii=False)
        # Escape U+2028/U+2029 — literal LS/PS in JSON strings confuse editors
        output = output.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
        f.write(output)
        f.write("\n")
    return out_path


def main(argv=None):
    args = parse_args(argv)
    dates = get_target_dates(args)
    source_dir = args.source_dir or os.path.expanduser("~/.claude")
    local_tz = datetime.now().astimezone().tzinfo

    all_sessions = discover_sessions(source_dir)

    for d in dates:
        print(f"Extracting for: {d}", file=sys.stderr)
        matched = filter_sessions_by_date(all_sessions, d, local_tz)
        print(f"  {len(matched)} session(s) matched for {d}", file=sys.stderr)
        data = assemble_output(d, matched)
        stats = data["stats"]
        print(
            f"  projects={stats['project_count']}, sessions={stats['session_count']}, "
            f"messages={stats['message_count']}, tokens=~{stats['estimated_tokens']}",
            file=sys.stderr,
        )
        if not args.dry_run:
            out_path = write_output(data, args.output_dir, d)
            print(f"Written: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
