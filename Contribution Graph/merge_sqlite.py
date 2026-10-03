"""Merge two Contribution Graph databases into one, preserving every contribution."""

import argparse
import os
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from contribution_store import ContributionStore


TABLES = (
    "projects", "members", "project_members", "tasks", "contributions",
    "evidence", "verifications", "disputes",
)


def rows(conn, table):
    return [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]


def insert(conn, table, row):
    columns = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({marks})", tuple(row.values()))


def unique_id(conn, table, old_id):
    candidate = f"merged-{old_id}"
    suffix = 2
    while conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (candidate,)).fetchone():
        candidate = f"merged-{old_id}-{suffix}"
        suffix += 1
    return candidate


def merge(target, source):
    target, source = Path(target), Path(source)
    if target.resolve() == source.resolve() or not target.is_file() or not source.is_file():
        raise ValueError("target and source must be two existing, different SQLite files")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target_backup = target.with_name(f"{target.stem}.before-merge-{stamp}{target.suffix}")
    source_archive = source.with_name(f"{source.stem}.before-merge-{stamp}{source.suffix}")
    working = target.with_name(f"{target.stem}.merging-{stamp}{target.suffix}")
    for path in (target_backup, source_archive, working):
        if path.exists():
            raise FileExistsError(path)

    # Work on a copy. Keep both original databases until the merge is validated.
    with closing(sqlite3.connect(target)) as original, closing(sqlite3.connect(target_backup)) as backup:
        original.backup(backup)
    shutil.copy2(target_backup, working)
    renames = {}
    try:
        with closing(sqlite3.connect(source)) as incoming, closing(sqlite3.connect(working)) as combined:
            incoming.row_factory = sqlite3.Row
            combined.row_factory = sqlite3.Row
            combined.execute("PRAGMA foreign_keys = ON")
            with combined:
                for table in TABLES:
                    for row in rows(incoming, table):
                        if table == "project_members":
                            existing = combined.execute(
                                "SELECT 1 FROM project_members WHERE project_id = ? AND member_id = ?",
                                (row["project_id"], row["member_id"]),
                            ).fetchone()
                            if not existing:
                                insert(combined, table, row)
                            continue
                        if "contribution_id" in row:
                            row["contribution_id"] = renames.get(row["contribution_id"], row["contribution_id"])
                        existing = combined.execute(f"SELECT * FROM {table} WHERE id = ?", (row["id"],)).fetchone()
                        if existing is None:
                            insert(combined, table, row)
                        elif dict(existing) == row:
                            continue
                        elif table == "tasks" and all(
                            existing[key] == row[key] for key in ("id", "project_id", "name", "task_value")
                        ) and not (existing["description"] and row["description"]):
                            combined.execute("UPDATE tasks SET description = ? WHERE id = ?",
                                             (existing["description"] or row["description"], row["id"]))
                        elif table in ("contributions", "evidence", "verifications", "disputes"):
                            old_id = row["id"]
                            row["id"] = unique_id(combined, table, old_id)
                            if table == "contributions":
                                renames[old_id] = row["id"]
                            insert(combined, table, row)
                        else:
                            raise ValueError(f"conflicting {table} id: {row['id']}")
                violations = combined.execute("PRAGMA foreign_key_check").fetchall()
                if violations or combined.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError(f"merged database failed integrity check: {violations}")
        ContributionStore(working, read_only=True).validate_integrity()
        os.replace(working, target)
        os.replace(source, source_archive)
    finally:
        working.unlink(missing_ok=True)
    return target_backup, source_archive, renames


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="canonical database to update")
    parser.add_argument("source", type=Path, help="database to merge and archive")
    args = parser.parse_args()
    backup, archive, renamed = merge(args.target, args.source)
    print(f"Merged into {args.target}; original target: {backup}; source archive: {archive}")
    for old, new in renamed.items():
        print(f"Renamed conflicting contribution {old} to {new}")
