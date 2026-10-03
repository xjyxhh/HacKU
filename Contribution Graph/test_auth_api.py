"""Member account provisioning, login sessions, and API authorization tests."""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from contribution_store import ContributionStore
from dashboard_server import create_app


class AuthApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "data.sqlite3"
        self.token_path = Path(self.directory.name) / "token.sqlite3"
        store = ContributionStore(self.path)
        store.create_project("alpha", "Alpha")
        store.add_member("alpha", "alice", "Alice")
        store.add_member("alpha", "bob", "Bob")
        store.set_member_role("alpha", "alice", "OWNER")
        store.set_member_role("alpha", "bob", "VERIFIER")
        store.add_task("alpha", "task", "Task", "20")
        store.submit_contribution("alpha", "work", "alice", "task", "CORE", "Implemented work")
        store.create_project("beta", "Beta")
        store.add_member("beta", "charlie", "Charlie")
        self.app = create_app(self.path, self.token_path, token_admin_key="root-key")
        self.admin = TestClient(self.app)

    def tearDown(self):
        self.admin.close()

    def provision(self, member_id, password="correct horse battery staple"):
        return self.admin.post(
            "/api/admin/member-accounts",
            headers={"X-Token-Admin-Key": "root-key"},
            json={"member_id": member_id, "password": password},
        )

    def login(self, member_id="alice", password="correct horse battery staple"):
        client = TestClient(self.app, base_url="https://testserver")
        response = client.post("/api/auth/login", json={"member_id": member_id, "password": password})
        return client, response

    def test_api_requires_login_and_admin_provisions_only_existing_project_members(self):
        self.assertEqual(self.admin.get("/login.html").status_code, 200)
        self.assertEqual(self.admin.get("/auth.js").status_code, 200)
        self.assertEqual(self.admin.get("/api/projects").status_code, 401)
        self.assertEqual(self.admin.get("/api/contributions/work").status_code, 401)
        self.assertEqual(self.admin.post("/api/admin/member-accounts", json={
            "member_id": "alice", "password": "correct horse battery staple",
        }).status_code, 403)
        unknown = self.provision("nobody")
        self.assertEqual(unknown.status_code, 404, unknown.text)
        short = self.provision("alice", "short")
        self.assertEqual(short.status_code, 400, short.text)
        created = self.provision("alice")
        self.assertEqual(created.status_code, 201, created.text)

    def test_login_uses_secure_http_only_cookie_and_binds_actor_identity(self):
        self.provision("alice")
        self.provision("bob")
        self.provision("charlie")
        client, response = self.login(password="wrong password here")
        self.assertEqual(response.status_code, 401)
        client.close()

        client, response = self.login()
        self.addCleanup(client.close)
        self.assertEqual(response.status_code, 200, response.text)
        cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("secure", cookie)
        self.assertIn("samesite=lax", cookie)
        self.assertEqual(client.get("/api/auth/session").json()["memberId"], "alice")
        self.assertEqual([row["id"] for row in client.get("/api/projects").json()], ["alpha"])
        self.assertEqual(client.get("/api/projects/beta/dashboard").status_code, 403)
        self.assertEqual(client.get("/api/contributions/work").status_code, 200)
        csrf = client.post(
            "/api/projects/alpha/contributions",
            headers={"Origin": "https://attacker.example"},
            json={
                "id": "cross-site", "contributor_id": "alice", "task_id": "task",
                "type": "CORE", "description": "Cross-origin request",
            },
        )
        self.assertEqual(csrf.status_code, 403)
        self.assertEqual(client.post("/api/contributions/work/evidence", json={
            "submitted_by": "alice", "kind": "NOTE", "reference": "My work log",
        }).status_code, 201)

        spoof = client.post("/api/projects/alpha/contributions", json={
            "id": "spoofed", "contributor_id": "bob", "task_id": "task",
            "type": "CORE", "description": "Impersonation attempt",
        })
        self.assertEqual(spoof.status_code, 403, spoof.text)
        self.assertEqual(client.get("/api/contributions/spoofed").status_code, 404)
        review_spoof = client.post("/api/contributions/work/reviews", json={
            "reviewer_id": "bob", "decision": "CONFIRM",
        })
        self.assertEqual(review_spoof.status_code, 403, review_spoof.text)

        evidence_spoof = client.post("/api/contributions/work/evidence", json={
            "submitted_by": "bob", "kind": "NOTE", "reference": "Not Alice",
        })
        self.assertEqual(evidence_spoof.status_code, 403, evidence_spoof.text)

        bob, bob_login = self.login("bob")
        self.addCleanup(bob.close)
        self.assertEqual(bob_login.status_code, 200, bob_login.text)
        reviewed = bob.post("/api/contributions/work/reviews", json={
            "reviewer_id": "bob", "decision": "CONFIRM",
        })
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        self.assertEqual(bob.get("/api/projects/alpha/dashboard").json()["members"][0]["totalScore"], 20)

        created = client.post("/api/projects", json={"id": "new-project", "name": "New Project"})
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["member_ids"], ["alice"])
        self.assertIn("new-project", {row["id"] for row in client.get("/api/projects").json()})

    def test_sessions_persist_and_password_reset_revokes_existing_sessions(self):
        self.provision("alice")
        client, response = self.login()
        self.assertEqual(response.status_code, 200)
        self.addCleanup(client.close)

        reloaded = TestClient(
            create_app(self.path, self.token_path, token_admin_key="root-key"),
            base_url="https://testserver",
            cookies=client.cookies,
        )
        self.addCleanup(reloaded.close)
        self.assertEqual(reloaded.get("/api/auth/session").status_code, 200)
        reset = self.provision("alice", "a newer correct horse battery")
        self.assertEqual(reset.status_code, 201, reset.text)
        self.assertEqual(reloaded.get("/api/auth/session").status_code, 401)

        new_client, new_login = self.login(password="a newer correct horse battery")
        self.addCleanup(new_client.close)
        self.assertEqual(new_login.status_code, 200, new_login.text)
        self.assertEqual(new_client.post("/api/auth/logout").status_code, 200)
        self.assertEqual(new_client.get("/api/auth/session").status_code, 401)

    def test_registration_profile_workspace_and_registered_member_invitation(self):
        alice = TestClient(self.app, base_url="https://testserver")
        self.addCleanup(alice.close)
        registered = alice.post("/api/auth/register", json={
            "email": "alice@example.com",
            "display_name": "Alice User",
            "password": "a correct horse battery staple",
        })
        self.assertEqual(registered.status_code, 201, registered.text)
        alice_id = registered.json()["memberId"]
        self.assertEqual(alice.get("/api/workspace").json()["projects"], [])

        created = alice.post("/api/projects", json={"id": "new-project", "name": "New Project"})
        self.assertEqual(created.status_code, 201, created.text)
        ledger = alice.get("/api/token/ledger", headers={"X-Project-ID": "new-project"})
        self.assertEqual(ledger.status_code, 200, ledger.text)
        self.assertEqual(ledger.json()["memberIds"], [alice_id])
        workspace = alice.get("/api/workspace").json()
        self.assertEqual(workspace["projects"][0]["role"], "OWNER")

        bob = TestClient(self.app, base_url="https://testserver")
        self.addCleanup(bob.close)
        bob_registration = bob.post("/api/auth/register", json={
            "email": "bob@example.com",
            "display_name": "Bob User",
            "password": "another correct horse battery",
        })
        self.assertEqual(bob_registration.status_code, 201, bob_registration.text)
        invitation = alice.post("/api/projects/new-project/members/invite", json={
            "identifier": "bob@example.com",
            "role": "VERIFIER",
        })
        self.assertEqual(invitation.status_code, 201, invitation.text)
        self.assertEqual({
            (member["id"], member["role"])
            for member in alice.get("/api/projects/new-project/members").json()
        }, {(alice_id, "OWNER"), (bob_registration.json()["memberId"], "VERIFIER")})

        duplicate = bob.post("/api/auth/register", json={
            "email": "alice@example.com",
            "display_name": "Duplicate",
            "password": "another correct horse battery",
        })
        self.assertEqual(duplicate.status_code, 400, duplicate.text)
        profile = alice.patch("/api/profile", json={
            "display_name": "Alice Updated",
            "email": "alice@example.com",
            "bio": "Builds useful things",
            "avatar_url": "",
            "wallet_address": "",
        })
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertEqual(profile.json()["displayName"], "Alice Updated")
        self.assertEqual(alice.get("/api/profile").json()["bio"], "Builds useful things")

    def test_admin_can_assign_owner_to_existing_legacy_project(self):
        response = self.admin.patch("/api/projects/alpha/members/alice", json={"role": "OWNER"},
                                   headers={"X-Token-Admin-Key": "root-key"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            ContributionStore(self.path).membership_roles[("alpha", "alice")],
            "OWNER",
        )

    def test_members_cannot_invite_or_review_without_project_role(self):
        self.provision("alice")
        self.provision("bob")
        self.provision("charlie")
        alice, _ = self.login("alice", "correct horse battery staple")
        self.addCleanup(alice.close)
        bob, _ = self.login("bob", "correct horse battery staple")
        self.addCleanup(bob.close)
        self.assertEqual(bob.patch("/api/projects/alpha/members/alice",
                                   json={"role": "VIEWER"}).status_code, 403)
        self.assertEqual(bob.post("/api/projects/alpha/tasks", json={
            "id": "blocked", "name": "Blocked", "task_value": "10",
        }).status_code, 403)
