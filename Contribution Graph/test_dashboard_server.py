"""Check the FastAPI route through a complete contribution workflow."""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from dashboard_server import create_app


class DashboardApiTests(unittest.TestCase):
    def test_dashboard_and_review_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            client = TestClient(create_app(Path(directory) / "data.sqlite3"))
            self.assertEqual(client.get("/").status_code, 200)
            self.assertEqual(client.get("/docs").status_code, 200)
            self.assertEqual(client.post("/api/projects", json={"id": "fintech", "name": "Project"}).status_code, 201)
            for member in ("alice", "bob"):
                self.assertEqual(client.post("/api/projects/fintech/members",
                                             json={"id": member, "name": member}).status_code, 201)
            self.assertEqual(client.post("/api/projects/fintech/tasks",
                                         json={"id": "task", "name": "Task", "task_value": 20}).status_code, 201)
            response = client.post("/api/projects/fintech/contributions", json={
                "id": "c1", "contributor_id": "alice", "task_id": "task",
                "type": "CORE", "description": "Built feature",
            })
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json()["status"], "PENDING")
            self.assertEqual(client.post("/api/contributions/c1/evidence", json={
                "submitted_by": "alice", "kind": "NOTE", "reference": "Work log",
            }).status_code, 201)
            self.assertEqual(len(client.get("/api/contributions/c1").json()["evidence"]), 1)
            self.assertEqual(client.get("/api/dashboard").json()["members"][0]["totalScore"], 0)
            self.assertEqual(client.get("/api/contributions/missing").status_code, 404)
            self.assertEqual(client.post("/api/contributions/c1/reviews", json={
                "reviewer_id": "alice", "decision": "CONFIRM",
            }).status_code, 400)
            self.assertEqual(client.post("/api/contributions/c1/reviews", json={
                "reviewer_id": "bob", "decision": "CONFIRM",
            }).status_code, 200)
            self.assertEqual(client.get("/api/dashboard").json()["members"][0]["totalScore"], 20)
            self.assertEqual(client.post("/api/contributions/c1/reviews", json={
                "reviewer_id": "bob", "decision": "DISPUTE", "note": "Review again",
            }).status_code, 200)
            self.assertEqual(client.get("/api/dashboard").json()["members"][0]["totalScore"], 0)
            self.assertEqual(client.post("/api/contributions/c1/resolve", json={
                "resolved_by": "bob", "resolution": "Half complete", "completion": "0.5",
            }).status_code, 200)
            self.assertEqual(client.get("/api/projects/fintech/dashboard").json()["members"][0]["totalScore"], 10)
            self.assertEqual(len(client.get("/api/contributions/c1").json()["disputes"]), 1)


if __name__ == "__main__":
    unittest.main()
