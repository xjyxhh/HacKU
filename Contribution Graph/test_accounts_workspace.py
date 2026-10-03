import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from dashboard_server import create_app


class AccountsWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "data.sqlite3"
        self.empty_private = self.root / "private"
        self.empty_private.mkdir()
        with patch.dict("os.environ", {"POCKETBAY_PRIVATE_DIR": str(self.empty_private)}):
            self.app = create_app(self.db, self.root / "token.sqlite3")

    def client(self):
        return TestClient(self.app)

    @staticmethod
    def register(client, email, display_name):
        response = client.post("/api/auth/register", headers={"Origin": "http://testserver"}, json={
            "email": email, "display_name": display_name, "password": "StrongPass1",
        })
        return response

    def headers(self, client):
        return {"Origin": "http://testserver", "X-CSRF-Token": client.cookies.get("hacku_csrf", "")}

    def test_register_workspace_and_self_created_owner_project(self):
        client = self.client()
        registered = self.register(client, "Owner@example.com", "Owner One")
        self.assertEqual(registered.status_code, 201, registered.text)
        self.assertFalse(registered.json()["emailVerified"])
        self.assertEqual(client.get("/api/workspace").json()["projects"], [])
        created = client.post("/api/projects", headers=self.headers(client), json={"id": "owned", "name": "Owned"})
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["tokenLedgerState"], "READY")
        workspace = client.get("/api/workspace").json()
        self.assertEqual(workspace["projects"][0]["role"], "OWNER")
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT role FROM project_member_roles WHERE project_id='owned'").fetchone()[0], "OWNER")

    def test_registered_account_survives_restart_and_uses_display_name(self):
        client = self.client()
        created = self.register(client, "saved@example.com", "Saved Name")
        self.assertEqual(created.status_code, 201, created.text)
        member_id = created.json()["memberId"]
        self.assertEqual(client.get("/api/auth/me").json()["displayName"], "Saved Name")
        self.assertEqual(client.post("/api/auth/logout", headers=self.headers(client)).status_code, 200)
        with patch.dict("os.environ", {"POCKETBAY_PRIVATE_DIR": str(self.empty_private)}):
            restarted = create_app(self.db, self.root / "token.sqlite3")
        returning = TestClient(restarted)
        login = returning.post("/api/auth/login", headers={"Origin": "http://testserver"},
                               json={"member_id": "SAVED@example.com", "password": "StrongPass1"})
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(returning.get("/api/auth/me").json()["memberId"], member_id)
        self.assertEqual(returning.get("/api/auth/me").json()["displayName"], "Saved Name")
        updated = returning.patch("/api/profile", headers=self.headers(returning),
                                  json={"display_name": "New Name", "bio": "", "avatar_url": ""})
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(returning.get("/api/auth/me").json()["displayName"], "New Name")

    def test_existing_account_invite_role_audit_and_last_owner_protection(self):
        owner, verifier = self.client(), self.client()
        self.register(owner, "owner@example.com", "Owner")
        self.register(verifier, "verifier@example.com", "Verifier")
        project = owner.post("/api/projects", headers=self.headers(owner), json={"id": "p", "name": "Project"})
        self.assertEqual(project.status_code, 201, project.text)
        invited = owner.post("/api/projects/p/members/invite-existing", headers=self.headers(owner), json={
            "member_id": verifier.get("/api/auth/me").json()["memberId"], "role": "VERIFIER",
        })
        self.assertEqual(invited.status_code, 201, invited.text)
        denied = owner.patch("/api/projects/p/members/" + owner.get("/api/auth/me").json()["memberId"] + "/role",
                             headers=self.headers(owner), json={"role": "MEMBER"})
        self.assertEqual(denied.status_code, 409, denied.text)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT role FROM project_member_roles WHERE project_id='p' AND role='VERIFIER'").fetchone()[0], "VERIFIER")
            self.assertEqual(conn.execute("SELECT old_role,new_role FROM project_role_audit WHERE project_id='p'").fetchone(), (None, "VERIFIER"))

    def test_email_verification_token_is_one_time_and_enables_email_login(self):
        client = self.client()
        captured = {}
        def capture(_email, link):
            captured["token"] = link.rsplit("#", 1)[1]
            return True
        with patch("dashboard_server.send_verification_email", capture), patch.dict("os.environ", {
            "HACKU_SMTP_HOST": "smtp.example.test", "HACKU_SMTP_FROM": "noreply@example.test",
        }):
            created = self.register(client, "verify@example.com", "Verify")
        self.assertTrue(created.json()["verificationSent"])
        verified = client.post("/api/auth/verify-email", headers={"Origin": "http://testserver"}, json={"token": captured["token"]})
        self.assertEqual(verified.status_code, 200, verified.text)
        replay = client.post("/api/auth/verify-email", headers={"Origin": "http://testserver"}, json={"token": captured["token"]})
        self.assertEqual(replay.status_code, 400)
        client.post("/api/auth/logout", headers=self.headers(client))
        login = client.post("/api/auth/login", headers={"Origin": "http://testserver"}, json={"member_id": "VERIFY@example.com", "password": "StrongPass1"})
        self.assertEqual(login.status_code, 200, login.text)

    def test_public_demo_is_fixed_and_does_not_write_project_rows(self):
        client = self.client()
        before = sqlite3.connect(self.db).execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        response = client.get("/api/demo")
        after = sqlite3.connect(self.db).execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["demo"])
        self.assertEqual(before, after)

    def test_three_members_complete_commission_with_delivery_and_real_approval(self):
        owner, contractor, verifier = self.client(), self.client(), self.client()
        self.register(owner, "principal@example.com", "Principal")
        self.register(contractor, "contractor@example.com", "Contractor")
        self.register(verifier, "verifier@example.com", "Verifier")
        owner_id = owner.get("/api/auth/me").json()["memberId"]
        contractor_id = contractor.get("/api/auth/me").json()["memberId"]
        verifier_id = verifier.get("/api/auth/me").json()["memberId"]
        self.assertEqual(owner.post("/api/projects", headers=self.headers(owner), json={"id":"commission-project","name":"Commission"}).status_code, 201)
        for client, member_id, role in ((owner, contractor_id, "MEMBER"), (owner, verifier_id, "VERIFIER")):
            response = client.post("/api/projects/commission-project/members/invite-existing", headers=self.headers(client), json={"member_id":member_id,"role":role})
            self.assertEqual(response.status_code, 201, response.text)
        def token_post(client, path, body):
            return client.post(f"/api/projects/commission-project/token/{path}", headers=self.headers(client), json=body)
        task = token_post(owner, "tasks", {"id":"task","name":"Task","value_type":"CORE","mint_cap":"100","acceptance_criteria":"Reviewed delivery"})
        self.assertEqual(task.status_code, 200, task.text)
        created = token_post(owner, "contracts", {"id":"contract","task_id":"task","principal_id":owner_id,"contractor_id":contractor_id,"contract_price":"10","maximum_mint_value":"20"})
        self.assertEqual(created.status_code, 200, created.text)
        for client, status in ((owner,"OFFERED"),(contractor,"ACCEPTED"),(owner,"CREDIT_RESERVED")):
            advanced = token_post(client, "contracts/contract/advance", {"status":status})
            self.assertEqual(advanced.status_code, 200, advanced.text)
        no_evidence = token_post(contractor, "contracts/contract/advance", {"status":"DELIVERED"})
        self.assertEqual(no_evidence.status_code, 409, no_evidence.text)
        delivered = token_post(contractor, "contracts/contract/deliver", {"evidence":["https://example.test/delivery"]})
        self.assertEqual(delivered.status_code, 200, delivered.text)
        verified = token_post(verifier, "contracts/contract/advance", {"status":"VERIFIED"})
        self.assertEqual(verified.status_code, 200, verified.text)
        approval = token_post(verifier, "contracts/contract/approve", {"note":"Evidence checked"})
        self.assertEqual(approval.status_code, 200, approval.text)
        settlement = token_post(owner, "contracts/contract/settle", {"verified_mint_value":"12","evidence_hashes":["settlement:proof"]})
        self.assertEqual(settlement.status_code, 200, settlement.text)
        with sqlite3.connect(self.root / "token-ledgers" / ( __import__("hashlib").sha256(b"commission-project").hexdigest() + ".sqlite3")) as conn:
            self.assertEqual(conn.execute("SELECT member_id,evidence FROM contract_delivery_evidence WHERE contract_id='contract'").fetchone(), (contractor_id,"https://example.test/delivery"))
            self.assertEqual(conn.execute("SELECT member_id FROM contract_approvals WHERE contract_id='contract'").fetchone()[0], verifier_id)


if __name__ == "__main__":
    unittest.main()
