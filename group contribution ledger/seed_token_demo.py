"""Build a fresh, repeatable multi-case token ledger for judging/demo use."""
import argparse
import json
from pathlib import Path

from token_engine import ContractStatus, TokenProject, TokenTask, ValueType
from token_store import TokenStore


def commission(store, contract_id, outcome=None, refund=None):
    store.create_commission(contract_id, "task", "alice", "bob", 50, 60)
    for state in (ContractStatus.OFFERED, ContractStatus.ACCEPTED, ContractStatus.CREDIT_RESERVED,
                  ContractStatus.DELIVERED, ContractStatus.VERIFIED):
        store.advance_contract(contract_id, state)
    store.settle_commission(contract_id, 60, [f"evidence:{contract_id}"], ["carol"])
    if outcome:
        store.dispute_contract(contract_id, "alice", f"Disputed delivery for {contract_id}")
        store.freeze_contract_payment(contract_id, f"Freeze for {contract_id}")
        store.resolve_contract(contract_id, outcome, f"Demonstration outcome: {outcome}", "carol", refund)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    db_path = output / "token.sqlite3"
    if db_path.exists():
        parser.error(f"refusing to overwrite existing database: {db_path}")

    store = TokenStore(db_path, TokenProject("demo", "Fairness demo", "treasury", ("alice", "bob", "carol")))
    store.add_task(TokenTask("task", "demo", "Shared task", ValueType.CORE, 300, "Deliver reviewed work"))
    store.mint_direct("direct:alice", "task", "alice", 10, ["evidence:direct"])
    print_case("Direct contribution", store, "Alice receives 10 for independently reviewed work.",
               "Alice benefits; reviewers spend time checking evidence.")

    commission(store, "commission:60-50")
    print_case("60 minted / 50 paid", store, "The principal keeps 10; the contractor receives 50.",
               "Both sides benefit; the principal bears the 50 payment and approval delay.")

    commission(store, "commission:refund", "REFUND")
    print_case("Full refund", store, "The frozen 50 returns to Alice; Bob retains none of that payment.",
               "Alice is protected; Bob bears the lost payment after spending effort.")

    commission(store, "commission:split", "SPLIT", 20)
    print_case("Partial split", store, "Alice receives 20 and Bob retains 30 from the frozen payment.",
               "Both keep part of the value; they bear negotiation and review costs.")

    two_party = TokenStore(output / "two-member.sqlite3",
                           TokenProject("two", "Two member boundary", "treasury", ("alice", "bob")))
    two_party.add_task(TokenTask("task", "two", "Shared task", ValueType.CORE, 100, "Deliver"))
    two_party.create_commission("two-party", "task", "alice", "bob", 50, 60)
    for state in (ContractStatus.OFFERED, ContractStatus.ACCEPTED, ContractStatus.CREDIT_RESERVED,
                  ContractStatus.DELIVERED, ContractStatus.VERIFIED):
        two_party.advance_contract("two-party", state)
    try:
        two_party.settle_commission("two-party", 60, ["evidence:two-party"], [])
    except ValueError as error:
        print_case("Two member approval boundary", two_party, "Independent approval is blocked.",
                   f"No party can approve their own exchange; limitation: {error}.")

    print(json.dumps({"database": str(db_path), "cases": 5}, ensure_ascii=False, indent=2))


def print_case(title, store, state, fairness):
    ledger = store.ledger_payload()
    print(f"\n## {title}\n{state}\n{fairness}")
    print("Status/events:", [(item["id"], item["kind"]) for item in ledger["events"]])
    print("Balances:", ledger["balances"], "supply:", ledger["totalSupply"])


if __name__ == "__main__":
    main()
