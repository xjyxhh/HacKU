import tempfile
import unittest
import sqlite3
from pathlib import Path

from token_engine import ContractStatus, LedgerEventType, TokenProject, TokenTask, ValueType
from token_store import TokenStore


class ContractResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "token.sqlite3"
        self.store = TokenStore(self.path, TokenProject("p", "Project", "treasury", ("alice", "bob", "carol")))
        self.store.add_task(TokenTask("task", "p", "Task", ValueType.CORE, 100, "Complete"))
        self.store.create_commission("c", "task", "alice", "bob", 50, 60)
        for status in (ContractStatus.OFFERED, ContractStatus.ACCEPTED, ContractStatus.CREDIT_RESERVED,
                       ContractStatus.DELIVERED, ContractStatus.VERIFIED):
            self.store.advance_contract("c", status)
        self.store.settle_commission("c", 60, ["evidence:c"], ["carol"])

    def settle_dispute(self):
        self.store.dispute_contract("c", "alice", "Delivery was incomplete")
        self.store.freeze_contract_payment("c", "Hold payment")

    def test_refund_and_reopen_preserves_supply_and_clears_escrow(self):
        self.settle_dispute()
        resolution, events = self.store.resolve_contract("c", "REFUND", "Return full payment", "carol")
        reopened = TokenStore(self.path)
        self.assertEqual(reopened.balance("alice"), 60)
        self.assertEqual(reopened.balance("bob"), 0)
        self.assertEqual(reopened.total_supply(), 60)
        self.assertEqual(reopened.ledger.contracts["c"].status, ContractStatus.RESOLVED)
        self.assertEqual(resolution["refundAmount"], 50)
        self.assertEqual([event.kind for event in events], [LedgerEventType.REFUND])
        self.assertFalse(reopened.ledger._frozen_events)
        with self.assertRaisesRegex(ValueError, "must be frozen"):
            reopened.resolve_contract("c", "REFUND", "again", "carol")

    def test_split_reconciles_exactly_without_new_mint_or_budget(self):
        self.settle_dispute()
        resolution, events = self.store.resolve_contract("c", "SPLIT", "Split fairly", "carol", 20)
        reopened = TokenStore(self.path)
        self.assertEqual(reopened.balance("alice"), 30)
        self.assertEqual(reopened.balance("bob"), 30)
        self.assertEqual(reopened.total_supply(), 60)
        self.assertEqual(reopened.minted_for_task("task"), 60)
        self.assertEqual(reopened.task_budget("task")["available"], 40)
        self.assertEqual([event.kind for event in events], [LedgerEventType.SPLIT, LedgerEventType.SPLIT])
        self.assertEqual(resolution["refundAmount"] + resolution["retainedAmount"], 50)

    def test_insufficient_balance_keeps_dispute_unfrozen(self):
        self.store.transfer("spent", "bob", "carol", 40, "task", ["transfer:spent"])
        self.store.dispute_contract("c", "alice", "Delivery was incomplete")
        with self.assertRaisesRegex(ValueError, "insufficient token balance"):
            self.store.freeze_contract_payment("c", "Hold payment")
        reopened = TokenStore(self.path)
        self.assertEqual(reopened.ledger.contracts["c"].status, ContractStatus.DISPUTED)
        self.assertFalse(reopened.ledger._frozen_events)

    def test_old_contract_status_check_migrates_without_losing_rows(self):
        path = Path(self.temp.name) / "old.sqlite3"
        schema = Path(__file__).with_name("token_schema.sql").read_text(encoding="utf-8")
        old_schema = schema.replace("'FROZEN', 'SETTLED', 'RESOLVED'", "'FROZEN', 'SETTLED'")
        with sqlite3.connect(path) as conn:
            conn.executescript(old_schema)
            conn.execute("INSERT INTO token_projects VALUES(?,?,?,?)", ("p", "Project", "treasury", '["alice","bob","carol"]'))
            conn.execute("INSERT INTO token_tasks VALUES(?,?,?,?,?,?)", ("task", "p", "Task", "CORE", "100", "Complete"))
            conn.execute("INSERT INTO commission_contracts(id,project_id,task_id,principal_id,contractor_id,value_type,contract_price,maximum_mint_value,acceptance_criteria_hash,status,row_sequence) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                         ("legacy", "p", "task", "alice", "bob", "CORE", "50", "60", "hash", "SETTLED", 0))
        migrated = TokenStore(path)
        self.assertEqual(migrated.ledger.contracts["legacy"].status, ContractStatus.SETTLED)
        with sqlite3.connect(path) as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertTrue(conn.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='commission_contracts_by_project'").fetchone())


if __name__ == "__main__":
    unittest.main()
