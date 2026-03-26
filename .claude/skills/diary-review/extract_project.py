"""Extract a single project's full data (including messages) from a diary JSON file.

Usage: python3 extract_project.py <diary_file> <project_query> <output_file>
"""
import json
import sys

diary_file = sys.argv[1]
project_query = sys.argv[2]
output_file = sys.argv[3]

with open(diary_file) as f:
    data = json.load(f)

for project in data["projects"]:
    if project_query in project["project"]:
        with open(output_file, "w") as out:
            json.dump(project, out, indent=2)
        print(f"OK {output_file}")
        break
else:
    print(f"No project matching '{project_query}' found")
    sys.exit(1)
