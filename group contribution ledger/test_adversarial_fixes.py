"""Regression cases for ledger initialization and portable snapshots."""

import tempfile
import threading
import sqlite3
import json
import time
import unittest
from pathlib import Path

from contribution_store import ContributionStore
from export_json import export_json
from import_json import import_json
from merge_sqlite import merge
from migrate_token_ledger import migrate_project
from token_engine import TokenProject, TokenTask, ValueType
from token_store import TokenStore
from dashboard_server import create_app
from fastapi.testclient import TestClient as BareTestClient
from test_auth_support import AuthenticatedClient


class AdversarialFixTests(unittest.TestCase):
    def test_token_writes_need_session_and_nonfinite_json_is_422(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = create_app(root / "data.sqlite3", root / "token.sqlite3")
            client = AuthenticatedClient(app)
            anonymous = BareTestClient(app)
            body = {"id": "p", "name": "Project", "treasury_id": "treasury", "member_ids": ["alice"]}
            self.assertEqual(anonymous.post("/api/token/project", json=body).status_code, 401)
            self.assertEqual(anonymous.post("/api/projects", json={"id": "p", "name": "Project"}).status_code, 401)
            self.assertEqual(client.post("/api/token/project", json=body,
                                         headers={"X-Token-Admin-Key": "ignored"}).status_code, 201)
            self.assertEqual(client.post("/api/token/tasks", content=b'{"id":"t","name":"T","value_type":"CORE","mint_cap":NaN,"acceptance_criteria":"done"}',
                                         headers={"Content-Type": "application/json", "X-Token-Admin-Key": "secret"}).status_code, 422)
            too_large = client.post("/api/token/tasks", json={
                "id": "t", "name": "Task", "value_type": "CORE",
                "mint_cap": "1e400", "acceptance_criteria": "Done",
            }, headers={"X-Token-Admin-Key": "secret"})
            self.assertEqual(too_large.status_code, 400)
            self.assertEqual(client.get("/api/token/tasks").json(), [])

    def test_support_dispute_and_resolution_match_legacy_score(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy_path, token_path = root / "data.sqlite3", root / "token.sqlite3"
            legacy = ContributionStore(legacy_path)
            legacy.create_project("p", "Project")
            for member in ("a", "b", "c"):
                legacy.add_member("p", member, member)
            legacy.add_task("p", "t", "Task", 10)
            legacy.submit_contribution("p", "help", "b", "t", "SUPPORT", "Helped a",
                                       support_value=7, helped_member_id="a")
            token = TokenStore(token_path, TokenProject("p", "Project", "treasury", ("a", "b", "c")))
            token.add_task(TokenTask("t", "p", "Task", ValueType.CORE, 10, "Done"))
            client = AuthenticatedClient(create_app(legacy_path, token_path),
                                headers={"X-Token-Admin-Key": "secret"})
            confirm = client.post("/api/contributions/help/reviews",
                                  json={"reviewer_id": "c", "decision": "CONFIRM"})
            self.assertEqual(confirm.status_code, 200, confirm.text)
            self.assertEqual(client.get("/api/token/ledger").json()["balances"]["b"], 7)
            dispute = client.post("/api/contributions/help/reviews",
                                  json={"reviewer_id": "c", "decision": "DISPUTE", "note": "recheck"})
            self.assertEqual(dispute.status_code, 200, dispute.text)
            self.assertEqual(client.get("/api/token/ledger").json()["balances"]["b"], 0)
            resolve = client.post("/api/contributions/help/resolve",
                                  json={"resolved_by": "c", "resolution": "three points", "support_value": 3})
            self.assertEqual(resolve.status_code, 200, resolve.text)
            self.assertEqual(client.get("/api/token/ledger").json()["balances"]["b"], 3)
            self.assertEqual(client.get("/api/token/ledger").json()["totalSupply"], 3)
            ContributionStore(legacy_path).submit_contribution(
                "p", "help2", "b", "t", "SUPPORT", "Helped a again",
                support_value=7, helped_member_id="a",
            )
            self.assertEqual(client.post("/api/token/tasks/t/cap", json={"mint_cap": 20}).status_code, 200)
            second = client.post("/api/contributions/help2/reviews",
                                 json={"reviewer_id": "c", "decision": "CONFIRM"})
            self.assertEqual(second.status_code, 200, second.text)
            spent = client.post("/api/token/transfer", json={
                "event_id": "spent", "source_id": "b", "destination_id": "c",
                "amount": 10, "task_id": "t", "evidence_hashes": ["spent-proof"],
            })
            self.assertEqual(spent.status_code, 201, spent.text)
            client.post("/api/contributions/help2/reviews",
                        json={"reviewer_id": "c", "decision": "DISPUTE", "note": "recheck"})
            second = client.post("/api/contributions/help2/resolve",
                                 json={"resolved_by": "c", "resolution": "three points", "support_value": 3})
            self.assertEqual(second.status_code, 200, second.text)
            self.assertEqual(second.json()["tokenResolved"]["correction"]["debtExact"], "4")
            self.assertEqual(client.get("/api/token/ledger").json()["balances"]["b"], 0)
            self.assertEqual(client.get("/api/token/debts").json()[0]["remainingExact"], "4")

    def test_incomplete_file_can_be_initialized(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token.sqlite3"
            path.touch()
            with self.assertRaises(ValueError):
                TokenStore(path)
            project = TokenProject("p", "Project", "treasury", ("alice",))
            TokenStore(path, project)
            self.assertEqual(TokenStore(path).project, project)

    def test_token_tables_can_share_existing_legacy_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "combined.sqlite3"
            ContributionStore(path).create_project("p", "Project")
            project = TokenProject("p", "Project", "treasury", ("alice",))
            TokenStore(path, project)
            self.assertEqual(TokenStore(path).project, project)
            self.assertEqual(ContributionStore(path).projects["p"].name, "Project")

    def test_concurrent_initialization_keeps_one_project(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token.sqlite3"
            outcomes = []
            barrier = threading.Barrier(6)
            def create(index):
                barrier.wait()
                try:
                    TokenStore(path, TokenProject(f"p{index}", "Project", "treasury", ("alice",)))
                    outcomes.append("created")
                except ValueError:
                    outcomes.append("rejected")
            workers = [threading.Thread(target=create, args=(index,)) for index in range(6)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join()
            self.assertEqual(outcomes.count("created"), 1)
            self.assertEqual(outcomes.count("rejected"), 5)
            self.assertTrue(TokenStore(path).project.id.startswith("p"))

    def test_read_does_not_wait_for_writer_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token.sqlite3"
            project = TokenProject("p", "Project", "treasury", ("a",))
            TokenStore(path, project)
            with sqlite3.connect(path) as writer:
                writer.execute("BEGIN IMMEDIATE")
                start = time.monotonic()
                self.assertEqual(TokenStore(path).project, project)
                self.assertLess(time.monotonic() - start, 2)

    def test_token_snapshot_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "data.sqlite3"
            token = root / "token.sqlite3"
            ContributionStore(legacy).create_project("p", "Project")
            store = TokenStore(token, TokenProject("p", "Project", "treasury", ("alice",)))
            store.add_task(TokenTask("t", "p", "Task", ValueType.CORE, 10, "Done"))
            store.mint_direct("m", "t", "alice", 3, ["proof"])
            snapshot = root / "snapshot.json"
            export_json(legacy, snapshot)
            restored = root / "restored"
            restored.mkdir()
            import_json(snapshot, restored / "data.sqlite3")
            self.assertEqual(TokenStore(restored / "token.sqlite3").ledger_payload(), store.ledger_payload())

    def test_import_rejects_invalid_value_without_leaving_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "original.sqlite3"
            store = ContributionStore(source)
            store.create_project("p", "Project")
            store.add_task("p", "t", "Task", "1")
            snapshot = root / "snapshot.json"
            export_json(source, snapshot)
            data = json.loads(snapshot.read_text(encoding="utf-8"))
            data["tasks"][0]["task_value"] = "-10"
            snapshot.write_text(json.dumps(data), encoding="utf-8")
            destination = root / "restored.sqlite3"
            with self.assertRaisesRegex(ValueError, "task_value"):
                import_json(snapshot, destination)
            self.assertFalse(destination.exists())

    def test_two_merges_in_one_second_get_distinct_backups(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "data.sqlite3"
            ContributionStore(target).create_project("main", "Main")
            backups = []
            for index in (1, 2):
                source = root / f"source{index}.sqlite3"
                ContributionStore(source).create_project(f"p{index}", f"Project {index}")
                backup, _, _ = merge(target, source)
                backups.append(backup)
            self.assertNotEqual(*backups)
            self.assertTrue(all(path.exists() for path in backups))

    def test_exact_amount_fields_preserve_decimal_precision(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token.sqlite3"
            store = TokenStore(path, TokenProject("p", "Project", "treasury", ("a",)))
            store.add_task(TokenTask("t", "p", "Task", ValueType.CORE,
                                     "0.1234567890123456789012345", "Done"))
            store.mint_direct("m", "t", "a", "0.1234567890123456789012345", ["proof"])
            payload = TokenStore(path).ledger_payload()
            self.assertEqual(payload["totalSupplyExact"], "0.1234567890123456789012345")
            self.assertEqual(payload["events"][0]["amountExact"], "0.1234567890123456789012345")

    def test_migration_preserves_support_without_inventing_approver(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "data.sqlite3", root / "token.sqlite3"
            store = ContributionStore(source)
            store.create_project("p", "Project")
            store.add_member("p", "a", "A")
            store.add_member("p", "b", "B")
            store.add_task("p", "t", "Task", 10)
            store.submit_contribution("p", "help", "b", "t", "SUPPORT", "Helped a",
                                      support_value=5, helped_member_id="a")
            store.review_contribution("help", "a", "CONFIRM")
            report = migrate_project(source, target, "p")
            self.assertEqual(report["migrated"][0]["kind"], "DIRECT")
            self.assertEqual(TokenStore(target).ledger.contracts, {})
            self.assertEqual(TokenStore(target).balance("b"), 5)

    def test_support_without_helped_member_projects_as_direct_credit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "data.sqlite3", root / "token.sqlite3"
            store = ContributionStore(source)
            store.create_project("p", "Project")
            store.add_member("p", "a", "A")
            store.add_member("p", "b", "B")
            store.add_task("p", "t", "Task", 10)
            store.submit_contribution("p", "help", "b", "t", "SUPPORT", "General support",
                                      support_value=5)
            store.review_contribution("help", "a", "CONFIRM")
            view = store.token_view("p")
            self.assertEqual(view["totalSupplyExact"], "5")
            self.assertFalse(view["skipped"])
            report = migrate_project(source, target, "p")
            self.assertTrue(report["conservation"])
            self.assertEqual(TokenStore(target).balance("b"), 5)

    def test_atomic_commission_rolls_back_on_cap_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token.sqlite3"
            store = TokenStore(path, TokenProject("p", "Project", "treasury", ("a", "b", "c")))
            store.add_task(TokenTask("t", "p", "Task", ValueType.CORE, 10, "Done"))
            store.mint_direct("m", "t", "a", 6, ["one"])
            with self.assertRaisesRegex(ValueError, "cap exceeded"):
                store.settle_legacy_commission("commission", "t", "a", "b", 5, ["two"], ["c"])
            self.assertEqual(TokenStore(path).ledger.contracts, {})

    def test_commission_payment_freezes_without_negative_balance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token.sqlite3"
            store = TokenStore(path, TokenProject("p", "Project", "treasury", ("a", "b", "c")))
            store.add_task(TokenTask("t", "p", "Task", ValueType.CORE, 10, "Done"))
            _, payment = store.settle_legacy_commission("commission", "t", "a", "b", 7,
                                                         ["proof"], ["c"])
            store.freeze_events([payment.sequence], "dispute")
            reopened = TokenStore(path)
            self.assertEqual(reopened.balance("a"), 0)
            self.assertEqual(reopened.balance("b"), 0)
            reopened.release_events([payment.sequence], "resolved")
            self.assertEqual(TokenStore(path).balance("b"), 7)
            TokenStore(path).freeze_events([payment.sequence], "disputed again")
            self.assertEqual(TokenStore(path).balance("b"), 0)
            graph = TokenStore(path).graph_payload()
            nodes = {tuple(node["address"]) for node in graph["nodes"]}
            self.assertTrue(all(tuple(edge["source"]) in nodes and tuple(edge["destination"]) in nodes
                                for edge in graph["edges"]))

    def test_refund_shortfall_is_recorded_and_collectible(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token.sqlite3"
            store = TokenStore(path, TokenProject("p", "Project", "treasury", ("a", "b")))
            store.add_task(TokenTask("t", "p", "Task", ValueType.CORE, 20, "Done"))
            store.mint_direct("mint", "t", "a", 7, ["proof"])
            store.transfer("out", "a", "b", 7, "t", ["out-proof"])
            event, remaining = store.reconcile_refund("c1", "a", "t", 4, ["resolve"])
            self.assertIsNone(event)
            self.assertEqual(remaining, 4)
            self.assertEqual(TokenStore(path).debts_payload()[0]["remainingExact"], "4")
            store.transfer("return", "b", "a", 4, "t", ["return-proof"])
            collected = store.collect_debt("c1")
            self.assertEqual(collected["remainingExact"], "0")
            self.assertEqual(TokenStore(path).total_supply(), 3)

    def test_sql_schema_rejects_orphan_and_nonnumeric_events(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token.sqlite3"
            store = TokenStore(path, TokenProject("p", "Project", "treasury", ("a",)))
            store.add_task(TokenTask("t", "p", "Task", ValueType.CORE, 10, "Done"))
            with sqlite3.connect(path) as conn:
                conn.execute("PRAGMA foreign_keys = ON")
                for task_id, amount in (("missing", "1"), ("t", "not-a-number")):
                    with self.assertRaises(sqlite3.IntegrityError):
                        conn.execute(
                            "INSERT INTO ledger_events (id, project_id, kind, amount, source_id, destination_id, task_id, evidence_key) "
                            "VALUES (?, 'p', 'MINT', ?, 'treasury', 'a', ?, 'proof')",
                            (f"bad-{task_id}", amount, task_id),
                        )

    def test_legacy_schema_rejects_cross_project_review(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.sqlite3"
            store = ContributionStore(path)
            store.create_project("p", "Project")
            store.create_project("q", "Other")
            store.add_member("p", "alice", "Alice")
            store.add_member("q", "bob", "Bob")
            store.add_task("p", "t", "Task", 1)
            store.submit_contribution("p", "c", "alice", "t", "CORE", "Done")
            with sqlite3.connect(path) as conn:
                conn.execute("PRAGMA foreign_keys = ON")
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute("INSERT INTO verifications (id, contribution_id, reviewer_id, decision) "
                                 "VALUES ('v', 'c', 'bob', 'CONFIRM')")


if __name__ == "__main__":
    unittest.main()
