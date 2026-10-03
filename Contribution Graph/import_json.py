"""Copy an existing Contribution Graph JSON file into a new SQLite database."""

import argparse
import json
import hashlib
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
    ledgers=data.get("token_ledgers")
    if not isinstance(ledgers,dict):
        legacy=data.get("token_ledger")
        if legacy:
            projects=legacy.get("token_projects",[])
            if len(projects)!=1: raise ValueError("legacy token snapshot must contain exactly one project")
            ledgers={projects[0]["id"]:legacy}
        else: ledgers={}
    known_projects={project["id"] for project in data.get("projects",[])}
    for project_id,ledger_data in ledgers.items():
        if project_id not in known_projects or [row.get("id") for row in ledger_data.get("token_projects",[])] != [project_id]:
            raise ValueError(f"token snapshot project does not match contribution project: {project_id}")
    token_root=destination.parent / "token-ledgers"
    token_paths={project_id:token_root / f"{hashlib.sha256(project_id.encode('utf-8')).hexdigest()}.sqlite3" for project_id in ledgers}
    legacy_token=data.get("token_ledger")
    legacy_project_id=(legacy_token.get("token_projects") or [{}])[0].get("id") if legacy_token else None
    token_destination=destination.with_name("token.sqlite3") if legacy_project_id and legacy_project_id in token_paths else None
    if token_destination is not None and token_destination.exists():
        raise ValueError(f"token database already exists: {token_destination}")
    existing_path=next((path for path in token_paths.values() if path.exists()),None)
    if existing_path: raise ValueError(f"token ledger already exists: {existing_path}")
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
                conn.executescript(Path(__file__).with_name("lifecycle_schema.sql").read_text(encoding="utf-8"))
                lifecycle=data.get("lifecycle",{})
                # The schema seeds ACTIVE defaults for older snapshots. Replace
                # those defaults with the exported lifecycle state when present.
                for seeded_table in ("project_lifecycle","project_membership_state","project_versions"):
                    if lifecycle.get(seeded_table): conn.execute(f"DELETE FROM {seeded_table}")
                for table in ("project_lifecycle","project_membership_state","contribution_unwind_requests",
                              "contribution_withdrawals","membership_exit_requests","project_lifecycle_events",
                              "unwind_outbox","token_ledger_migrations","project_versions","project_archive_snapshots"):
                    rows=lifecycle.get(table,[])
                    if not rows: continue
                    columns={column[1] for column in conn.execute(f"PRAGMA table_info({table})")}
                    for row in rows:
                        clean={key:value for key,value in row.items() if key in columns}
                        names=", ".join(clean)
                        placeholders=", ".join("?" for _ in clean)
                        conn.execute(f"INSERT INTO {table} ({names}) VALUES ({placeholders})",tuple(clean.values()))
        token_root.mkdir(parents=True,exist_ok=True) if token_paths else None
        for project_id,ledger_data in ledgers.items():
            token_path=token_paths[project_id]
            with closing(sqlite3.connect(token_path)) as conn:
                conn.execute("PRAGMA foreign_keys = ON")
                conn.executescript(Path(__file__).with_name("token_schema.sql").read_text(encoding="utf-8"))
                with conn:
                    for table in TOKEN_TABLES:
                        for row in ledger_data.get(table,[]):
                            allowed={column[1] for column in conn.execute(f"PRAGMA table_info({table})")}
                            clean={key:value for key,value in row.items() if key in allowed}
                            if set(clean)!=set(row): raise ValueError(f"invalid token snapshot columns in {table}")
                            columns=", ".join(clean); placeholders=", ".join("?" for _ in clean)
                            conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",tuple(clean.values()))
            TokenStore(token_path)
        if legacy_project_id:
            ledger_path=token_paths[legacy_project_id]
            with sqlite3.connect(ledger_path) as token_conn:
                event_count=token_conn.execute("SELECT count(*) FROM ledger_events").fetchone()[0]
                last_row=token_conn.execute("SELECT id FROM ledger_events ORDER BY sequence DESC LIMIT 1").fetchone()
            with sqlite3.connect(destination) as conn:
                conn.execute("INSERT OR IGNORE INTO token_ledger_migrations(project_id,source_path,target_path,source_event_count,last_event_id) VALUES(?,?,?,?,?)",(legacy_project_id,str(token_destination or ledger_path),str(ledger_path),event_count,last_row[0] if last_row else None))
        ContributionStore(destination).validate_integrity()
        if token_destination is not None:
            with closing(sqlite3.connect(token_paths[legacy_project_id])) as token_source, closing(sqlite3.connect(token_destination)) as token_target:
                token_source.backup(token_target)
            TokenStore(token_destination)
    except Exception:
        destination.unlink(missing_ok=True)
        if token_destination is not None:
            token_destination.unlink(missing_ok=True)
        for path in token_paths.values(): path.unlink(missing_ok=True)
        if token_paths: token_root.rmdir() if token_root.exists() and not any(token_root.iterdir()) else None
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    import_json(args.source, args.destination)
    print(f"Imported {args.source} into {args.destination}")
