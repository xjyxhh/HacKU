"""Export the canonical SQLite database as a portable JSON snapshot."""

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path


def export_json(source, destination):
    source, destination = Path(source), Path(destination)
    if not source.is_file():
        raise FileNotFoundError(source)
    with closing(sqlite3.connect(source)) as conn:
        conn.row_factory = sqlite3.Row

        def rows(table):
            return [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]

        data = {table: rows(table) for table in (
            "projects", "members", "tasks", "contributions", "evidence", "verifications", "disputes"
        )}
        for project in data["projects"]:
            project["member_ids"] = [row[0] for row in conn.execute(
                "SELECT member_id FROM project_members WHERE project_id = ? ORDER BY rowid", (project["id"],)
            )]
            project["task_ids"] = [task["id"] for task in data["tasks"]
                                   if task["project_id"] == project["id"]]
        for item in data["contributions"]:
            item["evidence_ids"] = [evidence["id"] for evidence in data["evidence"]
                                    if evidence["contribution_id"] == item["id"]]
    destination.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=Path(__file__).with_name("data.sqlite3"))
    parser.add_argument("destination", nargs="?", type=Path, default=Path(__file__).with_name("data.json"))
    args = parser.parse_args()
    export_json(args.source, args.destination)
    print(f"Exported {args.source} to {args.destination}")
