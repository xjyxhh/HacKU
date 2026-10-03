"""Export the canonical SQLite database as a portable JSON snapshot."""

import argparse
import json
import sqlite3
import os
import tempfile
import hashlib
from contextlib import closing
from pathlib import Path


TOKEN_TABLES = ("token_projects", "token_tasks", "commission_contracts", "ledger_events",
                "reconciliation_debts", "contract_approvals", "contract_disputes",
                "contract_resolutions")
LIFECYCLE_TABLES = ("project_lifecycle", "project_membership_state",
                    "contribution_unwind_requests", "contribution_withdrawals",
                    "membership_exit_requests", "project_lifecycle_events",
                    "unwind_outbox", "token_ledger_migrations", "project_versions",
                    "project_archive_snapshots")


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
        data["lifecycle"] = {
            table: rows(table) if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone() else []
            for table in LIFECYCLE_TABLES
        }
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
    token_paths = []
    if token_source is not None and Path(token_source).is_file():
        token_paths.append(Path(token_source))
    for project in data["projects"]:
        candidate = source.parent / "token-ledgers" / (hashlib.sha256(project["id"].encode("utf-8")).hexdigest() + ".sqlite3")
        if candidate.is_file() and candidate not in token_paths:
            token_paths.append(candidate)
    all_ledgers = {}
    for token_path in token_paths:
        with closing(sqlite3.connect(f"file:{token_path.resolve()}?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN")
            table_names={row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            token_projects=[row[0] for row in conn.execute("SELECT id FROM token_projects ORDER BY rowid")] if "token_projects" in table_names else []
            ledgers={pid:{table:[] for table in TOKEN_TABLES} for pid in token_projects}
            for table in TOKEN_TABLES:
                if table not in table_names: continue
                table_rows=[dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                for row in table_rows:
                    if "project_id" in row:
                        project_id=row["project_id"]
                    elif table in ("contract_approvals","contract_disputes","contract_resolutions"):
                        contract=conn.execute("SELECT project_id FROM commission_contracts WHERE id=?",(row.get("contract_id"),)).fetchone()
                        project_id=contract[0] if contract else None
                    else:
                        project_id=token_projects[0] if len(token_projects)==1 else None
                    if project_id in ledgers: ledgers[project_id][table].append(row)
            # The hashed project ledger is authoritative after migration. Never
            # let the retained legacy backup overwrite its newer events.
            all_ledgers.update(ledgers)
    if all_ledgers:
        data["token_ledgers"] = all_ledgers
        if len(all_ledgers) == 1:
            data["token_ledger"] = next(iter(all_ledgers.values()))
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
