import tempfile
import unittest
import hashlib
import sqlite3
from pathlib import Path

from contribution_store import ContributionStore
from dashboard_server import create_app
from test_auth_support import AuthenticatedClient
from token_engine import ContractStatus, TokenProject, TokenTask, ValueType
from token_store import TokenStore


class ContractResolutionApiTests(unittest.TestCase):
    def test_member_disputes_admin_freezes_and_records_split(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = ContributionStore(root / "data.sqlite3")
            legacy.create_project("source-project", "Project")
            for member in ("alice", "bob", "carol"):
                legacy.add_member("source-project", member, member)
            token_path = root / "token.sqlite3"
            app = create_app(root / "data.sqlite3", token_path)
            client = AuthenticatedClient(app)
            self.addCleanup(client.close)
            client._login("_test_admin")
            # Rename the fixture project to the intended isolated contract project.
            with sqlite3.connect(root / "data.sqlite3") as conn:
                conn.execute("PRAGMA foreign_keys=OFF")
                conn.execute("UPDATE projects SET id='contract-project' WHERE id='source-project'")
                conn.execute("UPDATE project_lifecycle SET project_id='contract-project' WHERE project_id='source-project'")
                conn.execute("UPDATE project_versions SET project_id='contract-project' WHERE project_id='source-project'")
                conn.execute("UPDATE project_members SET project_id='contract-project' WHERE project_id='source-project'")
                conn.execute("UPDATE project_membership_state SET project_id='contract-project' WHERE project_id='source-project'")
                conn.execute("UPDATE tasks SET project_id='contract-project' WHERE project_id='source-project'")
                conn.execute("PRAGMA foreign_keys=ON")
            self.assertEqual(client.post("/api/projects/contract-project/token/setup/retry",json={}).status_code,200)
            with sqlite3.connect(root / "data.sqlite3") as conn:
                for member in ("alice", "bob", "carol"):
                    conn.execute("INSERT OR IGNORE INTO project_member_roles(project_id,member_id,role) VALUES('contract-project',?,'OWNER')",(member,))
                    conn.execute("INSERT OR IGNORE INTO auth_project_admins(project_id,member_id) VALUES('contract-project',?)",(member,))
            client._ensure_accounts()
            self.assertEqual(client.post("/api/projects/contract-project/tasks",json={"id":"task","name":"Task","task_value":"100","description":"Done"}).status_code,201)
            client._login("alice")
            self.assertEqual(client.post("/api/projects/contract-project/token/contracts",json={"id":"c","task_id":"task","principal_id":"alice","contractor_id":"bob","contract_price":"50","maximum_mint_value":"60"}).status_code,200)
            client.post("/api/projects/contract-project/token/contracts/c/advance",json={"status":"OFFERED"})
            client._login("bob")
            client.post("/api/projects/contract-project/token/contracts/c/advance",json={"status":"ACCEPTED"})
            client._login("alice")
            client.post("/api/projects/contract-project/token/contracts/c/advance",json={"status":"CREDIT_RESERVED"})
            client._login("bob")
            delivered=client.post("/api/projects/contract-project/token/contracts/c/deliver", json={"evidence": ["deliverable:c"]})
            self.assertEqual(delivered.status_code, 200, delivered.text)
            client._login("carol")
            self.assertEqual(client.post("/api/projects/contract-project/token/contracts/c/advance", json={"status": "VERIFIED"}).status_code, 200)
            self.assertEqual(client.post("/api/projects/contract-project/token/contracts/c/approve", json={"note": "Independent"}).status_code, 200)
            settled = client.post("/api/projects/contract-project/token/contracts/c/settle", json={
                "verified_mint_value": "60", "evidence_hashes": ["evidence:c"], "approver_ids": ["carol"]})
            self.assertEqual(settled.status_code, 200, settled.text)
            client._login("alice")
            disputed = client.post("/api/projects/contract-project/token/contracts/c/dispute", json={"reason": "Incomplete delivery"})
            self.assertEqual(disputed.status_code, 200, disputed.text)
            client._login("_test_admin")
            frozen = client.post("/api/projects/contract-project/token/contracts/c/freeze", json={"reason": "Secure the payment"})
            self.assertEqual(frozen.status_code, 200, frozen.text)
            client._login("carol")
            resolved = client.post("/api/projects/contract-project/token/contracts/c/resolve", json={
                "outcome": "SPLIT", "refund_amount": "20", "note": "Split by verified work"})
            self.assertEqual(resolved.status_code, 200, resolved.text)
            self.assertEqual(resolved.json()["resolution"]["refundAmount"], "20")
            ledger = client.get("/api/projects/contract-project/token/ledger").json()
            self.assertEqual(ledger["balances"], {"alice": 30.0, "bob": 30.0, "carol": 0.0})
            contract = client.get("/api/projects/contract-project/token/contracts").json()[0]
            self.assertEqual(contract["status"], "RESOLVED")


if __name__ == "__main__":
    unittest.main()
