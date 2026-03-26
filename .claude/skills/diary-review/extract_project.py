"""Extract a single project's full data (including messages) from a diary JSON file."""
import json
import sys

diary_file = sys.argv[1]
project_query = sys.argv[2]  # partial match on project path

with open(diary_file) as f:
    data = json.load(f)

for project in data["projects"]:
    if project_query in project["project"]:
        print(json.dumps(project, indent=2))
        break
else:
    print(json.dumps({"error": f"No project matching '{project_query}' found"}), file=sys.stderr)
    sys.exit(1)
