"""Create a repeatable four-member dataset for the C dashboard."""

import argparse
from pathlib import Path

from contribution_engine import demo_data
from contribution_store import ContributionStore


def seed(path):
    path = Path(path)
    if path.exists():
        raise ValueError(f"data file already exists: {path}")
    project, members, tasks, contributions = demo_data()
    store = ContributionStore(path)
    store.create_project(project.id, project.name)
    for member in members.values():
        store.add_member(project.id, member.id, member.name)
    for task in tasks.values():
        store.add_task(project.id, task.id, task.name, task.task_value, task.description)
    for item in contributions:
        store.submit_contribution(
            project.id, item.id, item.contributor_id, item.task_id,
            item.type.value, item.description,
            completion="1" if item.id == "c2" else item.completion,
            support_value="4" if item.id == "c5" else item.support_value,
            helped_member_id=item.helped_member_id,
        )
    store.review_contribution("c1", "bob", "CONFIRM")
    store.review_contribution("c2", "alice", "ADJUST", "80% complete", completion="0.8")
    store.review_contribution("c4", "alice", "CONFIRM")
    store.review_contribution("c4", "alice", "DISPUTE", "Support value needs another review")
    store.resolve_dispute("c4", "alice", "Agreed on 7 support points", support_value="7")
    store.review_contribution("c5", "bob", "DISPUTE", "Coordination needs verification")
    return store.dashboard_data(project.id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default=Path(__file__).with_name("demo.json"), type=Path)
    args = parser.parse_args()
    data = seed(args.path)
    print(f"Created {args.path} with {len(data['members'])} members, "
          f"{len(data['tasks'])} tasks, and {len(data['contributions'])} contributions")
