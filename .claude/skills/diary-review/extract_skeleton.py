"""Extract diary skeleton (projects, sessions, stats — no messages) for lightweight analysis."""
import json
import sys

diary_file = sys.argv[1]

with open(diary_file) as f:
    data = json.load(f)

summary = {
    "date": data["date"],
    "stats": data["stats"],
    "projects": [
        {
            "project": p["project"],
            "session_count": len(p["sessions"]),
            "sessions": [
                {
                    "summary": s.get("summary", "")[:150],
                    "time_range": s["time_range"],
                    "git_branch": s.get("git_branch", ""),
                }
                for s in p["sessions"]
            ],
        }
        for p in data["projects"]
    ],
}

print(json.dumps(summary, indent=2))
