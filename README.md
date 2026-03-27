# Dear Diary

[![Tests](https://github.com/arutkayb/dear-diary/actions/workflows/tests.yml/badge.svg)](https://github.com/arutkayb/dear-diary/actions/workflows/tests.yml)

Turn your [Claude Code](https://docs.anthropic.com/en/docs/claude-code) conversation transcripts into structured daily diaries and reflections — automatically.

Dear Diary reads raw JSONL session files from `~/.claude/projects/`, filters out noise (tool use, thinking blocks, metadata), and produces clean JSON per day. A Claude Code skill then analyzes those diaries into reflections with wins, learnings, challenges, and content seeds.

## How It Works

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
   Stage 2: /diary-review           (Claude Code skill — analysis & reflection)
         |
         v
   reflections/YYYY-MM-DD.md        (structured reflection markdown)
```

**Stage 1** is a pure Python script — no LLM, no external dependencies, just file I/O and text processing.

**Stage 2** is a Claude Code skill that reads the diary JSON and produces a structured reflection. Two modes: autonomous analysis or interactive Q&A.

## Requirements

- **Python 3.6+** (uses only the standard library — no pip install needed)
- **Claude Code** (for Stage 2 skill only — Stage 1 works standalone)
- **macOS or Linux** (Windows is not supported)
- **Git** (optional, for commit collection feature)

## Quick Start

```bash
# Clone the repo
git clone https://github.com/arutkayb/dear-diary.git
cd dear-diary

# Extract yesterday's conversations
python3 extract.py

# Extract a specific date
python3 extract.py --date 2025-03-25

# Extract a date range
python3 extract.py --from 2025-03-20 --to 2025-03-25

# Preview without writing files
python3 extract.py --dry-run
```

Output is written to `./output/YYYY-MM-DD.json`.

### Generate a Reflection

From the project directory, using Claude Code:

```
/diary-review                          # Auto mode, yesterday
/diary-review 2025-03-25               # Auto mode, specific date
/diary-review --reflection             # Interactive Q&A mode
/diary-review 2025-03-25 --reflection  # Interactive mode, specific date
```

Output is written to `./reflections/YYYY-MM-DD.md`.

## CLI Reference

| Flag | Description |
|------|-------------|
| `--date YYYY-MM-DD` | Extract a single date (default: yesterday) |
| `--from YYYY-MM-DD` | Start of date range (inclusive) |
| `--to YYYY-MM-DD` | End of date range (inclusive, requires `--from`) |
| `--dry-run` | Print stats to stderr, don't write files |
| `--source-dir PATH` | Override `~/.claude` as source |
| `--output-dir PATH` | Override `./output` as destination |
| `--config FILE` | Path to config file (default: `./config.json`) |

## Configuration

```bash
cp config.example.json config.json
```

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
| `git_commits.enabled` | Collect git commits from that day across discovered repos |
| `git_commits.additional_repos` | Extra repo paths to scan beyond those found in sessions |

`config.json` is gitignored — it contains machine-specific paths.

## Output Format

```json
{
  "date": "2025-03-25",
  "extracted_at": "2025-03-25T09:17:49.976163+01:00",
  "stats": {
    "session_count": 12,
    "project_count": 3,
    "message_count": 245,
    "estimated_tokens": 67000
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
  "commits": []
}
```

The `commits` array is populated when git commit collection is enabled in config.

## Reflection Output

The `/diary-review` skill produces a markdown file with these sections:

| Section | Content |
|---------|---------|
| Day Overview | Stats + 1-2 sentence summary of the day's character |
| What I Worked On | Bullets grouped by project/theme |
| Wins | Concrete accomplishments |
| Learnings | Insights and deeper understandings |
| Challenges | Friction points or blockers |
| Patterns | Meta-observations about workflow |
| Key Takeaways | Standalone, quotable insights |
| Seeds for Content | Blog/post angles from the day's work |

## Project Structure

```
dear-diary/
├── extract.py                 # Stage 1 — extraction CLI
├── extract-yesterday.sh       # Convenience wrapper (outputs to ./diaries/)
├── config.example.json        # Config template
├── LICENSE
├── tests/
│   ├── test_extract.py        # Message filtering, date assignment, output schema
│   ├── test_git_commits.py    # Config loading, repo discovery, commit collection
│   └── fixtures/              # JSONL test data
└── .claude/
    ├── settings.json          # Claude Code permissions
    └── skills/
        └── diary-review/      # Stage 2 skill
            ├── SKILL.md
            ├── output-template.md
            ├── reflection-prompts.md
            ├── extract_skeleton.py
            └── extract_project.py
```

## Testing

42 unit tests, zero external dependencies:

```bash
python3 -m unittest discover tests/
```

## Design Principles

- **Zero external dependencies** — Python stdlib only. No pip install, no virtual environment.
- **Local-first** — All data stays on your machine. No cloud services, no API calls, no telemetry.
- **Deterministic extraction** — Stage 1 has no LLM involvement. Same input, same output.
- **Idempotent** — Safe to re-run. Overwrites cleanly, never appends or duplicates.
- **Error-resilient** — Malformed data is logged and skipped, never crashes.

## Contributing

Contributions are welcome! Please open an issue first to discuss what you'd like to change.

## License

[MIT](LICENSE)
