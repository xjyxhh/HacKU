"""Tests for TokenStore: durable replay of the token ledger (fusion PR1)."""

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from token_engine import (
    ContractStatus,
    LedgerEventType,
    TokenLedger,
    TokenProject,
    TokenTask,
    ValueType,
)
from token_store import TokenStore


PROJECT = TokenProject("fintech", "FinTech Demo", "treasury", ("alice", "bob", "charlie", "david"))
TASK = TokenTask("recommendation", "fintech", "Recommendation Engine", ValueType.CORE,
                 Decimal("100"), "A working recommendation engine with tests")


class TokenStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "token.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def open_store(self) -> TokenStore:
        return TokenStore(self.db)

    def new_store(self) -> TokenStore:
        store = TokenStore(self.db, PROJECT)
        store.add_task(TASK)
        return store

    def verified_contract(self, store, contract_id="commission-1", price="50", maximum="60"):
        store.create_commission(contract_id, "recommendation", "alice", "bob", price, maximum)
        for status in (
            ContractStatus.OFFERED,
            ContractStatus.ACCEPTED,
            ContractStatus.CREDIT_RESERVED,
            ContractStatus.VERIFIED,
        ):
            if status == ContractStatus.VERIFIED:
                store.deliver_commission(contract_id, ["sha:delivered"])
                store.advance_contract(contract_id, status)
                continue
            store.advance_contract(contract_id, status)
        return store.ledger.contracts[contract_id]

    def test_create_and_reopen_empty(self):
        self.new_store()
        store = self.open_store()
        self.assertEqual(store.project, PROJECT)
        self.assertEqual(store.ledger.tasks["recommendation"], TASK)
        self.assertEqual(store.total_supply(), Decimal("0"))
        self.assertEqual(store.balances(), {m: Decimal("0") for m in PROJECT.member_ids})

    def test_open_without_project_requires_existing_row(self):
        with self.assertRaises(ValueError):
            self.open_store()

    def test_create_project_twice_rejected(self):
        self.new_store()
        with self.assertRaises(ValueError):
            TokenStore(self.db, PROJECT)

    def test_mint_direct_survives_reopen(self):
        store = self.new_store()
        store.mint_direct("e1", "recommendation", "alice", "40", ["sha:evidence-a"])
        reopened = self.open_store()
        self.assertEqual(reopened.balance("alice"), Decimal("40"))
        self.assertEqual(reopened.total_supply(), Decimal("40"))
        self.assertEqual(reopened.minted_for_task("recommendation"), Decimal("40"))
        self.assertEqual(reopened.ledger.events, store.ledger.events)

    def test_duplicate_evidence_rejected_after_reopen(self):
        store = self.new_store()
        store.mint_direct("e1", "recommendation", "alice", "40", ["sha:evidence-a"])
        reopened = self.open_store()
        with self.assertRaises(ValueError):
            reopened.mint_direct("e2", "recommendation", "bob", "10", ["sha:evidence-a"])
        self.assertEqual(reopened.balance("bob"), Decimal("0"))

    def test_transfer_survives_reopen(self):
        store = self.new_store()
        store.mint_direct("e1", "recommendation", "alice", "40", ["sha:a"])
        store.transfer("e2", "alice", "bob", "15", "recommendation", ["sha:b"])
        reopened = self.open_store()
        self.assertEqual(reopened.balance("alice"), Decimal("25"))
        self.assertEqual(reopened.balance("bob"), Decimal("15"))
        self.assertEqual(reopened.total_supply(), Decimal("40"))

    def test_transfer_to_treasury_is_allowed(self):
        store = self.new_store()
        store.mint_direct("e1", "recommendation", "alice", "40", ["sha:a"])
        store.transfer("e2", "alice", "treasury", "10", "recommendation", ["sha:b"])
        reopened = self.open_store()
        self.assertEqual(reopened.balance("alice"), Decimal("30"))
        self.assertEqual(reopened.total_supply(), Decimal("30"))
        self.assertEqual(sum(reopened.balances().values(), Decimal("0")), reopened.total_supply())
        self.assertEqual(reopened.minted_for_task("recommendation"), Decimal("40"))

    def test_concurrent_writes_do_not_lose_updates(self):
        import threading
        store = self.new_store()
        store.mint_direct("e1", "recommendation", "alice", "40", ["sha:a"])
        errors = []

        def worker():
            try:
                TokenStore(self.db).mint_direct(
                    f"e-{threading.get_ident()}", "recommendation", "bob", "1", [f"sha:{threading.get_ident()}"],
                )
            except ValueError as error:
                errors.append(str(error))

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])  # in-flight replay means no stale-write rejections
        self.assertEqual(self.open_store().balance("bob"), Decimal("4"))

    def test_commission_settlement_survives_reopen(self):
        store = self.new_store()
        self.verified_contract(store)
        store.settle_commission("commission-1", "60", ["sha:delivered"], ["charlie"])
        reopened = self.open_store()
        # price 50 of the verified 60 goes to bob; alice keeps the remainder.
        self.assertEqual(reopened.balance("alice"), Decimal("10"))
        self.assertEqual(reopened.balance("bob"), Decimal("50"))
        self.assertEqual(reopened.total_supply(), Decimal("60"))
        contract = reopened.ledger.contracts["commission-1"]
        self.assertEqual(contract.status, ContractStatus.SETTLED)
        self.assertEqual(contract.verified_mint_value, Decimal("60"))
        self.assertEqual(contract.approver_ids, ["charlie"])
        self.assertEqual(contract.evidence_hashes, ["sha:delivered"])
        self.assertEqual(reopened.ledger.events[-1].kind, LedgerEventType.SPLIT)
        # A settled contract cannot be settled again, even after replay.
        with self.assertRaises(ValueError):
            reopened.settle_commission("commission-1", "60", ["sha:other"], ["david"])

    def test_refund_is_a_distinct_event_and_survives_reopen(self):
        store = self.new_store()
        store.mint_direct("mint", "recommendation", "alice", "40", ["sha:mint"])
        event, remaining = store.reconcile_refund(
            "dispute-1", "alice", "recommendation", "12", ["sha:refund"],
        )
        self.assertEqual(event.kind, LedgerEventType.REFUND)
        self.assertEqual(remaining, Decimal("0"))
        reopened = self.open_store()
        self.assertEqual(reopened.balance("alice"), Decimal("28"))
        self.assertEqual(reopened.total_supply(), Decimal("28"))
        self.assertEqual(reopened.ledger.events[-1].kind, LedgerEventType.REFUND)

    def test_failed_write_leaves_file_and_memory_unchanged(self):
        store = self.new_store()
        before = self.db.read_bytes()
        with self.assertRaises(ValueError):
            # mint cap is 100; 120 must be rejected
            store.mint_direct("e1", "recommendation", "alice", "120", ["sha:a"])
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(store.balance("alice"), Decimal("0"))
        self.assertEqual(store.ledger.events, [])
        # The store stays usable after the rejected write.
        store.mint_direct("e2", "recommendation", "alice", "40", ["sha:a"])
        self.assertEqual(self.open_store().balance("alice"), Decimal("40"))

    def test_failed_settlement_rolls_back_atomically(self):
        store = self.new_store()
        self.verified_contract(store)
        before = self.db.read_bytes()
        with self.assertRaises(ValueError):
            # alice is the principal and cannot approve her own contract
            store.settle_commission("commission-1", "60", ["sha:x"], ["alice"])
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(store.ledger.contracts["commission-1"].status, ContractStatus.VERIFIED)
        self.assertEqual(store.total_supply(), Decimal("0"))
        # A valid settlement still succeeds afterwards.
        store.settle_commission("commission-1", "60", ["sha:x"], ["charlie"])
        self.assertEqual(self.open_store().balance("bob"), Decimal("50"))

    def test_replay_matches_live_ledger_event_for_event(self):
        store = self.new_store()
        store.mint_direct("e1", "recommendation", "alice", "40", ["sha:a"])
        self.verified_contract(store)
        store.settle_commission("commission-1", "60", ["sha:b"], ["charlie"])
        store.transfer("e2", "bob", "david", "5", "recommendation", ["sha:c"])
        store.advance_contract.__wrapped__ if False else None  # keep lint quiet
        live = store.ledger
        replayed = self.open_store().ledger
        self.assertEqual(replayed.events, live.events)
        self.assertEqual(replayed.contracts, live.contracts)
        self.assertEqual(replayed.tasks, live.tasks)
        self.assertEqual(replayed._minted_evidence, live._minted_evidence)
        self.assertEqual(replayed._settled_contracts, live._settled_contracts)
        self.assertEqual(replayed.graph(), live.graph())

    def test_event_sequence_is_continuous_across_reopens(self):
        store = self.new_store()
        store.mint_direct("e1", "recommendation", "alice", "10", ["sha:a"])
        reopened = self.open_store()
        reopened.mint_direct("e2", "recommendation", "bob", "5", ["sha:b"])
        sequences = [event.sequence for event in self.open_store().ledger.events]
        self.assertEqual(sequences, [1, 2])

    def test_task_budget_reflects_reserved_contracts(self):
        store = self.new_store()
        store.create_commission("c1", "recommendation", "alice", "bob", "50", "60")
        reopened = self.open_store()
        budget = reopened.task_budget("recommendation")
        self.assertEqual(budget["mintCap"], Decimal("100"))
        self.assertEqual(budget["minted"], Decimal("0"))
        self.assertEqual(budget["reserved"], Decimal("60"))
        self.assertEqual(budget["available"], Decimal("40"))

    def test_freeze_release_survives_reopen(self):
        store = self.new_store()
        mint = store.mint_direct("e1", "recommendation", "alice", "40", ["sha:a"])
        store.freeze_events([mint.sequence], "争议")
        reopened = self.open_store()
        self.assertEqual(reopened.balance("alice"), Decimal("0"))
        self.assertEqual(reopened.total_supply(), Decimal("0"))
        with self.assertRaisesRegex(ValueError, "already been used"):
            reopened.mint_direct("duplicate-frozen", "recommendation", "bob", "10", ["sha:a"])
        reopened.release_events([mint.sequence], "解决")
        self.assertEqual(reopened.balance("alice"), Decimal("40"))
        replayed = self.open_store().ledger
        self.assertEqual(replayed._frozen_events, {})
        self.assertEqual(replayed._minted_evidence, reopened.ledger._minted_evidence)
        with self.assertRaisesRegex(ValueError, "already been used"):
            self.open_store().mint_direct("duplicate-released", "recommendation", "bob", "10", ["sha:a"])
        self.assertEqual(self.open_store().total_supply(), Decimal("40"))

    def test_open_without_project_rejects_when_file_has_no_ledger(self):
        with self.assertRaises(ValueError):
            TokenStore(self.db)

    def test_create_project_allows_other_projects_but_rejects_duplicate_project_id(self):
        self.new_store()
        other = TokenProject("other", "Other", "treasury", ("alice", "bob"))
        TokenStore(self.db, other)
        with self.assertRaises(ValueError):
            TokenStore(self.db, other)
        with self.assertRaisesRegex(ValueError, "project id is required"):
            TokenStore(self.db)

    def test_project_ledgers_are_isolated_with_reused_local_identifiers(self):
        first = TokenStore(
            self.db, TokenProject("first", "First", "first-treasury", ("alice",))
        )
        first.add_task(TokenTask("task", "first", "Task", ValueType.CORE,
                                 Decimal("20"), "Acceptance"))
        first.mint_direct("mint", "task", "alice", "10", ["first-proof"])

        second = TokenStore(
            self.db, TokenProject("second", "Second", "second-treasury", ("alice",))
        )
        second.add_task(TokenTask("task", "second", "Task", ValueType.CORE,
                                  Decimal("20"), "Acceptance"))
        second.mint_direct("mint", "task", "alice", "5", ["second-proof"])

        first_reopened = TokenStore(self.db, project_id="first")
        second_reopened = TokenStore(self.db, project_id="second")
        self.assertEqual(first_reopened.balance("alice"), Decimal("10"))
        self.assertEqual(second_reopened.balance("alice"), Decimal("5"))
        self.assertEqual(first_reopened.ledger_payload()["events"][0]["sequence"], 1)
        self.assertEqual(second_reopened.ledger_payload()["events"][0]["sequence"], 1)

    def test_ledger_payload_shape(self):
        store = self.new_store()
        store.mint_direct("e1", "recommendation", "alice", "40", ["sha:a"])
        payload = self.open_store().ledger_payload()
        self.assertEqual(payload["projectId"], "fintech")
        self.assertEqual(payload["treasuryId"], "treasury")
        self.assertEqual(payload["totalSupply"], 40.0)
        self.assertEqual(payload["balances"]["alice"], 40.0)
        self.assertEqual(payload["balances"]["bob"], 0.0)
        self.assertEqual(len(payload["events"]), 1)
        event = payload["events"][0]
        self.assertEqual(event["kind"], "MINT")
        self.assertEqual(event["amount"], 40.0)
        self.assertEqual(event["destinationId"], "alice")
        self.assertEqual(event["taskId"], "recommendation")


if __name__ == "__main__":
    unittest.main()
