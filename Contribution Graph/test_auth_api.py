import tempfile
import sqlite3
import os
import hashlib
import json
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import patch

from fastapi.testclient import TestClient as BareTestClient

from contribution_store import ContributionStore
from dashboard_server import create_app
import dashboard_server
from test_auth_support import AuthenticatedClient


class AuthApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "data.sqlite3"
        store = ContributionStore(self.db)
        store.create_project("p", "Project")
        for member in ("alice", "bob", "carol"):
            store.add_member("p", member, member.title())
        store.add_task("p", "task", "Task", 10)
        store.submit_contribution("p", "c", "alice", "task", "CORE", "Work")
        self.private = Path(self.temp.name) / "empty-private"
        self.private.mkdir()
        with patch.dict(os.environ, {"POCKETBAY_PRIVATE_DIR": str(self.private)}):
            self.app = create_app(self.db, Path(self.temp.name) / "token.sqlite3")
        self.client = AuthenticatedClient(self.app)
        self.addCleanup(self.client.close)

    def test_public_reads_anonymous_writes_and_trailing_api_path(self):
        anon = BareTestClient(self.app)
        self.assertEqual(anon.get("/api/projects").status_code, 200)
        self.assertEqual(anon.post("/api/projects", json={"id": "x", "name": "X"}).status_code, 401)
        self.assertEqual(self.client.post("/api/", json={}).status_code, 404)

    def test_site_admin_can_manage_project_without_active_membership(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT INTO project_members(project_id,member_id) VALUES('p','_test_admin')")
            conn.execute("INSERT INTO project_membership_state(project_id,member_id,state) VALUES('p','_test_admin','WITHDRAWN')")
        response = self.client.post("/api/projects/p/tasks", json={
            "id": "admin-task", "name": "Admin task", "task_value": 1,
        })
        self.assertEqual(response.status_code, 201, response.text)

    def test_origin_and_csrf_are_required(self):
        self.client._login("bob")
        headers = {"Origin": "http://testserver", "X-CSRF-Token": ""}
        response = super(AuthenticatedClient, self.client).post(
            "/api/projects/p/tasks", json={"id": "other", "name": "Other", "task_value": 1}, headers=headers)
        self.assertEqual(response.status_code, 403)
        headers["X-CSRF-Token"] = self.client.cookies.get("hacku_csrf")
        headers["Origin"] = "https://attacker.example"
        response = super(AuthenticatedClient, self.client).post(
            "/api/projects/p/tasks", json={"id": "other", "name": "Other", "task_value": 1}, headers=headers)
        self.assertEqual(response.status_code, 403)

    def test_localhost_and_loopback_ip_are_treated_as_same_local_origin(self):
        local = BareTestClient(self.app, base_url="http://127.0.0.1:8000")
        response = local.post("/api/auth/login", json={
            "member_id": "alice", "password": self.client.password,
        }, headers={"Origin": "http://localhost:8000", "Host": "127.0.0.1:8000"})
        self.assertEqual(response.status_code, 200, response.text)
        browser_headers = {"Host": "127.0.0.1:8000", "Sec-Fetch-Site": "same-origin"}
        response = local.post("/api/auth/login", json={
            "member_id": "alice", "password": self.client.password,
        }, headers=browser_headers)
        self.assertEqual(response.status_code, 200, response.text)
        blocked = local.post("/api/auth/login", json={
            "member_id": "alice", "password": self.client.password,
        }, headers={"Host": "127.0.0.1:8000", "Sec-Fetch-Site": "cross-site"})
        self.assertEqual(blocked.status_code, 403, blocked.text)

    def test_request_body_cannot_impersonate_contributor_or_reviewer(self):
        self.client._login("bob")
        response = super(AuthenticatedClient, self.client).post(
            "/api/projects/p/contributions",
            json={"id": "forged", "contributor_id": "alice", "task_id": "task", "type": "CORE", "description": "Forged"},
            headers={"Origin": "http://testserver", "X-CSRF-Token": self.client.cookies.get("hacku_csrf")})
        self.assertEqual(response.status_code, 403)
        response = super(AuthenticatedClient, self.client).post(
            "/api/contributions/c/reviews", json={"reviewer_id": "alice", "decision": "CONFIRM"},
            headers={"Origin": "http://testserver", "X-CSRF-Token": self.client.cookies.get("hacku_csrf")})
        self.assertEqual(response.status_code, 403)

    def test_invitation_is_single_use_and_cookie_session_can_be_revoked(self):
        self.client._login("alice")
        with sqlite3.connect(self.db) as conn:
            conn.execute("DELETE FROM auth_accounts WHERE member_id='carol'")
        invite = self.client.post("/api/projects/p/invites", json={"member_id": "carol"})
        self.assertEqual(invite.status_code, 200, invite.text)
        token = urlsplit(invite.json()["inviteUrl"]).fragment
        invitee = BareTestClient(self.app)
        redeemed = invitee.post("/api/auth/accept-invite",
                                json={"invite": token, "password": "New-password-123"},
                                headers={"Origin": "http://testserver"})
        self.assertEqual(redeemed.status_code, 200, redeemed.text)
        self.assertEqual(redeemed.headers["set-cookie"].find("HttpOnly") >= 0, True)
        replay = BareTestClient(self.app).post("/api/auth/accept-invite",
                                              json={"invite": token, "password": "Another-password-123"},
                                              headers={"Origin": "http://testserver"})
        self.assertEqual(replay.status_code, 400)
        old_csrf = invitee.cookies.get("hacku_csrf")
        changed = invitee.post("/api/auth/change-password",
                               json={"old_password": "New-password-123", "new_password": "Updated-password-123"},
                               headers={"Origin": "http://testserver", "X-CSRF-Token": old_csrf})
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(invitee.get("/api/auth/me").json()["authenticated"], False)

    def test_expired_invite_and_invite_attempt_limit(self):
        self.client._login("alice")
        with sqlite3.connect(self.db) as conn:
            conn.execute("DELETE FROM auth_accounts WHERE member_id='carol'")
        created = self.client.post("/api/projects/p/invites", json={"member_id": "carol"})
        token = urlsplit(created.json()["inviteUrl"]).fragment
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE auth_invites SET expires_at=0")
        anon = BareTestClient(self.app)
        statuses = [anon.post("/api/auth/accept-invite", json={"invite": token, "password": "Long-enough-123"},
                              headers={"Origin": "http://testserver"}).status_code for _ in range(11)]
        self.assertEqual(statuses[:10], [400] * 10)
        self.assertEqual(statuses[-1], 429)

    def test_invite_password_requires_eight_chars_mixed_case_and_number(self):
        self.client._login("alice")
        with sqlite3.connect(self.db) as conn:
            conn.execute("DELETE FROM auth_accounts WHERE member_id='carol'")
        created = self.client.post("/api/projects/p/invites", json={"member_id": "carol"})
        token = urlsplit(created.json()["inviteUrl"]).fragment
        anon = BareTestClient(self.app)
        for password in ("Short1A", "alllowercase1", "ALLUPPERCASE1", "NoDigitsHere"):
            response = anon.post("/api/auth/accept-invite", json={"invite": token, "password": password},
                                 headers={"Origin": "http://testserver"})
            self.assertEqual(response.status_code, 400, password)
        accepted = anon.post("/api/auth/accept-invite", json={"invite": token, "password": "Jyz20051215"},
                             headers={"Origin": "http://testserver"})
        self.assertEqual(accepted.status_code, 200, accepted.text)

    def test_deployment_login_cookie_is_secure_behind_proxy(self):
        anon = BareTestClient(self.app)
        with patch.dict(os.environ, {"POCKETBAY_DATA_DIR": "/data"}, clear=False):
            response = anon.post("/api/auth/login", json={"member_id": "alice", "password": self.client.password},
                                 headers={"Origin": "https://testserver", "X-Forwarded-Proto": "https"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("Secure", response.headers.get("set-cookie", ""))

    def test_recovery_seed_restores_missing_site_admin_without_changing_existing_admin(self):
        salt = os.urandom(16)
        digest = hashlib.scrypt(b"RecoveryPass123", salt=salt, n=2**14, r=8, p=1, dklen=32)
        private = Path(self.temp.name) / "private"
        private.mkdir()
        (private / "hacku-auth-seed.json").write_text(json.dumps({
            "member_id": "20231118", "salt": salt.hex(), "password_hash": digest.hex(),
        }), encoding="utf-8")
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT INTO members(id,name) VALUES('20231118','20231118')")
            conn.execute("UPDATE auth_accounts SET is_site_admin=0")
        with patch.dict(os.environ, {"POCKETBAY_PRIVATE_DIR": str(private)}):
            recovered = create_app(self.db, Path(self.temp.name) / "token.sqlite3")
        with sqlite3.connect(self.db) as conn:
            row = conn.execute("SELECT is_site_admin,password_hash FROM auth_accounts WHERE member_id='20231118'").fetchone()
        self.assertEqual(row, (1, digest))
        login = BareTestClient(recovered).post("/api/auth/login", json={
            "member_id": "20231118", "password": "RecoveryPass123",
        }, headers={"Origin": "http://testserver"})
        self.assertEqual(login.status_code, 200, login.text)
        with patch.dict(os.environ, {"POCKETBAY_PRIVATE_DIR": str(private)}):
            create_app(self.db, Path(self.temp.name) / "token.sqlite3")
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM auth_accounts WHERE is_site_admin=1").fetchone()[0], 1)

    def test_pocketbay_imports_snapshot_before_creating_identity_tables(self):
        fresh = Path(self.temp.name) / "fresh.sqlite3"
        with patch.dict(os.environ, {"POCKETBAY_DATA_DIR": self.temp.name,
                                     "POCKETBAY_PRIVATE_DIR": str(self.private)}), patch.object(dashboard_server, "DEFAULT_DB", fresh):
            create_app(fresh, Path(self.temp.name) / "fresh-token.sqlite3")
        with sqlite3.connect(fresh) as conn:
            self.assertGreater(conn.execute("SELECT count(*) FROM projects").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT count(*) FROM auth_accounts").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
