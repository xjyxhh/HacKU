"""One-way migration of legacy contributions into a durable token ledger (PR4).

Reads a legacy ContributionStore database and writes the settled token view of
the same project into a separate TokenStore database, using the exact stage-1
projection rules from 融合指南.md §2.2:

- only VERIFIED / RESOLVED contributions are migrated;
- CORE / REVIEW / COORDINATION mint directly to the contributor;
- SUPPORT becomes a settled commission (principal = helped member,
  contractor = contributor, verifiedMintValue = contractPrice = legacy score);
- task mint cap = max(task_value, migrated mint total);
- treasury id = "<project_id>-treasury"; evidence key = "legacy:<id>".

Contributions that cannot be projected (pending, disputed, zero score, or
missing helped member) are collected into the report's "skipped" list instead
of failing the run. The source database is opened in SQLite read-only mode, so
the website's live data cannot be modified by a migration run.

Run from the project directory:

    .venv/bin/python migrate_token_ledger.py data.sqlite3 token.sqlite3 fintech
"""

import argparse
import json
import sqlite3
from decimal import Decimal
from pathlib import Path

from contribution_engine import ContributionType, contribution_score
from contribution_store import ContributionStore
from token_engine import TokenProject, TokenTask, ValueType
from token_store import TokenStore


def migrate_project(source_db, target_db, project_id):
    """Migrate one project into a new token ledger database.

    Returns a JSON-ready report covering migrated records, skipped
    contributions, resulting balances, and the conservation check.
    """
    source_db, target_db = Path(source_db), Path(target_db)
    if not source_db.is_file():
        raise ValueError(f"source database not found: {source_db}")
    if target_db.exists():
        raise ValueError(f"target database already exists: {target_db}; refusing to overwrite")
    # Open the legacy store through a read-only connection so migration can
    # never modify the website's live data.
    probe = sqlite3.connect(f"file:{source_db.resolve()}?mode=ro", uri=True)
    probe.close()
    store = ContributionStore(source_db, read_only=True)
    view = store.token_view(project_id)
    project = store.projects[project_id]

    ledger_project = TokenProject(
        view["project"]["id"], view["project"]["name"],
        view["project"]["treasuryId"], tuple(project.member_ids),
    )
    token = TokenStore(target_db, ledger_project)
    tasks_by_id = {task["id"]: task for task in view["tasks"]}
    for task_id in project.task_ids:
        info = tasks_by_id[task_id]
        legacy = store.tasks[task_id]
        token.add_task(TokenTask(
            task_id, project.id, legacy.name, ValueType(info["valueType"]),
            Decimal(str(info["mintCap"])), legacy.description.strip() or legacy.name,
        ))

    contributions = {item.id: item for item in store.contributions.values()
                     if item.project_id == project_id}
    migrated = []

    def settle_contract(item, legacy_id):
        contract = next(c for c in view["contracts"] if c["id"] == f"{legacy_id}:commission")
        token.create_commission(
            contract["id"], item.task_id, contract["principalId"], contract["contractorId"],
            str(Decimal(str(contract["contractPrice"]))),
            str(Decimal(str(contract["maximumMintValue"]))),
        )
        for status in ("OFFERED", "ACCEPTED", "CREDIT_RESERVED", "DELIVERED", "VERIFIED"):
            token.advance_contract(contract["id"], status)
        approvers = [member_id for member_id in project.member_ids
                     if member_id not in (contract["principalId"], contract["contractorId"])]
        token.settle_commission(contract["id"], str(Decimal(str(contract["verifiedMintValue"]))),
                                [f"legacy:{legacy_id}"], approvers[:1])
        return {"contributionId": legacy_id, "kind": "COMMISSION",
                "contractId": contract["id"]}

    # Process contributions in stored rowid order, exactly like the stage-1
    # projection, so the migrated event order matches the token-view order.
    for item in contributions.values():
        if item.status not in ("VERIFIED", "RESOLVED"):
            continue
        if item.type == ContributionType.SUPPORT and item.helped_member_id is None:
            continue
        amount = contribution_score(item, project, store.members, store.tasks)
        if amount <= 0:
            continue
        if item.type == ContributionType.SUPPORT:
            migrated.append(settle_contract(item, item.id))
        else:
            token.mint_direct(f"{item.id}:mint", item.task_id, item.contributor_id,
                              str(amount), [f"legacy:{item.id}"])
            migrated.append({"contributionId": item.id, "kind": "DIRECT",
                             "eventId": f"{item.id}:mint"})

    payload = token.ledger_payload()
    skipped = view["skipped"]
    skip_reasons_ok = all(
        item["reason"].startswith("状态") or item["reason"].startswith("有效得分")
        for item in skipped
    )
    report = {
        "projectId": project_id,
        "source": str(source_db),
        "target": str(target_db),
        "migrated": migrated,
        "skipped": skipped,
        "balances": payload["balances"],
        "totalSupply": payload["totalSupply"],
        "oldTeamTotal": view["oldTeamTotal"],
        "conservation": (abs(Decimal(str(payload["totalSupply"]))
                             - Decimal(str(view["oldTeamTotal"]))) < Decimal("0.000000001"))
                        and skip_reasons_ok,
    }
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="legacy ContributionStore database (read-only)")
    parser.add_argument("target", type=Path, help="new token ledger database (must not exist)")
    parser.add_argument("project_id", help="project to migrate, e.g. fintech")
    args = parser.parse_args()
    report = migrate_project(args.source, args.target, args.project_id)
    print(json.dumps(report, ensure_ascii=False, indent=2))
