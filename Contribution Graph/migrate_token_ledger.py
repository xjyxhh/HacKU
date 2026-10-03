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
        raise ValueError("source database not found")
    if target_db.exists() and (not target_db.is_file() or target_db.stat().st_size != 0):
        raise ValueError("target database already exists; refusing to overwrite")
    # Open the legacy store through a read-only connection so migration can
    # never modify the website's live data.
    probe = sqlite3.connect(f"file:{source_db.resolve()}?mode=ro", uri=True)
    probe.close()
    store = ContributionStore(source_db, read_only=True)
    view = store.token_view(project_id)
    project = store.projects[project_id]
    rejected = [item for item in view["skipped"]
                if item["status"] in ("VERIFIED", "RESOLVED")
                and not item["reason"].startswith("有效得分为 0")]
    if rejected:
        raise ValueError(f"cannot migrate verified contributions: {rejected}")

    ledger_project = TokenProject(
        view["project"]["id"], view["project"]["name"],
        view["project"]["treasuryId"], tuple(project.member_ids),
    )
    token = TokenStore(target_db, ledger_project)
    tasks_by_id = {task["id"]: task for task in view["tasks"]}
    skipped_ids = {item["contributionId"] for item in view["skipped"]}
    contributions = {item.id: item for item in store.contributions.values()
                     if item.project_id == project_id}
    mint_totals = {task_id: Decimal("0") for task_id in project.task_ids}
    for item in contributions.values():
        if item.id not in skipped_ids:
            mint_totals[item.task_id] += contribution_score(
                item, project, store.members, store.tasks,
            )
    for task_id in project.task_ids:
        info = tasks_by_id[task_id]
        legacy = store.tasks[task_id]
        token.add_task(TokenTask(
            task_id, project.id, legacy.name, ValueType(info["valueType"]),
            max(legacy.task_value, mint_totals[task_id]),
            legacy.description.strip() or legacy.name,
        ))
    migrated = []

    def settle_contract(item, amount):
        contract_id = f"{item.id}:commission"
        token.create_commission(
            contract_id, item.task_id, item.helped_member_id, item.contributor_id,
            amount, amount,
        )
        for status in ("OFFERED", "ACCEPTED", "CREDIT_RESERVED", "DELIVERED", "VERIFIED"):
            token.advance_contract(contract_id, status)
        token.settle_commission(contract_id, amount,
                                [f"legacy:{item.id}"], [store._legacy_token_approver(item)])
        return {"contributionId": item.id, "kind": "COMMISSION",
                "contractId": contract_id}

    # Process contributions in stored rowid order, exactly like the stage-1
    # projection, so the migrated event order matches the token-view order.
    for item in contributions.values():
        if item.id in skipped_ids:
            continue
        amount = contribution_score(item, project, store.members, store.tasks)
        if (item.type == ContributionType.SUPPORT and item.helped_member_id is not None
                and store._legacy_token_approver(item)):
            migrated.append(settle_contract(item, amount))
        else:
            token.mint_direct(f"{item.id}:mint", item.task_id, item.contributor_id,
                              str(amount), [f"legacy:{item.id}"])
            migrated.append({"contributionId": item.id, "kind": "DIRECT",
                             "eventId": f"{item.id}:mint",
                             **({"reason": "历史审核没有独立批准人，保留已核验贡献并直接铸币"}
                                if item.type == ContributionType.SUPPORT and item.helped_member_id
                                else {})})

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
        "totalSupplyExact": str(token.total_supply()),
        "oldTeamTotalExact": str(sum(
            (contribution_score(item, project, store.members, store.tasks)
             for item in contributions.values()), Decimal("0"))),
        "conservation": token.total_supply() == sum(
            (contribution_score(item, project, store.members, store.tasks)
             for item in contributions.values()), Decimal("0")) and skip_reasons_ok,
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
