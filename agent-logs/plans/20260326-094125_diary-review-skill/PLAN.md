---
milestone: null
prd: null
status: completed
created: 2026-03-26
steps_total: 4
steps_completed: 4
---

## Goal

Create a Claude skill (`diary-review`) with two modes — `auto` (default, autonomous analysis) and `--reflection` (interactive iterative Q&A) — that reads extracted diary JSON and produces a reflection-enriched summary written to `reflections/YYYY-MM-DD.md`.

## Approach

This skill is Stage 2 of the 3-stage pipeline defined in `PROJECT.txt` (Extract → **Diary** → Content). It reads the JSON output from Stage 1 (`extract.py`) and produces structured reflection markdown.

**Patterns followed:**
- Multi-mode via `$ARGUMENTS` parsing — same as `audit-skill/SKILL.md` (argument-hint + positional/flag parsing)
- Interactive multi-turn Q&A — same as `intense-plan/SKILL.md` Phase 1 → WAIT → Phase 2 pattern, extended to 2-3 iterative rounds
- Supporting reference files via `${CLAUDE_SKILL_DIR}` — same as `intense-plan` (checklist + procedure) and `audit-skill` (checklist)
- Large-file handling via Bash+Python extraction then Agent subagents — combining patterns from `intense-plan` (parallel Explore agents) with lightweight preprocessing

**Reused code:** None directly. The skill reads `extract.py` output but doesn't import or call it.

**Written fresh:**
- `SKILL.md` — main skill instructions (~150-200 lines)
- `reflection-prompts.md` — categorized question bank (~60-80 lines)
- `output-template.md` — output markdown structure (~40-50 lines)

These are new because no existing skill does diary analysis or iterative reflection.

## Decision Register

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Skill location | `~/workspace/agentic-files/skills/diary-review/` symlinked to `~/.claude/skills/diary-review/` | CLAUDE.md global instructions for skill management |
| 2 | Mode selection | `--reflection` flag; `auto` is default | User confirmed — auto is the common case |
| 3 | Date handling | Optional positional `YYYY-MM-DD`, defaults to yesterday | User confirmed, matches `extract.py` convention |
| 4 | Invocation format | `/diary-review [YYYY-MM-DD] [--reflection]` | User answers: date positional, mode as flag |
| 5 | Diary file discovery | `./diaries/YYYY-MM-DD.json`, fallback `./output/YYYY-MM-DD.json` | Codebase: `extract-yesterday.sh` writes to `./diaries/`, older runs in `./output/` |
| 6 | Output destination | `./reflections/YYYY-MM-DD.md` | User confirmed |
| 7 | Output format | Platform-agnostic structured reflection markdown | User confirmed — content-creator is a separate step |
| 8 | Reflection mode depth | Iterative: 2-3 questions per round, 2-3 rounds, follow-ups based on answers | User confirmed |
| 9 | Large-file strategy | Bash `python3 -c` to extract summary JSON (projects, sessions, stats — no messages), then Agent subagents read specific sessions | User confirmed |
| 10 | Model/effort | `opus` + `max` | Understanding-heavy analysis; matches `audit-skill`, `code-reviewer` convention |
| 11 | Composition with content-creator | None — fully independent | User confirmed: content creation is a separate planned step |
| 12 | Tool scoping | `Read, Write, Glob, Grep, Bash(python3:*, date:*, ls:*, mkdir:*), Agent` | Read-heavy analysis + Write for output + Bash for JSON preprocessing + Agent for parallel deep dives |
| 13 | Supporting files | `reflection-prompts.md` (question bank), `output-template.md` (output structure) | Pattern from `audit-skill/audit-checklist.md`, `intense-plan/save-plan-procedure.md` |
| 14 | Auto mode parallelism | One Agent subagent per project (up to 3 parallel) | Pattern from `intense-plan` Phase 1 parallel subagents |
| 15 | Reflection round termination | Skill judges richness after each round; moves to output after 2-3 rounds or when user signals done | Iterative but bounded to avoid fatigue |

## Files Touched

| Action | File Path | What Changes |
|--------|-----------|--------------|
| CREATE | `~/workspace/agentic-files/skills/diary-review/SKILL.md` | Main skill: frontmatter, argument parsing, Phase 0-3 instructions for both modes |
| CREATE | `~/workspace/agentic-files/skills/diary-review/reflection-prompts.md` | Categorized reflection questions: accomplishments, learning, challenges, patterns, growth |
| CREATE | `~/workspace/agentic-files/skills/diary-review/output-template.md` | Markdown template for reflection output with section descriptions |
| CREATE | `~/.claude/skills/diary-review` | Symlink → `~/workspace/agentic-files/skills/diary-review` |

## Implementation Steps

### Phase A: Supporting files

- [x] **Step 1: Create reflection-prompts.md**
  - **What:** A categorized bank of reflection questions the skill draws from. Categories: Accomplishments & Impact, Learning & Growth, Challenges & Blockers, Patterns & Workflow, Direction & Intent. Each category has 4-5 questions ranging from surface-level ("What did you ship?") to deeper ("What assumption got challenged today?"). Includes guidance on when to use which questions (e.g., high session count → ask about context switching; single-project days → ask about depth vs breadth).
  - **Files:** `~/workspace/agentic-files/skills/diary-review/reflection-prompts.md`
  - **Depends on:** None
  - **Verify by:** `wc -l` shows 60-80 lines; file has 5 category headers with 4-5 questions each

- [x] **Step 2: Create output-template.md**
  - **What:** The markdown structure for the reflection output. Sections: Day Overview (date, stats, 1-2 sentence summary), What I Worked On (bulleted by project/theme), Reflections (subsections: Wins, Learnings, Challenges, Patterns), Key Takeaways (3-5 distilled points), Seeds for Content (2-3 potential blog/LinkedIn angles derived from the day). Each section has a short description of what goes there and how to derive it.
  - **Files:** `~/workspace/agentic-files/skills/diary-review/output-template.md`
  - **Depends on:** None
  - **Verify by:** `wc -l` shows 40-50 lines; file has all 6 section headers

### Phase B: Main skill file

- [x] **Step 3: Create SKILL.md**
  - **What:** The full skill definition with YAML frontmatter and phased instructions:
    - **Frontmatter:** `name: diary-review`, `argument-hint: [YYYY-MM-DD] [--reflection]`, `model: opus`, `effort: max`, `allowed-tools` as per Decision #12, `disable-model-invocation: true`
    - **Phase 0 — Setup:** Parse `$ARGUMENTS` for date and `--reflection` flag. Default date to yesterday via `date -v-1d +%Y-%m-%d`. Locate diary file (`./diaries/YYYY-MM-DD.json` then `./output/YYYY-MM-DD.json`). Error if not found. Run Bash `python3 -c` one-liner to extract lightweight summary: `{date, stats, projects: [{project, session_count, sessions: [{summary, time_range, git_branch}]}]}` — no messages, just the skeleton.
    - **Phase 1 — Analysis:** Launch Agent subagents (one per project, max 3 parallel, type Explore) to read specific session messages and identify: what was done, decisions made, challenges, outcomes, tools/techniques used. Each subagent gets the diary file path and the project name to focus on.
    - **Phase 2A — Auto mode:** Synthesize subagent findings into reflection points. Infer wins, learnings, challenges, and patterns from the conversation content. Read `${CLAUDE_SKILL_DIR}/output-template.md` and generate the reflection. Write to `./reflections/YYYY-MM-DD.md`.
    - **Phase 2B — Reflection mode:** Present the high-level summary to the user. Read `${CLAUDE_SKILL_DIR}/reflection-prompts.md`. Select 2-3 contextually relevant questions based on the day's activity shape (e.g., multi-project → ask about prioritization; debugging sessions → ask about root cause insights). Ask questions. WAIT for user response. Process answers. Ask 2-3 follow-up questions that dig deeper into what the user shared. WAIT. After 2-3 rounds (or when user signals done), synthesize user reflections + conversation analysis into the output. Write to `./reflections/YYYY-MM-DD.md`.
    - **Phase 3 — Wrap up:** Print the output file path and a 2-3 line summary of themes. Do NOT print the full reflection.
    - **Rules:** Never fabricate reflections the conversations don't support. In reflection mode, questions should be specific to what the user actually did (reference project names, features, bugs from the diary). If diary has no sessions, write a minimal file noting the empty day.
  - **Files:** `~/workspace/agentic-files/skills/diary-review/SKILL.md`
  - **Depends on:** Steps 1, 2 (references both supporting files)
  - **Verify by:** `wc -l` shows 150-200 lines; frontmatter parses as valid YAML; file references `${CLAUDE_SKILL_DIR}/reflection-prompts.md` and `${CLAUDE_SKILL_DIR}/output-template.md`

### Phase C: Symlink and verify

- [x] **Step 4: Create symlink and verify**
  - **What:** Symlink `~/.claude/skills/diary-review` → `~/workspace/agentic-files/skills/diary-review`. Verify the skill appears in Claude's skill list and the symlink resolves correctly.
  - **Files:** `~/.claude/skills/diary-review` (symlink)
  - **Depends on:** Step 3
  - **Verify by:** `ls -la ~/.claude/skills/diary-review` shows symlink; `cat ~/.claude/skills/diary-review/SKILL.md` shows valid content with correct frontmatter

## Testing Strategy

- **Smoke test (auto mode):** Run `/diary-review 2026-03-25` from the `dear-diary` project directory. Verify it creates `reflections/2026-03-25.md` with all expected sections populated.
- **Smoke test (reflection mode):** Run `/diary-review 2026-03-25 --reflection`. Verify it presents the day summary, asks contextual questions, waits for response, asks follow-ups, and generates the output after 2-3 rounds.
- **Edge case — no diary:** Run `/diary-review 2020-01-01` (nonexistent date). Verify it errors gracefully.
- **Edge case — default date:** Run `/diary-review --reflection` (no date). Verify it uses yesterday.

No automated test suite — this is a Claude skill (markdown instructions), not executable code.

## Risks & Hard Parts

- **Hardest part:** The large-file preprocessing strategy. The Bash `python3 -c` one-liner to extract the diary skeleton must handle the full JSON structure without loading messages. If the diary file is malformed or has unexpected nesting, this breaks Phase 0. Mitigation: the one-liner should be tested against the known `2026-03-25.json` file before finalizing.
- **Most likely wrong assumption:** That Agent subagents can effectively read specific portions of the 900KB diary file by project. If the Read tool's offset/limit isn't precise enough to target a specific project's messages, the subagents may need to use Bash+Python to extract their project's data instead.
- **Edge case easy to miss:** Sessions spanning midnight — a session with `time_range.end` on the target date but `time_range.start` on the previous date. The diary JSON already handles this (extract.py assigns by last-activity date), but the skill's summary should note the actual work timespan.

## Out of Scope

- Content creation / platform-specific formatting (Stage 3 — user will plan separately with content-creator)
- Automated daily cron execution of the review skill
- Historical trend analysis across multiple days' reflections
- Integration with extract.py (skill reads its output, doesn't invoke it)
