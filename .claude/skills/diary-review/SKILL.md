---
name: diary-review
description: Reviews a daily diary JSON (from extract.py) and produces a reflection-enriched summary written to reflections/YYYY-MM-DD.md. Two modes: reflection (interactive iterative Q&A, default) and --auto (autonomous analysis). Use from the dear-diary project directory.
argument-hint: [YYYY-MM-DD] [--auto]
disable-model-invocation: true
model: opus
effort: max
allowed-tools: Read, Write, Glob, Grep, Bash(python3:*), Bash(date:*), Bash(ls:*), Agent
---

## Arguments

`$ARGUMENTS` — optional `YYYY-MM-DD` date and/or `--auto` flag, e.g.:
- `/diary-review` → reflection mode, yesterday
- `/diary-review 2026-03-25` → reflection mode, specific date
- `/diary-review --auto` → auto mode, yesterday
- `/diary-review 2026-03-25 --auto` → auto mode, specific date

---

## Phase 0: Setup

### Parse arguments

From `$ARGUMENTS`:
1. Check for `--auto` flag — set `mode = auto` if present, else `mode = reflection`
2. Check for a date string matching `YYYY-MM-DD` — use it as `target_date`
3. If no date provided, resolve yesterday:
   - macOS: `date -v-1d +%Y-%m-%d`
   - Linux: `date -d yesterday +%Y-%m-%d`
   - Detect with: `if [[ "$OSTYPE" == "darwin"* ]]; then ... else ... fi`

### Locate the diary file

Try in order:
1. `./diaries/{target_date}.json`
2. `./output/{target_date}.json`

If neither exists, stop and print: `No diary found for {target_date}. Run extract.py first.`

### Extract diary skeleton

Run the skeleton extraction script:

```bash
python3 ${CLAUDE_SKILL_DIR}/extract_skeleton.py {diary_file}
```

If the diary has 0 sessions across all projects: create `./reflections/{target_date}.md` with a note ("No Claude Code sessions found for {target_date}.") and stop.

---

## Phase 1: Analysis

Using the skeleton from Phase 0, launch Agent subagents in parallel — one per project, max 3 at a time, type `Explore`.

First, extract each project's data to a temp file. Run these commands (one per project, can be parallel):

```
python3 ${CLAUDE_SKILL_DIR}/extract_project.py {diary_file} my_next_niche /tmp/diary-project-my_next_niche.txt
```

Use the exact command above as a template — only change the project query and output filename. Do NOT add shell redirects (`>`), substitutions (`$()`), `2>&1`, or any other shell constructs. The script writes the file and prints confirmation itself.

Then launch each subagent with:
- The temp file path for its project (e.g., `/tmp/diary-project-my_next_niche.txt`)
- This instruction: "Read the file at `/tmp/diary-project-{name}.txt` using the Read tool with offset/limit to read in chunks. It is a plain text file (not JSON) with sessions and messages already formatted as readable text. For each session, identify: (1) what was done/built/fixed/decided, (2) notable decisions or design choices, (3) challenges or blockers encountered, (4) outcomes and their status (shipped, in-progress, abandoned). IMPORTANT: Only use the Read tool. Do NOT use Bash, Grep, or any other tool. The file is already plain text — no parsing needed. Return a structured summary per session, then a project-level rollup."

If there are more than 3 projects, analyze the top 3 by session count and note the rest briefly from the skeleton summaries.

Collect all subagent results. Now you have a full picture of the day.

---

## Phase 2A: Auto mode

*Skip to Phase 2B if `mode = reflection` (the default).*

Synthesize subagent findings into the reflection output:

1. Read `${CLAUDE_SKILL_DIR}/output-template.md` for the section structure.
2. Generate the full reflection following the template exactly. For each section, derive content from the conversation analysis:
   - **Wins**: Look for shipped features, passing tests, successful deploys, bugs resolved
   - **Learnings**: Look for design decisions explained, new patterns discovered, moments of realization
   - **Challenges**: Look for long debug sessions, multiple retries, error loops, abandoned attempts
   - **Patterns**: Look at session distribution, time ranges, project spread — derive meta-observations
   - **Seeds for Content**: Pick the 2-3 most interesting moments or decisions that would resonate with other developers or indie builders
3. Go to Phase 3.

---

## Phase 2B: Reflection mode

### Round 1: Present summary and ask initial questions

Present a concise summary of the day to the user (project names, what was done, 3-5 bullets max — use skeleton data). Then:

1. Read `${CLAUDE_SKILL_DIR}/reflection-prompts.md`
2. Based on the day's shape (see "When to Use Which Questions" table), select 2-3 contextually relevant questions
3. Make questions specific — reference actual project names, features, bugs, or session details from the diary
4. Ask questions. **WAIT for user response.**

### Round 2: Process and follow up

Process the user's answers. Incorporate what they shared into your understanding. Then:
1. Ask 2-3 follow-up questions that dig into something the user mentioned, or open a dimension they didn't address
2. Avoid re-asking anything already answered
3. **WAIT for user response.**

### Round 3 (optional): Final depth

If the responses so far are rich enough to fill all output sections, skip to synthesis. Otherwise ask 1-2 final questions targeting any remaining gaps.

When the user signals done (e.g., "that's enough", "let's write it", or gives very short answers), proceed immediately.

### Synthesize

Combine the conversation analysis (from Phase 1) with the user's reflections to generate the output. User-provided reflections take precedence over inferred ones — never overwrite what the user said with something different.

Read `${CLAUDE_SKILL_DIR}/output-template.md` and generate the full reflection. Go to Phase 3.

---

## Phase 3: Write output

1. Use the Write tool to write the generated reflection to `./reflections/{target_date}.md` (the Write tool creates parent directories automatically — do NOT run mkdir)
3. Print: `Reflection written to reflections/{target_date}.md`
4. Print a 2-3 line summary of the key themes identified (do NOT print the full file)

---

## Rules

- Never fabricate reflections, wins, or learnings that aren't supported by the conversation content or user responses.
- In reflection mode, questions must be specific to what the user actually did — no generic questions that could apply to any day.
- In auto mode, if you cannot determine intent from a session (e.g., very short session, only slash commands), note it briefly and move on.
- Sessions spanning midnight are already assigned to the target date by extract.py — no special handling needed, but note the actual work timespan in Day Overview if notable.
- If a project path is a long absolute path, shorten it to the last 2 path components in the output (e.g., `AdvancedSCalendarFolder/AdvancedSCalendar` → `AdvancedSCalendar`).
- The output file is the deliverable. Do not print the full reflection to the conversation.
