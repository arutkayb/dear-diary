"""Extract a single project's diary data as readable text (not JSON).

Usage: python3 extract_project.py <diary_file> <project_query> <output_file>

Outputs a plain text file that can be read directly without parsing.
"""
import json
import sys

diary_file = sys.argv[1]
project_query = sys.argv[2]
output_file = sys.argv[3]

with open(diary_file) as f:
    data = json.load(f)

project = None
for p in data["projects"]:
    if project_query in p["project"]:
        project = p
        break

if not project:
    print(f"No project matching '{project_query}' found")
    sys.exit(1)

lines = []
lines.append(f"# Project: {project['project']}")
lines.append(f"Sessions: {len(project['sessions'])}")
lines.append("")

for i, session in enumerate(project["sessions"], 1):
    tr = session.get("time_range", {})
    start = tr.get("start", "?")[:16]
    end = tr.get("end", "?")[:16]
    branch = session.get("git_branch", "?")
    summary = session.get("summary", "(no summary)")[:200]
    messages = session.get("messages", [])

    lines.append(f"{'='*60}")
    lines.append(f"## Session {i}/{len(project['sessions'])} ({start} to {end}, branch: {branch})")
    lines.append(f"Summary: {summary}")
    lines.append(f"Messages: {len(messages)}")
    lines.append("")

    for msg in messages:
        role = msg.get("role", "?")
        text = msg.get("text", "")
        # Truncate very long messages to keep file manageable
        if len(text) > 1000:
            text = text[:1000] + f"... [truncated, {len(text)} chars total]"
        lines.append(f"[{role}] {text}")
        lines.append("")

with open(output_file, "w") as out:
    out.write("\n".join(lines))

print(f"OK {output_file}")
