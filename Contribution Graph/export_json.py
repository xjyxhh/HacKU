"""Export the canonical SQLite database as a portable JSON snapshot."""

import argparse
import json
import sqlite3
import os
import tempfile
from contextlib import closing
from pathlib import Path


TOKEN_TABLES = ("token_projects", "token_tasks", "commission_contracts", "ledger_events",
                "reconciliation_debts")


def export_json(source, destination, token_source=None):
    source, destination = Path(source), Path(destination)
    if not source.is_file():
        raise FileNotFoundError(source)
    with closing(sqlite3.connect(source)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN")  # Keep all legacy tables from one committed snapshot.
        token_in_source = bool(conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='token_projects'"
        ).fetchone())

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
    if token_source is None:
        if token_in_source:
            token_source = source
        elif source.name == "data.sqlite3":
            token_source = source.with_name("token.sqlite3")
    if token_source is not None and Path(token_source).is_file():
        with closing(sqlite3.connect(f"file:{Path(token_source).resolve()}?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN")
            data["token_ledger"] = {
                table: ([dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                                        (table,)).fetchone() else [])
                for table in TOKEN_TABLES
            }
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=Path(__file__).with_name("data.sqlite3"))
    parser.add_argument("destination", nargs="?", type=Path, default=Path(__file__).with_name("data.json"))
    parser.add_argument("--token-db", type=Path, help="optional token ledger to include")
    args = parser.parse_args()
    export_json(args.source, args.destination, args.token_db)
    print(f"Exported {args.source} to {args.destination}")
