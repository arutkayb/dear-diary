# Dear Diary

A local-first pipeline that turns Claude Code conversation transcripts into structured daily diaries and reflections. Reads raw JSONL session files from `~/.claude/projects/`, filters out noise (tool use, thinking blocks, metadata), and produces clean JSON per day. A Claude skill then analyzes those diaries into reflection summaries with wins, learnings, challenges, and content seeds.

## The Pipeline

Dear Diary is a 3-stage pipeline: **Extract → Reflect → Create**.

```
~/.claude/projects/*/*.jsonl        (raw Claude Code sessions)
         |
         v
   Stage 1: extract.py              (deterministic filtering & structuring)
         |
         v
   output/YYYY-MM-DD.json           (clean daily diary JSON)
         |
         v
   Stage 2: /diary-review           (Claude skill — analysis & reflection)
         |
         v
   reflections/YYYY-MM-DD.md        (reflection-enriched markdown)
         |
         v
   Stage 3: (planned)               (content creation from reflections)
```

**Stage 1** is a pure Python script — no LLM, no external dependencies, just file I/O and text processing. It runs standalone via cron or manually.

**Stage 2** is a Claude Code skill that reads the diary JSON, analyzes conversations with parallel subagents, and produces a structured reflection. It has two modes: autonomous analysis and interactive Q&A.

**Stage 3** is planned but not yet implemented — it will generate blog posts and social content from the reflection output.

## Quick Start

### Extract today's diary

```bash
# Extract yesterday's conversations (default)
python3 extract.py

# Extract a specific date
python3 extract.py --date 2026-03-25

# Extract a date range
python3 extract.py --from 2026-03-20 --to 2026-03-25

# Preview without writing
python3 extract.py --dry-run
```

Output is written to `./output/YYYY-MM-DD.json`.

### Generate a reflection

From the project directory, using Claude Code:

```
/diary-review                          # Auto mode, yesterday
/diary-review 2026-03-25               # Auto mode, specific date
/diary-review --reflection             # Interactive mode, yesterday
/diary-review 2026-03-25 --reflection  # Interactive mode, specific date
```

Output is written to `./reflections/YYYY-MM-DD.md`.

## Stage 1: Extraction (`extract.py`)

### What it does

Scans all Claude Code project directories under `~/.claude/projects/`, finds sessions that have activity on the target date, and produces a single structured JSON file containing only the meaningful conversational content — human and assistant text messages.

### What it filters out

- `tool_use` and `tool_result` blocks
- `thinking` blocks
- `isMeta: true` messages
- `progress`, `file-history-snapshot`, `last-prompt` content types
- Non-user/assistant roles (system messages, etc.)
- Messages with no text content after filtering

### CLI options

| Flag | Description |
|------|-------------|
| `--date YYYY-MM-DD` | Extract a single date (default: yesterday) |
| `--from YYYY-MM-DD` | Start of date range |
| `--to YYYY-MM-DD` | End of date range |
| `--dry-run` | Print stats to stderr, don't write files |
| `--source-dir PATH` | Override `~/.claude` as source |
| `--output-dir PATH` | Override `./output` as destination |
| `--config FILE` | Path to config file (default: `./config.json`) |

### Output structure

```json
{
  "date": "2026-03-25",
  "extracted_at": "2026-03-25T09:17:49.976163+01:00",
  "stats": {
    "session_count": 94,
    "project_count": 5,
    "message_count": 665,
    "estimated_tokens": 182150,
    "commit_count": 12,
    "repo_count": 3
  },
  "projects": [
    {
      "project": "/path/to/project",
      "sessions": [
        {
          "session_id": "sess-abc123",
          "time_range": { "start": "...", "end": "..." },
          "git_branch": "main",
          "summary": "First 200 chars of first user message...",
          "messages": [
            { "role": "user", "text": "...", "timestamp": "..." },
            { "role": "assistant", "text": "...", "timestamp": "..." }
          ]
        }
      ]
    }
  ],
  "commits": [
    {
      "repo": "/path/to/repo",
      "commit_count": 3,
      "commits": [
        { "hash": "abc123", "timestamp": "...", "branch": "main", "message": "..." }
      ]
    }
  ]
}
```

The `commits` field is only present when git commit collection is enabled in config.

### The `extract-yesterday.sh` wrapper

A convenience script that runs extraction with `./diaries/` as the output directory instead of `./output/`:

```bash
./extract-yesterday.sh              # Same as: python3 extract.py --output-dir ./diaries
./extract-yesterday.sh --date 2026-03-25  # Accepts all extract.py flags
```

### Edge cases handled

- **Midnight-spanning sessions** — assigned to the date of last activity
- **Large JSONL files** — parsed line-by-line (streaming), never loaded entirely into memory
- **No sessions for target date** — produces valid JSON with empty data, not an error
- **Concurrent writes** — gracefully handles incomplete last lines from active sessions
- **Malformed JSON lines** — logged to stderr and skipped, never crashes

## Stage 2: Diary Review (`/diary-review` skill)

A Claude Code skill that transforms daily diary JSON into reflection-enriched markdown. It has two modes:

### Auto mode (default)

Analyzes conversations autonomously using parallel subagents (one per project, max 3 at a time). Infers wins, learnings, and challenges from the conversation content itself — what shipped, what broke, what took longer than expected.

### Reflection mode (`--reflection`)

An interactive session where the skill:
1. Presents a summary of the day
2. Asks 2-3 contextual questions specific to what you actually worked on
3. Processes your answers and follows up
4. Synthesizes everything into the reflection, with your own words taking precedence over inferred analysis

### Workflow

```
Phase 0: Setup
  Parse args → locate diary file → extract skeleton (stats, no messages)

Phase 1: Analysis (parallel)
  For each project → extract to temp file → launch subagent → collect findings

Phase 2: Synthesis
  Auto: infer reflections from conversation patterns
  Reflection: interactive Q&A → merge user input with analysis

Phase 3: Output
  Write reflections/YYYY-MM-DD.md
```

### Output sections

| Section | Content |
|---------|---------|
| Day Overview | Stats line + 1-2 sentence summary of the day's character |
| What I Worked On | 4-8 bullets grouped by project/theme, active past tense |
| Wins | 2-4 concrete accomplishments |
| Learnings | 2-4 insights or deeper understandings |
| Challenges | 1-3 friction points or blockers |
| Patterns | 1-3 meta-observations about workflow and habits |
| Key Takeaways | 3-5 standalone, quotable insights |
| Seeds for Content | 2-3 blog/post angles for Stage 3 |

## Configuration

Copy the example config to get started:

```bash
cp config.example.json config.json
```

### `config.json`

```json
{
  "git_commits": {
    "enabled": false,
    "additional_repos": []
  }
}
```

| Field | Description |
|-------|-------------|
| `git_commits.enabled` | When `true`, extract.py collects git commits from that day across all repos found in sessions |
| `git_commits.additional_repos` | Extra repo paths to scan beyond those discovered from session working directories |

`config.json` is gitignored — it may contain machine-specific paths.

## Project Structure

```
dear-diary/
├── extract.py                 # Stage 1 — extraction CLI
├── extract-yesterday.sh       # Convenience wrapper
├── config.json                # Local config (gitignored)
├── config.example.json        # Config template
├── PROJECT.txt                # Original PRD/requirements
├── tests/
│   ├── test_extract.py        # Message filtering, date assignment, output schema
│   ├── test_git_commits.py    # Config loading, repo discovery, commit collection
│   └── fixtures/              # JSONL test data
├── .claude/
│   ├── settings.json          # Claude Code permissions
│   └── skills/
│       └── diary-review/      # Stage 2 skill
│           ├── SKILL.md
│           ├── output-template.md
│           ├── reflection-prompts.md
│           ├── extract_skeleton.py
│           └── extract_project.py
├── output/                    # Daily diary JSON (gitignored)
├── diaries/                   # Alternative output dir (gitignored)
└── reflections/               # Reflection markdown (gitignored)
```

## Testing

The project has 17 unit tests covering message extraction, date filtering, output assembly, config loading, repo discovery, and git commit collection. No external dependencies — uses Python's built-in `unittest`.

```bash
python3 -m pytest tests/
# or
python3 -m unittest discover tests/
```

## Daily Workflow

A typical daily usage looks like this:

1. **Extract** — Run `extract-yesterday.sh` (or set up a cron job) to collect the previous day's conversations into a structured JSON file.

2. **Review** — Run `/diary-review` in Claude Code for an autonomous summary, or `/diary-review --reflection` for an interactive session where you reflect on what you worked on, what went well, and what was hard.

3. **Read** — Open `reflections/YYYY-MM-DD.md` for a structured record of the day: what shipped, what you learned, what patterns are emerging.

The pipeline is idempotent — re-running extraction for the same date overwrites the previous output, and re-running the review produces a fresh reflection.

## Design Principles

- **Zero external dependencies** — extract.py uses only Python stdlib. No pip install, no virtual environment, no dependency drift.
- **Local-first** — All data stays on your machine. No cloud services, no API calls, no telemetry.
- **Deterministic extraction** — Stage 1 has no LLM involvement. Same input always produces same output.
- **Idempotent** — Safe to re-run. Overwrites, never appends or duplicates.
- **Error-resilient** — Malformed data is logged and skipped. The script never crashes on bad input.
