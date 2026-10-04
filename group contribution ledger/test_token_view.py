"""Stage-1 token projection: read-only behavior, conservation, and the SUPPORT mapping."""

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from contribution_store import ContributionStore
from dashboard_server import create_app


def build(path):
    """Create a fixed four-member project covering direct, support, pending and disputed work."""
    store = ContributionStore(path)
    store.create_project("fintech", "FinTech")
    for member in ("alice", "bob", "charlie", "david"):
        store.add_member("fintech", member, member.title())
    store.add_task("fintech", "recommendation", "Recommendation", "40", "Working engine")
    store.add_task("fintech", "dashboard", "Dashboard", "25")
    store.submit_contribution("fintech", "core", "alice", "recommendation", "CORE", "Built engine")
    store.submit_contribution("fintech", "second", "bob", "dashboard", "CORE", "Built dashboard")
    store.submit_contribution("fintech", "help", "david", "recommendation", "SUPPORT", "Helped Alice",
                              support_value="7", helped_member_id="alice")
    store.submit_contribution("fintech", "pending", "charlie", "recommendation", "REVIEW", "Reviewed",
                              support_value="3")
    store.submit_contribution("fintech", "disputed", "charlie", "dashboard", "COORDINATION", "Coordinated",
                              support_value="4")
    store = ContributionStore(path)
    store.review_contribution("core", "bob", "CONFIRM")
    store.review_contribution("second", "alice", "ADJUST", completion="0.8")
    store.review_contribution("help", "charlie", "CONFIRM")
    store.review_contribution("help", "charlie", "DISPUTE", "Recheck the value")
    store.resolve_dispute("help", "charlie", "Agreed on 7", support_value="7")
    store.review_contribution("disputed", "alice", "DISPUTE", "Needs verification")
    return store


class TokenViewTests(unittest.TestCase):
    def test_projection_restates_legacy_totals(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.sqlite3"
            store = build(path)
            legacy = {member_id: float(score.total_score)
                      for member_id, score in store.project_scores("fintech").items()}
            view = store.token_view("fintech")

            self.assertEqual(legacy, {"alice": 40.0, "bob": 20.0, "charlie": 0.0, "david": 7.0})
            self.assertEqual(view["oldTeamTotal"], 67.0)
            self.assertEqual(view["totalSupply"], view["oldTeamTotal"])
            self.assertEqual({row["memberId"]: row["balance"] for row in view["balances"]}, legacy)
            self.assertEqual(sum(row["balance"] for row in view["balances"]), view["totalSupply"])
            alice = next(row for row in view["balances"] if row["memberId"] == "alice")
            self.assertEqual((alice["minted"], alice["paid"], alice["balance"]), (47.0, 7.0, 40.0))

    def test_projection_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.sqlite3"
            store = build(path)
            before = path.read_bytes()
            store.token_view("fintech")
            store.dashboard_data("fintech")
            self.assertEqual(path.read_bytes(), before)

    def test_support_becomes_a_settled_commission(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.sqlite3"
            view = build(path).token_view("fintech")

            self.assertEqual(len(view["contracts"]), 1)
            contract = view["contracts"][0]
            self.assertEqual(contract["principalId"], "alice")
            self.assertEqual(contract["contractorId"], "david")
            self.assertEqual(contract["contractPrice"], 7.0)
            self.assertEqual(contract["verifiedMintValue"], 7.0)
            self.assertEqual(contract["status"], "SETTLED")
            self.assertEqual(contract["approverIds"], ["charlie"])
            kinds = [event["kind"] for event in view["events"]]
            self.assertEqual(kinds.count("MINT"), 3)
            self.assertEqual(kinds.count("TRANSFER"), 1)

    def test_pending_and_disputed_are_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.sqlite3"
            view = build(path).token_view("fintech")
            self.assertEqual({row["contributionId"] for row in view["skipped"]}, {"pending", "disputed"})
            self.assertTrue(all(row["reason"] for row in view["skipped"]))

    def test_support_without_independent_approver_is_direct(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.sqlite3"
            store = ContributionStore(path)
            store.create_project("pair", "Pair")
            store.add_member("pair", "alice", "Alice")
            store.add_member("pair", "bob", "Bob")
            store.add_task("pair", "task", "Task", "10")
            store.submit_contribution("pair", "help", "bob", "task", "SUPPORT", "Helped Alice",
                                      support_value="5", helped_member_id="alice")
            store = ContributionStore(path)
            store.review_contribution("help", "alice", "CONFIRM")

            view = ContributionStore(path).token_view("pair")
            self.assertEqual(view["totalSupply"], 5.0)
            self.assertEqual(view["contracts"], [])
            self.assertEqual(view["events"][0]["id"], "help:mint")
            self.assertEqual(view["contracts"], [])

    def test_dashboard_data_exposes_balances(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.sqlite3"
            store = build(path)
            dashboard = store.dashboard_data("fintech")
            self.assertEqual({row["memberId"]: row["balance"] for row in dashboard["balances"]},
                             {"alice": 40.0, "bob": 20.0, "charlie": 0.0, "david": 7.0})

    def test_unknown_project_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.sqlite3"
            with self.assertRaisesRegex(ValueError, "unknown project"):
                build(path).token_view("missing")

    def test_token_view_api(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.sqlite3"
            build(path)
            with TestClient(create_app(path)) as client:
                response = client.get("/api/projects/fintech/token-view")
                self.assertEqual(response.status_code, 200)
                view = response.json()
                self.assertEqual(view["totalSupply"], 67.0)
                self.assertEqual(len(view["balances"]), 4)
                self.assertEqual(client.get("/api/projects/missing/token-view").status_code, 404)
                self.assertEqual(
                    client.get("/api/projects/fintech/dashboard").json()["balances"][0]["memberId"], "alice")


if __name__ == "__main__":
    unittest.main()
