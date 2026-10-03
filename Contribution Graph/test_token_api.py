"""Tests for the token ledger HTTP API and review-to-mint hook (fusion PR2/PR3)."""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from contribution_store import ContributionStore
from dashboard_server import create_app
from migrate_token_ledger import migrate_project


def build_legacy(path):
    """Legacy project with one confirmable CORE and one confirmable SUPPORT."""
    store = ContributionStore(path)
    store.create_project("fintech", "FinTech")
    for member in ("alice", "bob", "charlie", "david"):
        store.add_member("fintech", member, member.title())
    store.add_task("fintech", "recommendation", "Recommendation", "40", "Working engine")
    store.submit_contribution("fintech", "core", "alice", "recommendation", "CORE", "Built engine")
    store.submit_contribution("fintech", "help", "david", "recommendation", "SUPPORT",
                              "Helped Alice", support_value="7", helped_member_id="alice")
    return store


class TokenApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.legacy_db = Path(self.tmp.name) / "legacy.sqlite3"
        self.token_db = Path(self.tmp.name) / "token.sqlite3"
        build_legacy(self.legacy_db)
        self.client = TestClient(create_app(self.legacy_db, self.token_db))

    def tearDown(self):
        self.tmp.cleanup()

    def create_ledger(self):
        response = self.client.post("/api/token/project", json={
            "id": "fintech", "name": "FinTech", "treasury_id": "fintech-treasury",
            "member_ids": ["alice", "bob", "charlie", "david"],
        })
        self.assertEqual(response.status_code, 201, response.text)
        response = self.client.post("/api/token/tasks", json={
            "id": "recommendation", "name": "Recommendation", "value_type": "CORE",
            "mint_cap": "100", "acceptance_criteria": "Working engine",
        })
        self.assertEqual(response.status_code, 201, response.text)

    def test_ledger_routes_404_before_creation(self):
        for path in ("/api/token/ledger", "/api/token/graph", "/api/token/contracts"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404, path)
        response = self.client.get("/api/token/tasks/recommendation/budget")
        self.assertEqual(response.status_code, 404)

    def test_create_project_and_ledger_roundtrip(self):
        self.create_ledger()
        ledger = self.client.get("/api/token/ledger").json()
        self.assertEqual(ledger["projectId"], "fintech")
        self.assertEqual(ledger["treasuryId"], "fintech-treasury")
        self.assertEqual(ledger["totalSupply"], 0.0)
        self.assertEqual(ledger["balances"], {m: 0.0 for m in ("alice", "bob", "charlie", "david")})
        budget = self.client.get("/api/token/tasks/recommendation/budget").json()
        self.assertEqual(budget["mintCap"], "100")
        self.assertEqual(budget["available"], "100")

    def test_create_project_twice_rejected(self):
        self.create_ledger()
        response = self.client.post("/api/token/project", json={
            "id": "fintech", "name": "FinTech", "treasury_id": "fintech-treasury",
            "member_ids": ["alice", "bob"],
        })
        self.assertEqual(response.status_code, 400)

    def test_mint_transfer_and_graph(self):
        self.create_ledger()
        response = self.client.post("/api/token/mint", json={
            "event_id": "e1", "task_id": "recommendation", "recipient_id": "alice",
            "amount": "40", "evidence_hashes": ["sha:a"],
        })
        self.assertEqual(response.status_code, 201, response.text)
        response = self.client.post("/api/token/transfer", json={
            "event_id": "e2", "source_id": "alice", "destination_id": "bob",
            "amount": "15", "task_id": "recommendation", "evidence_hashes": ["sha:b"],
        })
        self.assertEqual(response.status_code, 201, response.text)
        ledger = self.client.get("/api/token/ledger").json()
        self.assertEqual(ledger["balances"]["alice"], 25.0)
        self.assertEqual(ledger["balances"]["bob"], 15.0)
        self.assertEqual(ledger["totalSupply"], 40.0)
        self.assertEqual([event["kind"] for event in ledger["events"]], ["MINT", "TRANSFER"])
        graph = self.client.get("/api/token/graph").json()
        kinds = {node["kind"] for node in graph["nodes"]}
        self.assertIn("TREASURY", kinds)
        self.assertIn("MEMBER", kinds)
        self.assertIn("TASK", kinds)
        minted = [edge for edge in graph["edges"] if edge["kind"] == "MINTED"]
        self.assertEqual(minted[0]["amount"], 40.0)
        # Duplicate evidence is still rejected over HTTP after a fresh open.
        response = self.client.post("/api/token/mint", json={
            "event_id": "e3", "task_id": "recommendation", "recipient_id": "bob",
            "amount": "5", "evidence_hashes": ["sha:a"],
        })
        self.assertEqual(response.status_code, 400)

    def test_mint_validates_cap_and_members(self):
        self.create_ledger()
        response = self.client.post("/api/token/mint", json={
            "event_id": "e1", "task_id": "recommendation", "recipient_id": "alice",
            "amount": "120", "evidence_hashes": ["sha:a"],
        })
        self.assertEqual(response.status_code, 400)
        response = self.client.post("/api/token/mint", json={
            "event_id": "e1", "task_id": "recommendation", "recipient_id": "mallory",
            "amount": "10", "evidence_hashes": ["sha:a"],
        })
        self.assertEqual(response.status_code, 400)

    def test_contract_lifecycle_and_settlement(self):
        self.create_ledger()
        response = self.client.post("/api/token/contracts", json={
            "id": "c1", "task_id": "recommendation", "principal_id": "alice",
            "contractor_id": "bob", "contract_price": "50", "maximum_mint_value": "60",
        })
        self.assertEqual(response.status_code, 201, response.text)
        for status in ("OFFERED", "ACCEPTED", "CREDIT_RESERVED", "DELIVERED", "VERIFIED"):
            response = self.client.post("/api/token/contracts/c1/advance", json={"status": status})
            self.assertEqual(response.status_code, 200, response.text)
        response = self.client.post("/api/token/contracts/c1/advance", json={"status": "SETTLED"})
        self.assertEqual(response.status_code, 400)  # invalid transition
        response = self.client.post("/api/token/contracts/c1/settle", json={
            "verified_mint_value": "60", "evidence_hashes": ["sha:done"],
            "approver_ids": ["alice"],
        })
        self.assertEqual(response.status_code, 400)  # principal cannot approve
        response = self.client.post("/api/token/contracts/c1/settle", json={
            "verified_mint_value": "60", "evidence_hashes": ["sha:done"],
            "approver_ids": ["charlie"],
        })
        self.assertEqual(response.status_code, 200, response.text)
        ledger = self.client.get("/api/token/ledger").json()
        self.assertEqual(ledger["balances"]["alice"], 10.0)
        self.assertEqual(ledger["balances"]["bob"], 50.0)
        contracts = self.client.get("/api/token/contracts").json()
        self.assertEqual(contracts[0]["status"], "SETTLED")
        self.assertEqual(contracts[0]["verifiedMintValue"], 60.0)
        self.assertEqual(contracts[0]["approverIds"], ["charlie"])

    def test_confirm_mints_into_token_ledger(self):
        self.create_ledger()
        response = self.client.post("/api/contributions/core/reviews", json={
            "reviewer_id": "bob", "decision": "CONFIRM", "note": "",
        })
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["tokenMint"]["kind"], "DIRECT")
        self.assertEqual(body["tokenMint"]["amount"], 40.0)
        ledger = self.client.get("/api/token/ledger").json()
        self.assertEqual(ledger["balances"]["alice"], 40.0)
        self.assertEqual(ledger["totalSupply"], 40.0)

    def test_confirm_support_settles_commission(self):
        self.create_ledger()
        response = self.client.post("/api/contributions/help/reviews", json={
            "reviewer_id": "charlie", "decision": "CONFIRM", "note": "",
        })
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["tokenMint"]["kind"], "COMMISSION")
        ledger = self.client.get("/api/token/ledger").json()
        # V == P == 7: alice (principal) nets 0 after paying david (contractor).
        self.assertEqual(ledger["balances"]["alice"], 0.0)
        self.assertEqual(ledger["balances"]["david"], 7.0)
        self.assertEqual(ledger["totalSupply"], 7.0)

    def test_review_without_token_ledger_still_works(self):
        # No /api/token/project call: the legacy flow must behave exactly as before.
        response = self.client.post("/api/contributions/core/reviews", json={
            "reviewer_id": "bob", "decision": "CONFIRM", "note": "",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("tokenMint", response.json())
        self.assertFalse(self.token_db.exists())

    def test_dispute_does_not_mint(self):
        self.create_ledger()
        response = self.client.post("/api/contributions/core/reviews", json={
            "reviewer_id": "bob", "decision": "DISPUTE", "note": "Needs a second look",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("tokenMint", response.json())
        ledger = self.client.get("/api/token/ledger").json()
        self.assertEqual(ledger["totalSupply"], 0.0)

    def test_double_confirm_does_not_double_mint(self):
        self.create_ledger()
        self.client.post("/api/contributions/core/reviews", json={
            "reviewer_id": "bob", "decision": "CONFIRM", "note": "",
        })
        # A second VERIFIED transition is rejected by the legacy engine, so no
        # token mint can happen either; total supply stays at 40.
        response = self.client.post("/api/contributions/core/reviews", json={
            "reviewer_id": "charlie", "decision": "CONFIRM", "note": "",
        })
        self.assertEqual(response.status_code, 400)
        ledger = self.client.get("/api/token/ledger").json()
        self.assertEqual(ledger["totalSupply"], 40.0)

    def test_adjust_mints_as_verification(self):
        self.create_ledger()
        response = self.client.post("/api/contributions/core/reviews", json={
            "reviewer_id": "bob", "decision": "ADJUST", "note": "",
            "completion": "0.5",
        })
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["tokenMint"]["kind"], "DIRECT")
        self.assertEqual(body["tokenMint"]["amount"], 20.0)
        ledger = self.client.get("/api/token/ledger").json()
        self.assertEqual(ledger["balances"]["alice"], 20.0)
        self.assertEqual(ledger["totalSupply"], 20.0)

    def test_dispute_freezes_and_resolve_releases_minted_tokens(self):
        self.create_ledger()
        self.client.post("/api/contributions/core/reviews",
                         json={"reviewer_id": "bob", "decision": "CONFIRM"})
        dispute = self.client.post("/api/contributions/core/reviews", json={
            "reviewer_id": "alice", "decision": "DISPUTE", "note": "recheck",
        })
        self.assertEqual(dispute.status_code, 200, dispute.text)
        frozen = dispute.json()["tokenFrozen"]
        self.assertEqual(frozen["kind"], "FREEZE")
        ledger = self.client.get("/api/token/ledger").json()
        self.assertEqual(ledger["balances"]["alice"], 0.0)
        self.assertEqual(ledger["totalSupply"], 40.0)  # supply unchanged by FREEZE
        resolve = self.client.post("/api/contributions/core/resolve", json={
            "resolved_by": "bob", "resolution": "agreed", "completion": "1",
        })
        self.assertEqual(resolve.status_code, 200, resolve.text)
        body = resolve.json()
        self.assertEqual(body["tokenResolved"]["released"]["kind"], "RELEASE")
        self.assertNotIn("correction", body["tokenResolved"])  # final == frozen
        self.assertEqual(body["tokenResolved"]["finalAmount"], 40.0)
        ledger = self.client.get("/api/token/ledger").json()
        self.assertEqual(ledger["balances"]["alice"], 40.0)

    def test_resolve_after_dispute_can_mint_with_changed_score(self):
        self.create_ledger()
        self.client.post("/api/contributions/core/reviews",
                         json={"reviewer_id": "bob", "decision": "CONFIRM"})
        self.client.post("/api/contributions/core/reviews",
                         json={"reviewer_id": "alice", "decision": "DISPUTE", "note": "recheck"})
        resolve = self.client.post("/api/contributions/core/resolve", json={
            "resolved_by": "bob", "resolution": "lower value", "completion": "0.8",
        })
        self.assertEqual(resolve.status_code, 200, resolve.text)
        body = resolve.json()
        correction = body["tokenResolved"]["correction"]
        self.assertEqual(correction["kind"], "REFUND")
        self.assertEqual(correction["amount"], 8.0)
        ledger = self.client.get("/api/token/ledger").json()
        self.assertEqual(ledger["balances"]["alice"], 32.0)

    def test_corrupt_token_db_never_fails_committed_legacy_review(self):
        self.token_db.write_bytes(b"corrupted-not-sqlite")
        response = self.client.post("/api/contributions/core/reviews", json={
            "reviewer_id": "bob", "decision": "CONFIRM", "note": "",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("tokenMint", response.json())
        self.assertIn("skipped", response.json()["tokenMint"])
        self.assertEqual(ContributionStore(self.legacy_db).contributions["core"].status.value,
                         "VERIFIED")

    def test_corrupt_token_db_dispute_and_resolve_still_work(self):
        self.token_db.write_bytes(b"corrupted-not-sqlite")
        dispute = self.client.post("/api/contributions/core/reviews", json={
            "reviewer_id": "bob", "decision": "DISPUTE", "note": "recheck",
        })
        self.assertEqual(dispute.status_code, 200)
        resolve = self.client.post("/api/contributions/core/resolve", json={
            "resolved_by": "charlie", "resolution": "ok", "completion": "1",
        })
        self.assertEqual(resolve.status_code, 200)

    def test_token_write_storage_errors_are_400_not_500(self):
        self.create_ledger()
        self.token_db.write_bytes(b"corrupted-not-sqlite")
        response = self.client.post("/api/token/mint", json={
            "event_id": "e1", "task_id": "recommendation", "recipient_id": "alice",
            "amount": "10", "evidence_hashes": ["sha:a"],
        })
        self.assertEqual(response.status_code, 400, response.text)

    def test_freeze_and_release_over_http(self):
        self.create_ledger()
        self.client.post("/api/token/mint", json={
            "event_id": "e1", "task_id": "recommendation", "recipient_id": "alice",
            "amount": "40", "evidence_hashes": ["sha:a"],
        })
        import json as _json
        from token_store import TokenStore
        sequences = [e["sequence"] for e in
                     TokenStore(self.token_db).ledger_payload()["events"]
                     if e["kind"] == "MINT"]
        # Exercised through the store layer used by the review hooks.
        TokenStore(self.token_db).freeze_events(sequences, "争议")
        ledger = self.client.get("/api/token/ledger").json()
        self.assertEqual(ledger["balances"]["alice"], 0.0)
        TokenStore(self.token_db).release_events(sequences, "解决")
        self.assertEqual(self.client.get("/api/token/ledger").json()
                         ["balances"]["alice"], 40.0)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.legacy_db = Path(self.tmp.name) / "legacy.sqlite3"
        self.token_db = Path(self.tmp.name) / "token.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_migration_preserves_balances_and_conservation(self):
        build_legacy(self.legacy_db)
        client = TestClient(create_app(self.legacy_db, self.token_db))
        client.post("/api/token/project", json={
            "id": "fintech", "name": "FinTech", "treasury_id": "fintech-treasury",
            "member_ids": ["alice", "bob", "charlie", "david"],
        })
        client.post("/api/token/tasks", json={
            "id": "recommendation", "name": "Recommendation", "value_type": "CORE",
            "mint_cap": "100", "acceptance_criteria": "Working engine",
        })
        client.post("/api/contributions/core/reviews",
                    json={"reviewer_id": "bob", "decision": "CONFIRM"})
        client.post("/api/contributions/help/reviews",
                    json={"reviewer_id": "charlie", "decision": "CONFIRM"})
        before = self.legacy_db.read_bytes()

        migrated_db = Path(self.tmp.name) / "migrated.sqlite3"
        report = migrate_project(self.legacy_db, migrated_db, "fintech")
        self.assertEqual(self.legacy_db.read_bytes(), before)  # source untouched
        self.assertEqual(len(report["migrated"]), 2)
        self.assertEqual(report["balances"], {"alice": 40.0, "bob": 0.0,
                                              "charlie": 0.0, "david": 7.0})
        self.assertEqual(report["totalSupply"], 47.0)
        self.assertEqual(report["oldTeamTotal"], 47.0)
        self.assertTrue(report["conservation"])

        # The migrated ledger opens standalone and matches the live one.
        live = TestClient(create_app(self.legacy_db, self.token_db)).get("/api/token/ledger").json()
        migrated = TestClient(create_app(self.legacy_db, migrated_db)).get("/api/token/ledger").json()
        self.assertEqual(migrated["balances"], live["balances"])
        self.assertEqual(migrated["totalSupply"], live["totalSupply"])
        self.assertEqual(len(migrated["events"]), len(live["events"]))
        # Event order must match the stage-1 projection exactly, not just
        # totals and counts.
        view = ContributionStore(self.legacy_db, read_only=True).token_view("fintech")
        projected_ids = [event["id"] for event in view["events"]]
        migrated_ids = [event["id"] for event in migrated["events"]]
        self.assertEqual(migrated_ids, projected_ids)

    def test_source_is_opened_read_only(self):
        build_legacy(self.legacy_db)
        before = self.legacy_db.read_bytes()
        migrated_db = Path(self.tmp.name) / "migrated.sqlite3"
        migrate_project(self.legacy_db, migrated_db, "fintech")
        self.assertEqual(self.legacy_db.read_bytes(), before)

    def test_migration_refuses_to_overwrite(self):
        build_legacy(self.legacy_db)
        migrate_project(self.legacy_db, self.token_db, "fintech")
        with self.assertRaises(ValueError):
            migrate_project(self.legacy_db, self.token_db, "fintech")


if __name__ == "__main__":
    unittest.main()
