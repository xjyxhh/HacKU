"""B's preview, evidence, validation and persistent review workflow through HTTP."""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from dashboard_server import create_app


class ReviewApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "shared.json"
        self.client = TestClient(create_app(self.path))
        self.addCleanup(self.client.close)
        self.client.post("/api/projects", json={"id": "fintech", "name": "Team"})
        for member in ("alice", "bob"):
            self.client.post("/api/projects/fintech/members", json={"id": member, "name": member})
        self.client.post("/api/projects/fintech/tasks", json={"id": "task", "name": "Task", "task_value": 40})
        self.submit("core", "CORE")
        self.submit("support", "SUPPORT", support_value=8, helped_member_id="bob")

    def submit(self, contribution_id, kind, **fields):
        response = self.client.post("/api/projects/fintech/contributions", json={
            "id": contribution_id, "contributor_id": "alice", "task_id": "task",
            "type": kind, "description": "Implemented work", **fields,
        })
        self.assertEqual(response.status_code, 201, response.text)

    def review(self, contribution_id, decision, **fields):
        return self.client.post(f"/api/contributions/{contribution_id}/reviews", json={
            "reviewer_id": "bob", "decision": decision, **fields,
        })

    def detail(self, contribution_id):
        return self.client.get(f"/api/contributions/{contribution_id}").json()

    def assert_rejected_without_write(self, route, payload, status=400):
        before = self.path.read_bytes()
        response = self.client.post(route, json=payload)
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(self.path.read_bytes(), before)

    def test_review_page_and_assets_are_served(self):
        for path in ("/review.html", "/review.js", "/review.css"):
            self.assertEqual(self.client.get(path).status_code, 200)
        self.assertIn('href="/review.html"', self.client.get("/").text)

    def test_preview_core_uses_proposed_score_without_saving(self):
        before = self.path.read_bytes()
        response = self.client.post("/api/contributions/core/preview", json={"completion": "0.8", "quality": "0.9"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"currentScore": 0, "proposedScore": 40, "updatedScore": 28.8, "scoreChanged": True})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.detail("core")["contribution"]["status"], "PENDING")
        self.assertEqual(self.detail("core")["proposedScore"], 40)

    def test_preview_non_core_categories_and_unchanged_scores(self):
        for kind in ("SUPPORT", "REVIEW", "COORDINATION"):
            with self.subTest(kind=kind):
                contribution_id = f"preview-{kind.lower()}"
                self.submit(contribution_id, kind, support_value=8)
                route = f"/api/contributions/{contribution_id}/preview"
                before = self.path.read_bytes()
                response = self.client.post(route, json={"support_value": "6", "quality": "1.1"})
                self.assertEqual(response.json()["updatedScore"], 6.6)
                self.assertEqual(self.path.read_bytes(), before)
                self.assertFalse(self.client.post(route, json={}).json()["scoreChanged"])

    def test_invalid_preview_and_schema_errors_never_write(self):
        for payload in ({"completion": -0.1}, {"completion": 1.1}, {"quality": 2}, {"support_value": 1}):
            with self.subTest(payload=payload):
                self.assert_rejected_without_write("/api/contributions/core/preview", payload)
        self.assert_rejected_without_write("/api/contributions/support/preview", {"support_value": -1})
        self.assert_rejected_without_write("/api/contributions/core/preview", {"completion": "invalid"}, 422)
        self.assert_rejected_without_write("/api/contributions/missing/preview", {}, 404)

    def test_all_evidence_types_are_kept_after_reload(self):
        for kind, reference in (("NOTE", "Work log"), ("URL", "https://example.com"),
                                ("IMAGE", "https://example.com/work.png"),
                                ("GITHUB_PR", "https://github.com/example/repo/pull/1")):
            response = self.client.post("/api/contributions/core/evidence", json={
                "submitted_by": "alice", "kind": kind, "reference": reference,
            })
            self.assertEqual(response.status_code, 201)
        with TestClient(create_app(self.path)) as reloaded:
            record = reloaded.get("/api/contributions/core").json()
        self.assertEqual([item["kind"] for item in record["evidence"]], ["NOTE", "URL", "IMAGE", "GITHUB_PR"])
        self.assertEqual(record["currentScore"], 0)

    def test_adjust_dispute_resolve_refreshes_scores_and_graph(self):
        self.assertEqual(self.review("support", "ADJUST", support_value=6, note="Reviewed work").status_code, 200)
        dashboard = self.client.get("/api/projects/fintech/dashboard").json()
        self.assertEqual(dashboard["members"][0]["totalScore"], 6)
        self.assertEqual(dashboard["members"][0]["breakdown"]["SUPPORT"], 6)
        self.assertEqual(dashboard["members"][0]["contributionShare"], 100)
        self.assertEqual(dashboard["relationships"][0]["score"], 6)
        self.assertEqual(self.review("support", "DISPUTE", note="Attribution needs review").status_code, 200)
        preview = self.client.post("/api/contributions/support/preview", json={"support_value": 5}).json()
        self.assertEqual(preview["currentScore"], 0)
        self.assertEqual(preview["proposedScore"], 6)
        self.assertEqual(preview["updatedScore"], 5)
        dashboard = self.client.get("/api/dashboard").json()
        self.assertEqual(dashboard["members"][0]["totalScore"], 0)
        self.assertEqual(dashboard["relationships"][0]["status"], "DISPUTED")
        response = self.client.post("/api/contributions/support/resolve", json={
            "resolved_by": "bob", "resolution": "Agreed on five points", "support_value": 5,
        })
        self.assertEqual(response.status_code, 200)
        with TestClient(create_app(self.path)) as reloaded:
            dashboard = reloaded.get("/api/dashboard").json()
            record = reloaded.get("/api/contributions/support").json()
        self.assertEqual(dashboard["members"][0]["totalScore"], 5)
        self.assertEqual(dashboard["relationships"][0]["score"], 5)
        self.assertEqual(record["contribution"]["status"], "RESOLVED")
        self.assertEqual([item["decision"] for item in record["verifications"]], ["ADJUST", "DISPUTE"])
        self.assertEqual(record["disputes"][0]["reason"], "Attribution needs review")
        self.assertEqual(record["disputes"][0]["resolution"], "Agreed on five points")

    def test_core_adjustment_uses_completion(self):
        self.assertEqual(self.review("core", "ADJUST", completion="0.8").status_code, 200)
        self.assertEqual(self.detail("core")["currentScore"], 32)

    def test_self_verification_and_self_resolution_are_rejected(self):
        for decision in ("CONFIRM", "ADJUST"):
            self.assert_rejected_without_write("/api/contributions/core/reviews", {
                "reviewer_id": "alice", "decision": decision, **({"completion": 0.8} if decision == "ADJUST" else {}),
            })
        self.review("core", "DISPUTE", note="Review work")
        self.assert_rejected_without_write("/api/contributions/core/resolve", {"resolved_by": "alice", "resolution": "Self review"})

    def test_invalid_review_and_resolution_leave_file_unchanged(self):
        for payload in ({"decision": "DISPUTE", "note": " "}, {"decision": "ADJUST"},
                        {"decision": "ADJUST", "completion": 1},
                        {"decision": "ADJUST", "quality": 2},
                        {"decision": "CONFIRM", "completion": 0.8},
                        {"decision": "CONFIRM", "reviewer_id": "outsider"}):
            with self.subTest(payload=payload):
                self.assert_rejected_without_write("/api/contributions/core/reviews", {"reviewer_id": "bob", **payload})
        self.assert_rejected_without_write("/api/contributions/core/resolve", {"resolved_by": "bob", "resolution": "Not disputed"})
        self.review("core", "CONFIRM")
        self.assert_rejected_without_write("/api/contributions/core/reviews", {"reviewer_id": "bob", "decision": "CONFIRM"})
        self.review("core", "DISPUTE", note="Needs review")
        self.assert_rejected_without_write("/api/contributions/core/resolve", {"resolved_by": "bob", "resolution": " "})
        self.assert_rejected_without_write("/api/contributions/core/resolve", {"resolved_by": "bob", "resolution": "Invalid", "quality": 2})


if __name__ == "__main__":
    unittest.main()
