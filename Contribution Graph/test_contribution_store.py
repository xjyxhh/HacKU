"""Persistence and submission checks for the local Contribution Graph store."""

import tempfile
import unittest
import json
import sqlite3
from contextlib import closing
from decimal import Decimal
from pathlib import Path

from contribution_engine import ContributionStatus, ContributionType
from contribution_store import ContributionStore


class ContributionStoreTests(unittest.TestCase):
    def test_create_submit_and_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "data.sqlite3"
            store = ContributionStore(path)
            store.create_project("fintech", "FinTech Contribution Graph")
            store.add_member("fintech", "alice", "Alice")
            store.add_member("fintech", "david", "David")
            store.add_task("fintech", "deployment", "Deployment", "20", "Deploy the app")
            contribution = store.submit_contribution(
                "fintech", "c1", "david", "deployment", "SUPPORT", "Helped debug",
                support_value="8", helped_member_id="alice",
            )

            self.assertEqual(contribution.status, ContributionStatus.PENDING)
            self.assertEqual(store.project_scores("fintech")["david"].total_score, 0)
            reloaded = ContributionStore(path)
            self.assertEqual(reloaded.projects["fintech"].member_ids, ["alice", "david"])
            self.assertEqual(reloaded.projects["fintech"].task_ids, ["deployment"])
            self.assertEqual(reloaded.tasks["deployment"].task_value, Decimal("20"))
            self.assertEqual(reloaded.contributions["c1"].type, ContributionType.SUPPORT)
            self.assertEqual(reloaded.contributions["c1"].helped_member_id, "alice")
            self.assertEqual(reloaded.contributions["c1"].status, ContributionStatus.PENDING)
            self.assertEqual(reloaded.project_scores("fintech")["david"].total_score, 0)

    def test_invalid_submission_does_not_change_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.sqlite3"
            store = ContributionStore(path)
            store.create_project("p", "Project")
            store.add_member("p", "alice", "Alice")
            store.add_task("p", "task", "Task", "10")
            with self.assertRaisesRegex(ValueError, "helped member"):
                store.submit_contribution("p", "c1", "alice", "task", "SUPPORT", "Helped",
                                          support_value="2", helped_member_id="unknown")
            with self.assertRaisesRegex(ValueError, "finite"):
                store.add_task("p", "bad", "Bad", "NaN")
            with self.assertRaisesRegex(ValueError, "new"):
                store.add_member("p", "alice", "Duplicate")
            self.assertEqual(ContributionStore(path).contributions, {})
            self.assertEqual(store.contributions, {})

    def test_review_dispute_resolution_and_dashboard(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.sqlite3"
            store = ContributionStore(path)
            store.create_project("p", "Project")
            store.add_member("p", "alice", "Alice")
            store.add_member("p", "bob", "Bob")
            store.add_task("p", "task", "Task", "20")
            store.submit_contribution("p", "core", "alice", "task", "CORE", "Built feature")
            store.submit_contribution("p", "help", "bob", "task", "SUPPORT", "Helped Alice",
                                      support_value="8", helped_member_id="alice")
            evidence = store.add_evidence("help", "bob", "NOTE", "Pair programming notes")
            self.assertIn(evidence.id, store.contributions["help"].evidence_ids)

            store.review_contribution("core", "bob", "CONFIRM")
            store.review_contribution("help", "alice", "ADJUST", "Agreed value", support_value="6")
            self.assertEqual(store.project_scores("p")["bob"].total_score, Decimal("6"))
            store.review_contribution("help", "alice", "DISPUTE", "Need to revisit attribution")
            self.assertEqual(store.project_scores("p")["bob"].total_score, 0)
            with self.assertRaisesRegex(ValueError, "pending"):
                store.review_contribution("help", "alice", "CONFIRM")
            with self.assertRaisesRegex(ValueError, "own contribution"):
                store.resolve_dispute("help", "bob", "Self resolution")
            store.resolve_dispute("help", "alice", "Confirmed 5 points", support_value="5")

            reloaded = ContributionStore(path)
            self.assertEqual(reloaded.contributions["help"].status, ContributionStatus.RESOLVED)
            self.assertEqual(reloaded.contributions["help"].support_value, Decimal("5"))
            self.assertEqual(len(reloaded.verifications), 3)
            self.assertEqual(len(reloaded.disputes), 1)
            self.assertEqual(next(iter(reloaded.disputes.values())).resolution, "Confirmed 5 points")
            record = reloaded.contribution_data("help")
            self.assertEqual(record["contribution"]["support_value"], "5")
            self.assertEqual(len(record["evidence"]), 1)
            self.assertEqual(len(record["verifications"]), 2)
            self.assertEqual(len(record["disputes"]), 1)
            json.dumps(record)
            dashboard = reloaded.dashboard_data("p")
            self.assertEqual([(member["id"], member["totalScore"]) for member in dashboard["members"]],
                             [("alice", 20.0), ("bob", 5.0)])
            self.assertEqual(dashboard["members"][1]["contributionShare"], 20.0)
            self.assertEqual(dashboard["members"][1]["breakdown"]["SUPPORT"], 5.0)
            self.assertEqual(dashboard["relationships"][0]["fromMemberId"], "bob")
            self.assertEqual(dashboard["relationships"][0]["toMemberId"], "alice")
            self.assertEqual(dashboard["relationships"][0]["taskId"], "task")
            self.assertEqual(dashboard["relationships"][0]["score"], 5.0)
            json.dumps(dashboard)

    def test_invalid_review_does_not_change_score_or_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.sqlite3"
            store = ContributionStore(path)
            store.create_project("p", "Project")
            store.add_member("p", "alice", "Alice")
            store.add_member("p", "bob", "Bob")
            store.add_task("p", "task", "Task", "20")
            store.submit_contribution("p", "core", "alice", "task", "CORE", "Built feature")
            store.submit_contribution("p", "support", "alice", "task", "SUPPORT", "Helped",
                                      support_value="2")
            with self.assertRaisesRegex(ValueError, "requires a score change"):
                store.review_contribution("core", "bob", "ADJUST")
            with self.assertRaisesRegex(ValueError, "quality"):
                store.review_contribution("core", "bob", "ADJUST", quality="2")
            with self.assertRaisesRegex(ValueError, "score change"):
                store.review_contribution("core", "bob", "ADJUST", completion="1")
            with self.assertRaisesRegex(ValueError, "score change"):
                store.review_contribution("support", "bob", "ADJUST", completion="0.5")
            with self.assertRaisesRegex(ValueError, "own contribution"):
                store.review_contribution("core", "alice", "CONFIRM")
            with self.assertRaisesRegex(ValueError, "reason"):
                store.review_contribution("core", "alice", "DISPUTE")
            self.assertEqual(ContributionStore(path).contributions["core"].status, ContributionStatus.PENDING)
            self.assertEqual(store.contributions["core"].status, ContributionStatus.PENDING)
            self.assertEqual(store.contributions["support"].status, ContributionStatus.PENDING)

    def test_failed_transaction_restores_store_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.sqlite3"
            store = ContributionStore(path)
            store.create_project("p", "Project")
            with closing(sqlite3.connect(path)) as conn:
                with conn:
                    conn.execute("CREATE TRIGGER fail_membership BEFORE INSERT ON project_members "
                                 "BEGIN SELECT RAISE(ABORT, 'write failed'); END")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "write failed"):
                store.add_member("p", "alice", "Alice")
            self.assertEqual(store.projects["p"].member_ids, [])
            self.assertNotIn("alice", store.members)
            self.assertNotIn("alice", ContributionStore(path).members)
            with closing(sqlite3.connect(path)) as conn:
                with conn:
                    conn.execute("DROP TRIGGER fail_membership")
            store.add_member("p", "bob", "Bob")
            self.assertEqual(ContributionStore(path).projects["p"].member_ids, ["bob"])

    def test_foreign_key_rejects_unknown_project(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.sqlite3"
            store = ContributionStore(path)
            store.create_project("p", "Project")
            with store._connect() as conn:
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute("INSERT INTO tasks (id, project_id, name, task_value) "
                                 "VALUES ('task', 'missing', 'Task', '10')")
            self.assertEqual(ContributionStore(path).tasks, {})


if __name__ == "__main__":
    unittest.main()
