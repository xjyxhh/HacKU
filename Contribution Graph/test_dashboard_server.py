"""Check the FastAPI route through a complete contribution workflow."""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient as BareTestClient
from test_auth_support import AuthenticatedClient

from dashboard_server import create_app


class DashboardApiTests(unittest.TestCase):
    def test_project_creator_is_not_added_as_member_and_unused_member_can_be_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            client = AuthenticatedClient(create_app(Path(directory) / "data.sqlite3", Path(directory) / "token.sqlite3"))
            created = client.post("/api/projects", json={"id": "empty", "name": "Empty"})
            self.assertEqual(created.status_code, 201, created.text)
            self.assertEqual(client.get("/api/projects/empty/dashboard").json()["members"], [])
            self.assertEqual(client.post("/api/projects/empty/members", json={"id": "alice", "name": "Alice"}).status_code, 201)
            self.assertEqual(client.post("/api/projects/empty/members", json={"id": "bob", "name": "Bob"}).status_code, 201)
            removed = client.delete("/api/projects/empty/members/alice")
            self.assertEqual(removed.status_code, 200, removed.text)
            self.assertEqual([member["id"] for member in client.get("/api/projects/empty/dashboard").json()["members"]], ["bob"])

    def test_dashboard_and_review_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            client = AuthenticatedClient(create_app(Path(directory) / "data.sqlite3", Path(directory) / "token.sqlite3"),
                                headers={"X-Token-Admin-Key": "test-key"})
            self.assertEqual(client.get("/").status_code, 200)
            self.assertEqual(client.get("/docs").status_code, 200)
            self.assertEqual(client.post("/api/projects", json={"id": "fintech", "name": "Project"}).status_code, 201)
            self.assertEqual(client.get("/api/projects").json(), [{"id": "fintech", "name": "Project"}])
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
            members = client.get("/api/dashboard").json()["members"]
            self.assertEqual(next(member for member in members if member["id"] == "alice")["totalScore"], 20)
            self.assertEqual(client.post("/api/contributions/c1/reviews", json={
                "reviewer_id": "bob", "decision": "DISPUTE", "note": "Review again",
            }).status_code, 200)
            members = client.get("/api/dashboard").json()["members"]
            self.assertEqual(next(member for member in members if member["id"] == "alice")["totalScore"], 0)
            self.assertEqual(client.post("/api/contributions/c1/resolve", json={
                "resolved_by": "bob", "resolution": "Half complete", "completion": "0.5",
            }).status_code, 200)
            members = client.get("/api/projects/fintech/dashboard").json()["members"]
            self.assertEqual(next(member for member in members if member["id"] == "alice")["totalScore"], 10)
            self.assertEqual(len(client.get("/api/contributions/c1").json()["disputes"]), 1)

    def test_entry_data_persists_across_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.sqlite3"
            client = AuthenticatedClient(create_app(path, path.with_name("token.sqlite3")),
                                headers={"X-Token-Admin-Key": "test-key"})
            client.post("/api/projects", json={"id": "demo", "name": "Demo"})
            for member in ("alice", "david"):
                client.post("/api/projects/demo/members", json={"id": member, "name": member.title()})
            client.post("/api/projects/demo/tasks", json={"id": "deploy", "name": "Deployment", "task_value": "20", "description": "Deploy app"})
            response = client.post("/api/projects/demo/contributions", json={
                "id": "new-help", "contributor_id": "david", "task_id": "deploy", "type": "SUPPORT",
                "description": "Helped Alice deploy", "support_value": "8", "helped_member_id": "alice",
            })
            self.assertEqual(response.status_code, 201)
            reopened = AuthenticatedClient(create_app(path, path.with_name("token.sqlite3")),
                                  headers={"X-Token-Admin-Key": "test-key"})
            data = reopened.get("/api/projects/demo/dashboard").json()
            self.assertEqual(data["tasks"][0]["description"], "Deploy app")
            self.assertEqual(data["contributions"][0]["status"], "PENDING")
            self.assertEqual(data["contributions"][0]["score"], 0)
            detail = reopened.get("/api/contributions/new-help").json()
            self.assertEqual(detail["contribution"]["support_value"], "8")
            self.assertEqual(detail["contribution"]["helped_member_id"], "alice")


if __name__ == "__main__":
    unittest.main()
