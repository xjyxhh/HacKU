"""Back up contribution and Token SQLite files, then rehearse restoration.

Stop application writes before running this command. Every database is backed
up with SQLite's Backup API, checked, and restored into a separate test folder.
"""

import argparse
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

from contribution_store import ContributionStore
from token_store import TokenStore


def backup_and_rehearse(data_db: Path, destination: Path):
    data_db = Path(data_db)
    destination = Path(destination)
    if not data_db.is_file():
        raise FileNotFoundError(data_db)
    if destination.exists():
        raise ValueError(f"backup directory already exists: {destination}")
    destination.mkdir(parents=True)
    source_files = [data_db]
    legacy = data_db.with_name("token.sqlite3")
    if legacy.is_file():
        source_files.append(legacy)
    token_root = data_db.parent / "token-ledgers"
    if token_root.is_dir():
        source_files.extend(sorted(token_root.glob("*.sqlite3")))
    manifest = []
    for source in source_files:
        relative = Path("token-ledgers") / source.name if source.parent == token_root else Path(source.name)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as src, sqlite3.connect(target) as dst:
            src.backup(dst)
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError(f"integrity check failed: {target}")
        manifest.append({"file": str(relative), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    rehearsal = destination / "restore-rehearsal"
    for item in manifest:
        source = destination / item["file"]
        target = rehearsal / item["file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        with sqlite3.connect(target) as conn:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError(f"restoration integrity check failed: {target}")
    restored = ContributionStore(rehearsal / data_db.name)
    project_ids = sorted(restored.projects)
    token_balances = {}
    for item in manifest:
        if item["file"].endswith("token.sqlite3") or item["file"].startswith("token-ledgers/"):
            ledger = TokenStore(rehearsal / item["file"])
            token_balances[ledger.project.id] = {
                "events": len(ledger.ledger.events),
                "balancesExact": {member: str(amount) for member, amount in ledger.balances().items()},
                "debts": ledger.debts_payload(),
            }
    result = {"projects": project_ids, "tokenLedgers": token_balances, "files": manifest}
    (destination / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_db", type=Path)
    parser.add_argument("destination", type=Path, help="new backup directory; must not exist")
    args = parser.parse_args()
    result = backup_and_rehearse(args.data_db, args.destination)
    print(json.dumps(result, ensure_ascii=False, indent=2))
