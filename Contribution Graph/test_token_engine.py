"""Focused tests for role A's token ledger and graph engine."""

import unittest
from decimal import Decimal

from token_engine import (
    ContractStatus,
    LedgerEventType,
    ProductionMode,
    TokenLedger,
    TokenProject,
    TokenTask,
    ValueType,
)


class TokenEngineTests(unittest.TestCase):
    def setUp(self):
        project = TokenProject("fintech", "FinTech Demo", "treasury", ("alice", "bob", "charlie", "david"))
        self.ledger = TokenLedger(project)
        self.ledger.add_task(TokenTask(
            "recommendation", "fintech", "Recommendation Engine", ValueType.CORE,
            Decimal("100"), "A working recommendation engine with tests",
        ))

    def verified_contract(self, contract_id="commission-1", price="50", maximum="60"):
        contract = self.ledger.create_commission(
            contract_id, "recommendation", "alice", "bob", price, maximum,
        )
        for status in (
            ContractStatus.OFFERED,
            ContractStatus.ACCEPTED,
            ContractStatus.CREDIT_RESERVED,
            ContractStatus.DELIVERED,
            ContractStatus.VERIFIED,
        ):
            self.ledger.advance_contract(contract.id, status)
        return contract

    def test_value_types_and_production_modes(self):
        self.assertEqual({item.value for item in ValueType}, {"CORE", "REVIEW", "COORDINATION"})
        self.assertEqual({item.value for item in ProductionMode}, {"DIRECT", "COMMISSIONED"})

    def test_direct_mint_changes_supply_and_balance_once(self):
        self.ledger.mint_direct("mint-1", "recommendation", "alice", "40", ["sha256:artifact-1"])
        self.assertEqual(self.ledger.balance("alice"), Decimal("40"))
        self.assertEqual(self.ledger.total_supply(), Decimal("40"))
        self.assertEqual(self.ledger.minted_for_task("recommendation"), Decimal("40"))
        with self.assertRaisesRegex(ValueError, "already been used"):
            self.ledger.mint_direct("mint-2", "recommendation", "bob", "10", ["sha256:artifact-1"])

    def test_commission_mints_60_and_splits_10_50(self):
        contract = self.verified_contract()
        mint, payment = self.ledger.settle_commission(
            contract.id, "60", ["sha256:core-result"], ["charlie"],
        )
        self.assertEqual((mint.amount, payment.amount), (Decimal("60"), Decimal("50")))
        self.assertEqual(self.ledger.balances(), {
            "alice": Decimal("10"),
            "bob": Decimal("50"),
            "charlie": Decimal("0"),
            "david": Decimal("0"),
        })
        self.assertEqual(self.ledger.total_supply(), Decimal("60"))
        self.assertEqual(sum(self.ledger.balances().values(), Decimal("0")), Decimal("60"))
        self.assertEqual(contract.status, ContractStatus.SETTLED)

    def test_payment_is_capped_by_verified_value(self):
        contract = self.verified_contract(price="50", maximum="60")
        _, payment = self.ledger.settle_commission(
            contract.id, "40", ["sha256:partial-result"], ["charlie"],
        )
        self.assertEqual(payment.amount, Decimal("40"))
        self.assertEqual(self.ledger.balances()["alice"], Decimal("0"))
        self.assertEqual(self.ledger.balances()["bob"], Decimal("40"))
        self.assertEqual(self.ledger.total_supply(), Decimal("40"))

    def test_settlement_requires_verified_state_and_independent_approver(self):
        contract = self.ledger.create_commission(
            "commission-1", "recommendation", "alice", "bob", "50", "60",
        )
        with self.assertRaisesRegex(ValueError, "verified"):
            self.ledger.settle_commission(contract.id, "60", ["sha256:x"], ["charlie"])
        for status in (ContractStatus.OFFERED, ContractStatus.ACCEPTED,
                       ContractStatus.CREDIT_RESERVED, ContractStatus.DELIVERED,
                       ContractStatus.VERIFIED):
            self.ledger.advance_contract(contract.id, status)
        with self.assertRaisesRegex(ValueError, "independently approve"):
            self.ledger.settle_commission(contract.id, "60", ["sha256:x"], ["alice"])
        self.assertEqual(self.ledger.events, [])
        self.assertEqual(contract.status, ContractStatus.VERIFIED)

    def test_mint_cap_and_contract_invariants(self):
        with self.assertRaisesRegex(ValueError, "different"):
            self.ledger.create_commission("same", "recommendation", "alice", "alice", "10", "20")
        with self.assertRaisesRegex(ValueError, "contract price"):
            self.ledger.create_commission("expensive", "recommendation", "alice", "bob", "61", "60")
        self.ledger.mint_direct("mint-1", "recommendation", "alice", "90", ["sha256:first"])
        with self.assertRaisesRegex(ValueError, "mint cap"):
            self.ledger.mint_direct("mint-2", "recommendation", "bob", "11", ["sha256:second"])
        self.assertEqual(self.ledger.total_supply(), Decimal("90"))

    def test_contract_cannot_settle_twice(self):
        contract = self.verified_contract()
        self.ledger.settle_commission(contract.id, "60", ["sha256:core-result"], ["charlie"])
        with self.assertRaisesRegex(ValueError, "already settled"):
            self.ledger.settle_commission(contract.id, "60", ["sha256:another"], ["david"])
        self.assertEqual(len(self.ledger.events), 2)

    def test_transfers_do_not_increase_total_supply(self):
        self.ledger.mint_direct("mint-1", "recommendation", "alice", "60", ["sha256:seed"])
        self.ledger.transfer("pay-1", "alice", "bob", "20", "recommendation", ["sha256:pay-1"])
        self.ledger.transfer("pay-2", "bob", "alice", "20", "recommendation", ["sha256:pay-2"])
        self.assertEqual(self.ledger.total_supply(), Decimal("60"))
        self.assertEqual(self.ledger.balances()["alice"], Decimal("60"))
        self.assertEqual(self.ledger.balances()["bob"], Decimal("0"))

    def test_task_budget_accounts_for_minted_and_reserved(self):
        self.ledger.mint_direct("mint-1", "recommendation", "alice", "20", ["sha256:seed"])
        contract = self.ledger.create_commission(
            "commission-1", "recommendation", "alice", "bob", "30", "50",
        )
        self.ledger.advance_contract(contract.id, ContractStatus.OFFERED)
        budget = self.ledger.task_budget("recommendation")
        self.assertEqual(budget, {
            "mintCap": Decimal("100"), "minted": Decimal("20"),
            "reserved": Decimal("50"), "available": Decimal("30"),
        })

    def test_graph_explains_commission_execution_mint_and_payment(self):
        contract = self.verified_contract()
        self.ledger.settle_commission(contract.id, "60", ["sha256:core-result"], ["charlie"])
        graph = self.ledger.graph()
        edge_kinds = [edge.kind for edge in graph.edges]
        self.assertIn("COMMISSIONED", edge_kinds)
        self.assertIn("EXECUTED", edge_kinds)
        self.assertIn("CONTRIBUTES_TO", edge_kinds)
        self.assertIn("MINTED", edge_kinds)
        self.assertIn("TRANSFER", edge_kinds)
        addresses = [node.address for node in graph.nodes]
        self.assertEqual(len(addresses), len(set(addresses)))
        self.assertTrue(all(address[:2] == ("cvn", "fintech") for address in addresses))
        minted = next(edge for edge in graph.edges if edge.kind == "MINTED")
        paid = next(edge for edge in graph.edges if edge.kind == "TRANSFER")
        self.assertEqual((minted.amount, paid.amount), (Decimal("60"), Decimal("50")))

    def test_invalid_transition_is_rejected_without_mutation(self):
        contract = self.ledger.create_commission(
            "commission-1", "recommendation", "alice", "bob", "50", "60",
        )
        with self.assertRaisesRegex(ValueError, "invalid contract transition"):
            self.ledger.advance_contract(contract.id, ContractStatus.DELIVERED)
        self.assertEqual(contract.status, ContractStatus.DRAFT)

    def test_freeze_pauses_balance_and_release_restores_it(self):
        mint = self.ledger.mint_direct("e1", "recommendation", "alice", "40", ["sha:a"])
        self.assertEqual(self.ledger.balance("alice"), Decimal("40"))
        frozen = self.ledger.freeze_events([mint.sequence], "争议冻结")
        self.assertEqual(len(frozen), 1)
        self.assertEqual(frozen[0].kind, LedgerEventType.FREEZE)
        self.assertEqual(self.ledger.balance("alice"), Decimal("0"))
        self.assertEqual(self.ledger.total_supply(), Decimal("0"))
        with self.assertRaisesRegex(ValueError, "already been used"):
            self.ledger.mint_direct("duplicate", "recommendation", "bob", "10", ["sha:a"])
        released = self.ledger.release_events([mint.sequence], "争议已解决")
        self.assertEqual(released[0].kind, LedgerEventType.RELEASE)
        self.assertEqual(self.ledger.balance("alice"), Decimal("40"))
        self.assertEqual(self.ledger.total_supply(), Decimal("40"))

    def test_freeze_is_idempotent_and_rejects_unsettled_targets(self):
        mint = self.ledger.mint_direct("e1", "recommendation", "alice", "40", ["sha:a"])
        transfer = self.ledger.transfer("e2", "alice", "bob", "5", "recommendation", ["sha:b"])
        with self.assertRaisesRegex(ValueError, "insufficient token balance to freeze"):
            self.ledger.freeze_events([mint.sequence], "争议")
        self.ledger.freeze_events([transfer.sequence], "争议")
        again = self.ledger.freeze_events([transfer.sequence], "争议")
        self.assertEqual(again, [])
        with self.assertRaisesRegex(ValueError, "unknown event sequence"):
            self.ledger.release_events([999])
        self.assertEqual(self.ledger.balance("bob"), Decimal("0"))
        self.ledger.release_events([transfer.sequence])
        self.ledger.freeze_events([transfer.sequence])


if __name__ == "__main__":
    unittest.main()
