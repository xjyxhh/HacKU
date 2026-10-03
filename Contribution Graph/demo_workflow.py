"""Run the complete four-member Contribution Graph workflow."""

import argparse
import json
import tempfile
from pathlib import Path

from contribution_engine import demo_data
from contribution_store import ContributionStore


def run(path):
    project, members, tasks, contributions = demo_data()
    store = ContributionStore(path)
    if store.projects:
        raise ValueError("demo data file already contains projects; choose a new path")
    store.create_project(project.id, project.name)
    for member in members.values():
        store.add_member(project.id, member.id, member.name)
    for task in tasks.values():
        store.add_task(project.id, task.id, task.name, task.task_value, task.description)
    for contribution in contributions:
        store.submit_contribution(
            project.id, contribution.id, contribution.contributor_id, contribution.task_id,
            contribution.type, contribution.description,
            "1" if contribution.id == "c2" else contribution.completion,
            "4" if contribution.id == "c5" else contribution.support_value,
            contribution.helped_member_id,
        )

    def checkpoint(label, expected):
        current = ContributionStore(path)
        totals = {member_id: float(score.total_score)
                  for member_id, score in current.project_scores(project.id).items()}
        assert totals == expected, (label, totals)
        print(f"{label}: {json.dumps(totals, ensure_ascii=False)}")

    checkpoint("All submitted (PENDING)", {"alice": 0, "bob": 0, "charlie": 0, "david": 0})
    store = ContributionStore(path)
    store.add_evidence("c4", "david", "NOTE", "Deployment debugging notes")
    store.review_contribution("c1", "bob", "CONFIRM")
    store.review_contribution("c2", "alice", "ADJUST", "80% complete", completion="0.8")
    store.review_contribution("c3", "alice", "CONFIRM")
    store.review_contribution("c4", "alice", "CONFIRM")
    store.review_contribution("c5", "bob", "CONFIRM")
    checkpoint("Verified and adjusted", {"alice": 40, "bob": 20, "charlie": 3, "david": 12})
    store.review_contribution("c4", "alice", "DISPUTE", "Support value needs another review")
    checkpoint("Support disputed (excluded)", {"alice": 40, "bob": 20, "charlie": 3, "david": 4})
    store = ContributionStore(path)
    store.resolve_dispute("c4", "alice", "Agreed on 7 support points", support_value="7")
    checkpoint("Dispute resolved", {"alice": 40, "bob": 20, "charlie": 3, "david": 11})
    dashboard = ContributionStore(path).dashboard_data(project.id)
    assert dashboard["relationships"][0]["score"] == 7
    print(json.dumps(dashboard, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Keep demo data at this new SQLite path")
    args = parser.parse_args()
    if args.db:
        run(Path(args.db))
    else:
        with tempfile.TemporaryDirectory() as directory:
            run(Path(directory) / "demo.sqlite3")


if __name__ == "__main__":
    main()
