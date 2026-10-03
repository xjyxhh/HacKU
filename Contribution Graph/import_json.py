"""Copy an existing Contribution Graph JSON file into a new SQLite database."""

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from contribution_store import ContributionStore
from export_json import TOKEN_TABLES
from token_store import TokenStore


def import_json(source, destination):
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise ValueError(f"database already exists: {destination}")
    data = json.loads(source.read_text(encoding="utf-8"), parse_float=str, parse_int=str)
    token_destination = destination.with_name("token.sqlite3") if "token_ledger" in data else None
    if token_destination is not None and token_destination.exists():
        raise ValueError(f"token database already exists: {token_destination}")
    ContributionStore(destination)  # Create the schema before copying rows.
    try:
        with closing(sqlite3.connect(destination)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with conn:
                conn.executemany("INSERT INTO projects (id, name) VALUES (:id, :name)", data.get("projects", []))
                conn.executemany("INSERT INTO members (id, name) VALUES (:id, :name)", data.get("members", []))
                conn.executemany("INSERT INTO project_members (project_id, member_id) VALUES (?, ?)",
                                 ((project["id"], member_id) for project in data.get("projects", [])
                                  for member_id in project["member_ids"]))
                conn.executemany("INSERT INTO tasks (id, project_id, name, task_value, description) "
                                 "VALUES (:id, :project_id, :name, :task_value, :description)",
                                 data.get("tasks", []))
                conn.executemany("INSERT INTO contributions (id, project_id, contributor_id, task_id, "
                                 "type, description, completion, quality, support_value, status, "
                                 "helped_member_id, resolution_note) VALUES (:id, :project_id, :contributor_id, "
                                 ":task_id, :type, :description, :completion, :quality, :support_value, "
                                 ":status, :helped_member_id, :resolution_note)", data.get("contributions", []))
                conn.executemany("INSERT INTO evidence (id, contribution_id, submitted_by, kind, reference) "
                                 "VALUES (:id, :contribution_id, :submitted_by, :kind, :reference)",
                                 data.get("evidence", []))
                conn.executemany("INSERT INTO verifications (id, contribution_id, reviewer_id, decision, note) "
                                 "VALUES (:id, :contribution_id, :reviewer_id, :decision, :note)",
                                 data.get("verifications", []))
                conn.executemany("INSERT INTO disputes (id, contribution_id, raised_by, reason, resolution, "
                                 "resolved_by) VALUES (:id, :contribution_id, :raised_by, :reason, "
                                 ":resolution, :resolved_by)", data.get("disputes", []))
        ContributionStore(destination).validate_integrity()
        if token_destination is not None:
            with closing(sqlite3.connect(token_destination)) as conn:
                conn.execute("PRAGMA foreign_keys = ON")
                conn.executescript(Path(__file__).with_name("token_schema.sql").read_text(encoding="utf-8"))
                with conn:
                    for table in TOKEN_TABLES:
                        allowed = {column[1] for column in conn.execute(f"PRAGMA table_info({table})")}
                        for row in data["token_ledger"].get(table, []):
                            if set(row) != allowed:
                                raise ValueError(f"invalid token snapshot columns in {table}")
                            columns = ", ".join(row)
                            placeholders = ", ".join("?" for _ in row)
                            conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                                         tuple(row.values()))
            TokenStore(token_destination)
    except Exception:
        destination.unlink(missing_ok=True)
        if token_destination is not None:
            token_destination.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    import_json(args.source, args.destination)
    print(f"Imported {args.source} into {args.destination}")
