import tempfile
import unittest
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
            legacy.create_project("p", "Project")
            for member in ("alice", "bob", "carol"):
                legacy.add_member("p", member, member)
            token_path = root / "token.sqlite3"
            store = TokenStore(token_path, TokenProject("p", "Project", "treasury", ("alice", "bob", "carol")))
            store.add_task(TokenTask("task", "p", "Task", ValueType.CORE, 100, "Done"))
            store.create_commission("c", "task", "alice", "bob", 50, 60)
            for status in (ContractStatus.OFFERED, ContractStatus.ACCEPTED, ContractStatus.CREDIT_RESERVED,
                           ContractStatus.DELIVERED, ContractStatus.VERIFIED):
                store.advance_contract("c", status)
            client = AuthenticatedClient(create_app(root / "data.sqlite3", token_path))
            self.addCleanup(client.close)
            client._login("carol")
            self.assertEqual(client.post("/api/token/contracts/c/approve", json={"note": "Independent"}).status_code, 201)
            settled = client.post("/api/token/contracts/c/settle", json={
                "verified_mint_value": "60", "evidence_hashes": ["evidence:c"], "approver_ids": ["carol"]})
            self.assertEqual(settled.status_code, 200, settled.text)
            client._login("alice")
            disputed = client.post("/api/token/contracts/c/dispute", json={"reason": "Incomplete delivery"})
            self.assertEqual(disputed.status_code, 201, disputed.text)
            client._login("_test_admin")
            frozen = client.post("/api/token/contracts/c/freeze", json={"reason": "Secure the payment"})
            self.assertEqual(frozen.status_code, 201, frozen.text)
            client._login("carol")
            resolved = client.post("/api/token/contracts/c/resolve", json={
                "outcome": "SPLIT", "refund_amount": "20", "note": "Split by verified work"})
            self.assertEqual(resolved.status_code, 200, resolved.text)
            self.assertEqual(resolved.json()["resolution"]["refundAmount"], "20")
            ledger = client.get("/api/token/ledger").json()
            self.assertEqual(ledger["balances"], {"alice": 30.0, "bob": 30.0, "carol": 0.0})
            contract = client.get("/api/token/contracts").json()[0]
            self.assertEqual(contract["status"], "RESOLVED")


if __name__ == "__main__":
    unittest.main()
