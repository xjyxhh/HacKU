"""Check that database consolidation preserves colliding contribution history."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from contribution_store import ContributionStore
from merge_sqlite import merge
from seed_dashboard import seed


class MergeSqliteTests(unittest.TestCase):
    def test_merge_keeps_both_c1_records_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "data.sqlite3"
            source = Path(directory) / "sample.sqlite3"
            store = ContributionStore(target)
            store.create_project("fintech", "FinTech group contribution ledger")
            store.add_member("fintech", "alice", "Alice")
            store.add_member("fintech", "david", "David")
            store.add_task("fintech", "deployment", "Deployment", "20", "Deploy the application")
            store.submit_contribution("fintech", "c1", "david", "deployment", "SUPPORT",
                                      "Helped Alice debug deployment issues", support_value="8", helped_member_id="alice")
            seed(source)

            backup, archive, renamed = merge(target, source)
            self.assertTrue(backup.is_file())
            self.assertTrue(archive.is_file())
            self.assertFalse(source.exists())
            self.assertEqual(renamed, {"c1": "merged-c1"})
            merged = ContributionStore(target)
            self.assertEqual((len(merged.members), len(merged.tasks), len(merged.contributions)), (4, 4, 6))
            self.assertEqual(merged.contributions["c1"].contributor_id, "david")
            self.assertEqual(merged.contributions["merged-c1"].contributor_id, "alice")
            self.assertEqual(len(merged.contribution_data("merged-c1")["verifications"]), 1)
            with sqlite3.connect(target) as conn:
                self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
