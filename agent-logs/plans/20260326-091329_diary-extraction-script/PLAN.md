---
milestone: null
prd: null
status: completed
created: 2026-03-26
steps_total: 11
steps_completed: 11
---

## Goal

A Python CLI script that extracts all Claude Code conversation transcripts from local storage (`~/.claude/projects/`) for a given date, filters them to human/assistant text-only messages, and writes one structured JSON file per day to `./output/`.

## What This Is Not

- No LLM processing, summarization, or diary generation (Stage 2)
- No content creation or publishing (Stage 3)
- No GUI, web interface, or interactive mode
- No project allowlist/blocklist filtering — every session on the host is extracted
- No session deduplication across machines — single-host only
- No database or persistent index — stateless, reads raw files each run

## Tech Stack

| Category | Choice | Reason |
|----------|--------|--------|
| Language | Python 3.10+ | Zero external deps possible; built-in json, argparse, datetime handle all needs. Simpler streaming I/O than Node.js for this workload. |
| Framework / runtime | None (stdlib only) | PRD requires minimal dependencies; Python stdlib covers JSONL parsing, CLI args, file I/O, timezone handling |
| Build / package manager | None | Single-file script, no packaging needed. Run directly with `python3 extract.py` |
| Data storage | JSON files on disk | Output is `./output/YYYY-MM-DD.json`. No database. |
| Testing | unittest (stdlib) | No need for pytest — stdlib is sufficient for the test surface area |
| Deployment target | macOS local machine via cron/launchd | Single user, single host, runs as scheduled task |

## Decision Register

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Language | Python 3.10+ | User said "pick based on fit". Python's built-in json, argparse, datetime, and lazy file iteration make this the simplest choice for a zero-dep JSONL processing CLI. |
| 2 | Default target date | Yesterday (host local timezone) | PRD CLI Interface section |
| 3 | Idempotency strategy | Overwrite previous output for same date | PRD Idempotency section |
| 4 | Midnight-spanning sessions | Assign to date of last message activity | PRD Edge Cases section |
| 5 | Error handling | Log warning to stderr, continue processing | PRD Error Resilience section |
| 6 | No-sessions behavior | Write valid JSON with empty projects array and zero stats | PRD Edge Cases section |
| 7 | JSONL parsing | Line-by-line iteration (`for line in open(f)`) — Python does this lazily by default | PRD Non-Functional (streaming requirement) |
| 8 | Performance target | Full day extraction under 30 seconds for 20+ sessions | PRD Non-Functional |
| 9 | Output token budget | Under 100k tokens (~400k chars) for a heavy day | PRD Success Criteria |
| 10 | Message filtering | Keep `type=user` and `type=assistant` messages only. From content blocks, keep only `type=text`. Discard `tool_use`, `tool_result`, `thinking`, `file-history-snapshot`, `progress`, `last-prompt`. Skip messages with `isMeta=true`. | PRD Message Extraction + verified schema inspection |
| 11 | Date/time format in output | ISO 8601 with timezone offset (e.g., `2026-03-25T09:15:00+03:00`) | Industry convention |
| 12 | Output JSON formatting | 2-space indentation | Convention for human-inspectable JSON |
| 13 | Incomplete JSONL line handling | Skip the line, log warning to stderr | Standard streaming parser behavior for concurrent-write safety |
| 14 | CLI flag names | `--date`, `--from`, `--to`, `--dry-run`, `--output-dir`, `--source-dir` | POSIX CLI conventions |
| 15 | Exit codes | 0 = success, 1 = fatal error | POSIX convention |
| 16 | Log destination | stderr (so stdout/file output stays clean) | POSIX convention for CLIs |
| 17 | Output directory default | `./output/` | User confirmed |
| 18 | Output filename pattern | `YYYY-MM-DD.json` (bare date) | User confirmed |
| 19 | Timezone for date boundaries | Host machine local timezone (`datetime.now().astimezone()`) | User confirmed |
| 20 | Token estimation | `character_count // 4` | User confirmed as accurate enough |
| 21 | Date range output | One file per day | User confirmed |
| 22 | Project exclusion | None — extract all projects | User confirmed: "I want every conversation" |
| 23 | Session discovery method | Scan `~/.claude/projects/*/*.jsonl` for session files | Verified by inspecting actual storage layout |
| 24 | Project path extraction | Read `cwd` field from first message in each session file (avoids lossy directory name decoding) | Verified: directory encoding is lossy (`/` and `_` both become `-`), but each message carries the real `cwd` |
| 25 | Session summary | First user message text, truncated to 200 chars | No summary field exists in session index files (verified). First prompt gives Stage 2 quick context. |
| 26 | Git branch per session | Take `gitBranch` field from first message that has it | Verified: field exists on most messages |
| 27 | Session time range | Derived from first and last message timestamps in the filtered set | No start/end fields in session metadata |
| 28 | Content block text joining | When a message has multiple `text` blocks, join with newline | Keeps all text content, simple separator |

## Project Structure

```
dear-diary/
├── extract.py           # Main CLI script — all extraction logic in one file
├── tests/
│   ├── test_extract.py  # Unit tests for extraction functions
│   └── fixtures/        # Sample JSONL files for testing
├── output/              # Default output directory (created at runtime, gitignored)
└── PROJECT.txt          # PRD (already exists)
```

## Files to Create

| Order | File Path | Purpose |
|-------|-----------|---------|
| 1 | extract.py | Main script: CLI parsing, session discovery, JSONL extraction, date filtering, output assembly, file writing |
| 2 | tests/fixtures/session_basic.jsonl | Test fixture: minimal session with user/assistant text messages |
| 3 | tests/fixtures/session_mixed.jsonl | Test fixture: session with tool_use, thinking, isMeta, tool_result blocks mixed with text |
| 4 | tests/fixtures/session_malformed.jsonl | Test fixture: session with broken JSON lines and incomplete trailing line |
| 5 | tests/test_extract.py | Tests for message filtering, date filtering, output structure, error resilience |
| 6 | .gitignore | Ignore output/ directory and __pycache__ |

## Implementation Phases

**Phase A: Scaffold**
Goal: `python3 extract.py` runs, parses CLI args, and writes a valid empty JSON file to `./output/`.

- [x] **Step 1: CLI skeleton with argparse**
  - **What exists after:** `extract.py` with `main()`, argparse setup for `--date` flag, and date resolution (defaults to yesterday in host local TZ). Prints resolved date to stderr and exits 0.
  - **Files:** `extract.py`
  - **Verify by:** `python3 extract.py` prints `Extracting for: YYYY-MM-DD` (yesterday). `python3 extract.py --date 2026-03-20` prints `Extracting for: 2026-03-20`. Exit code 0.

- [x] **Step 2: Empty output writer**
  - **What exists after:** Script writes a valid JSON file to `./output/YYYY-MM-DD.json` with the correct structure (date, extracted_at, zero stats, empty projects array). Creates output dir if missing.
  - **Files:** `extract.py`, `.gitignore`
  - **Verify by:** `python3 extract.py --date 2026-03-20 && cat output/2026-03-20.json | python3 -m json.tool` shows valid JSON with `"date": "2026-03-20"`, `"session_count": 0`, empty `"projects": []`.

**Phase B: Core**
Goal: extracting yesterday's conversations works end-to-end with real data.

- [x] **Step 3: Session discovery**
  - **What exists after:** `discover_sessions(source_dir)` scans `~/.claude/projects/*/*.jsonl`, returns list of `{file_path, session_id, project_dir}` for all session files.
  - **Files:** `extract.py`
  - **Depends on:** Step 1
  - **Verify by:** `python3 -c "from extract import discover_sessions; sessions = discover_sessions('$HOME/.claude'); print(f'{len(sessions)} sessions found')"` prints a count close to 911.

- [x] **Step 4: Date filtering**
  - **What exists after:** `filter_sessions_by_date(sessions, target_date, local_tz)` reads timestamps from each session file (first and last message), determines the session's activity date (last message timestamp converted to local TZ), returns only sessions active on target_date.
  - **Files:** `extract.py`
  - **Depends on:** Step 3
  - **Verify by:** `python3 extract.py --date 2026-03-25` logs to stderr the number of sessions found for that date. Running with today's date shows sessions from today.

- [x] **Step 5: Message extraction and filtering**
  - **What exists after:** `extract_messages(session_file)` parses JSONL line-by-line, yields only `{role, text, timestamp}` for user/assistant messages with text content blocks. Skips tool_use, tool_result, thinking, file-history-snapshot, progress, last-prompt, and isMeta messages. Handles malformed lines (skip + warn).
  - **Files:** `extract.py`
  - **Depends on:** Step 3
  - **Verify by:** `python3 -c "from extract import extract_messages; msgs = list(extract_messages('$HOME/.claude/projects/-Users-rutkay-workspace-agentic-files/b38b8733-27df-4158-a175-f746966131a1.jsonl')); print(f'{len(msgs)} text messages extracted')"` — count should be significantly less than 488 (total lines in that file).

- [x] **Step 6: Output assembly with stats**
  - **What exists after:** Full pipeline wired: discover → filter → extract → assemble JSON structure grouped by project (using `cwd`), then by session. Each session includes session_id, time_range (first/last message), git_branch, summary (first user message truncated to 200 chars), and messages array. Stats computed: session_count, project_count, message_count, estimated_tokens (total chars // 4). Output written to `./output/YYYY-MM-DD.json`.
  - **Files:** `extract.py`
  - **Depends on:** Steps 2, 4, 5
  - **Verify by:** `python3 extract.py --date 2026-03-25 && python3 -c "import json; d=json.load(open('output/2026-03-25.json')); print(f'projects={len(d[\"projects\"])}, sessions={d[\"stats\"][\"session_count\"]}, messages={d[\"stats\"][\"message_count\"]}, tokens=~{d[\"stats\"][\"estimated_tokens\"]}')"` shows non-zero stats (assuming there were sessions on 2026-03-25).

- [x] **Step 7: Unit tests**
  - **What exists after:** Test fixtures with controlled JSONL data. Tests covering: (1) message filtering keeps only user/assistant text blocks, (2) isMeta messages are skipped, (3) tool_use/tool_result/thinking blocks are stripped, (4) midnight-spanning session assigned to last-activity date, (5) malformed JSON lines skipped without crash.
  - **Files:** `tests/test_extract.py`, `tests/fixtures/session_basic.jsonl`, `tests/fixtures/session_mixed.jsonl`, `tests/fixtures/session_malformed.jsonl`
  - **Depends on:** Steps 5, 6
  - **Verify by:** `python3 -m pytest tests/test_extract.py -v` (or `python3 -m unittest tests.test_extract -v`) — all tests pass.

**Phase C: Complete**
Goal: all planned CLI features working, resilient to edge cases.

- [x] **Step 8: Date range support**
  - **What exists after:** `--from` and `--to` flags. When both provided, script iterates over each date in range and produces one output file per day. `--date` and `--from/--to` are mutually exclusive.
  - **Files:** `extract.py`
  - **Depends on:** Step 6
  - **Verify by:** `python3 extract.py --from 2026-03-20 --to 2026-03-22 && ls output/` shows `2026-03-20.json`, `2026-03-21.json`, `2026-03-22.json`.

- [x] **Step 9: Dry run mode**
  - **What exists after:** `--dry-run` flag. When set, script runs the full pipeline but prints stats to stderr instead of writing files. Shows per-project session count and total message/token estimates.
  - **Files:** `extract.py`
  - **Depends on:** Step 6
  - **Verify by:** `python3 extract.py --dry-run --date 2026-03-25` prints stats to stderr, no file created in `output/`. Exit code 0.

- [x] **Step 10: Configurable directories**
  - **What exists after:** `--output-dir` overrides default `./output/`. `--source-dir` overrides default `~/.claude`. Both create target dirs if needed.
  - **Files:** `extract.py`
  - **Depends on:** Step 6
  - **Verify by:** `python3 extract.py --date 2026-03-25 --output-dir /tmp/diary-test && cat /tmp/diary-test/2026-03-25.json | python3 -m json.tool` shows valid output.

- [x] **Step 11: Error resilience hardening**
  - **What exists after:** Graceful handling of: empty session files (skip), session files with only non-message types (skip), source directory not existing (error message + exit 1), permission errors on individual files (warn + skip). All warnings logged to stderr with file path context.
  - **Files:** `extract.py`
  - **Depends on:** Step 6
  - **Verify by:** `python3 extract.py --source-dir /nonexistent 2>&1` prints error and exits 1. Create an empty `.jsonl` file in a test project dir, run extraction — no crash, warning logged.

## Testing Strategy

- **Framework:** `unittest` (Python stdlib). Test files in `tests/`. Run with `python3 -m unittest discover tests -v`.
- **Fixtures:** Hand-crafted JSONL files in `tests/fixtures/` with known content for deterministic assertions.
- **Key behaviors to test:**
  1. **Message filtering correctness** — given a JSONL with text, tool_use, tool_result, thinking, and isMeta messages, only user/assistant text blocks appear in output
  2. **Midnight-spanning session date assignment** — a session with messages on March 25 23:50 and March 26 00:10 is assigned to March 26
  3. **Output JSON schema validation** — output contains all required fields (date, extracted_at, stats, projects with sessions and messages) with correct types
  4. **Malformed JSONL resilience** — broken JSON lines and incomplete trailing lines are skipped, valid lines still extracted
  5. **Empty date produces valid output** — extracting a date with no sessions writes valid JSON with zero stats and empty projects array
- **Tests begin in Phase B** (Step 7), not deferred to Phase C.

## Risks

1. **JSONL schema drift** — Claude Code may change its storage format across versions. The `version` field on messages could help detect this, but the extractor assumes the schema verified today (v2.1.84). Mitigation: the error-resilience layer (Step 11) will skip unrecognizable messages with warnings rather than crash.

2. **Lossy project directory encoding** — The `-`-separated directory names under `~/.claude/projects/` cannot be reliably decoded back to filesystem paths (both `/` and `_` become `-`). Mitigation: we use the `cwd` field from messages instead (Decision #24), but if a session file has zero parseable messages, we lose the project path. Default: use the directory name as-is.

3. **Token estimation accuracy** — `chars // 4` is a rough approximation. Actual Claude tokenization varies. The 100k token budget check could be off by 20-30%. Mitigation: this is a monitoring stat, not a hard limit — Stage 2 will handle actual context window fitting.

4. **Large file I/O performance** — The largest session file is ~30MB (488 lines of very long JSON). Line-by-line Python parsing should handle this fine, but if many such files exist for one day, the 30-second target could be tight. Mitigation: Python's lazy file iteration keeps memory flat; time is bounded by disk I/O which should be fast for local SSD.
