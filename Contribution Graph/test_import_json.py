"""Check that existing JSON data migrates without changing scores or history."""

import json
import tempfile
import unittest
from pathlib import Path

from contribution_store import ContributionStore
from import_json import import_json


class JsonImportTests(unittest.TestCase):
    def test_import_preserves_merged_data(self):
        source = Path(__file__).with_name("data.json")
        original = json.loads(source.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "data.sqlite3"
            import_json(source, destination)
            store = ContributionStore(destination)
            self.assertEqual(len(store.contributions), len(original["contributions"]))
            self.assertEqual(len(store.verifications), len(original["verifications"]))
            self.assertEqual(len(store.disputes), len(original["disputes"]))
            self.assertEqual({id: score.total_score for id, score in store.project_scores("fintech").items()},
                             {"alice": 40, "bob": 20, "charlie": 0, "david": 7})
            self.assertEqual(store.contributions["c4"].resolution_note, "Agreed on 7 support points")
            self.assertEqual(store.contributions["merged-c1"].contributor_id, "alice")
            self.assertEqual(store.contributions["c1"].contributor_id, "david")
            self.assertEqual(next(item.contribution_id for item in store.verifications.values()
                                  if item.reviewer_id == "bob" and item.decision.value == "CONFIRM"),
                             "merged-c1")
            with self.assertRaisesRegex(ValueError, "already exists"):
                import_json(source, destination)


if __name__ == "__main__":
    unittest.main()
