"""SQLite persistence adapter for the token engine (fusion PR1).

TokenStore wraps the in-memory TokenLedger with durable storage. Every
mutating call validates against the live in-memory ledger first, then appends
the resulting rows to SQLite inside one transaction. On open, the ledger is
rebuilt by replaying stored definitions and events, so a TokenLedger is
always a deterministic projection of the append-only ledger_events table.

This module is purely additive: it creates its own tables via token_schema.sql
and never touches the eight legacy tables from schema.sql.
"""

import json
import sqlite3
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

from token_engine import (
    CommissionContract,
    ContractStatus,
    LedgerEvent,
    LedgerEventType,
    TokenLedger,
    TokenProject,
    TokenTask,
    ValueType,
)


class TokenStore:
    """Durable TokenLedger: in-memory rules + append-only SQLite storage."""

    def __init__(self, path, project: TokenProject | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if project is not None:
            if self.path.is_file():
                raise ValueError(
                    f"token ledger already exists in {self.path}; refusing to overwrite"
                )
            self._ledger = TokenLedger(project)
            self._initializing = True
            try:
                with self._write() as conn:
                    self._insert_project(conn, project)
            finally:
                del self._initializing
        else:
            if not self.path.is_file():
                raise ValueError(
                    f"no token ledger stored in {self.path}; pass a TokenProject to create one"
                )
            try:
                with self._write() as conn:
                    self._load_locked(conn)
            except sqlite3.Error as error:
                raise ValueError(f"token ledger storage error: {error}") from error

    @property
    def ledger(self) -> TokenLedger:
        return self._ledger

    @property
    def project(self) -> TokenProject:
        return self._ledger.project

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _write(self):
        """One BEGIN IMMEDIATE transaction per public mutation.

        Replay happens under the write lock, so concurrent mutations always
        validate against the latest committed state (matching the legacy
        store's _write/_load pattern). A failed mutation rolls the file back
        and rebuilds memory from stored state; both always end consistent.
        """
        with self._connect() as conn:
            conn.executescript(
                Path(__file__).with_name("token_schema.sql").read_text(encoding="utf-8")
            )
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._load_locked(conn)
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                self._reload(conn)
                raise

    def _reload(self, conn):
        project = self._ledger.project
        self._ledger = TokenLedger(project)
        self._load_locked(conn)

    def _load_locked(self, conn):
        """Rebuild the in-memory ledger from stored definitions and events.

        Must be called while holding the write lock (_write), never on a
        read-only path.
        """
        stored = conn.execute(
            "SELECT id, name, treasury_id, member_ids FROM token_projects"
        ).fetchall()
        if not stored:
            # First write to a fresh ledger file: nothing to replay. Callers
            # about to insert the initial project keep their in-memory ledger.
            if getattr(self, "_initializing", False):
                return
            raise ValueError(
                f"no token project stored in {self.path}; pass a TokenProject to create one"
            )
        if len(stored) > 1:
            raise ValueError("TokenStore supports exactly one token project per database file")
        project_id, name, treasury_id, member_ids = stored[0]
        self._ledger = TokenLedger(
            TokenProject(project_id, name, treasury_id, tuple(json.loads(member_ids)))
        )
        for task_id, name, value_type, mint_cap, criteria in conn.execute(
            "SELECT id, name, value_type, mint_cap, acceptance_criteria FROM token_tasks "
            "WHERE project_id = ? ORDER BY rowid",
            (self.project.id,),
        ):
            self._ledger.add_task(TokenTask(
                task_id, self.project.id, name, ValueType(value_type),
                Decimal(mint_cap), criteria,
            ))
        contracts = []
        for row in conn.execute(
            "SELECT id, task_id, principal_id, contractor_id, value_type, contract_price, "
            "maximum_mint_value, acceptance_criteria_hash, status, evidence_hashes, "
            "approver_ids, verified_mint_value, row_sequence FROM commission_contracts "
            "WHERE project_id = ? ORDER BY row_sequence",
            (self.project.id,),
        ):
            (contract_id, task_id, principal_id, contractor_id, value_type, price,
             maximum, criteria_hash, status, evidence, approvers, verified, _seq) = row
            contract = CommissionContract(
                contract_id, self.project.id, task_id, principal_id, contractor_id,
                ValueType(value_type), Decimal(price), Decimal(maximum), criteria_hash,
                ContractStatus(status),
                evidence_hashes=json.loads(evidence),
                approver_ids=json.loads(approvers),
                verified_mint_value=Decimal(verified) if verified is not None else None,
            )
            self._ledger.contracts[contract_id] = contract
            contracts.append(contract)
        for row in conn.execute(
            "SELECT sequence, id, kind, amount, source_id, destination_id, task_id, "
            "contract_id, evidence_key, note FROM ledger_events "
            "WHERE project_id = ? ORDER BY sequence",
            (self.project.id,),
        ):
            sequence, event_id, kind, amount, source, destination, task_id, contract_id, key, note = row
            event = LedgerEvent(
                sequence, event_id, self.project.id, LedgerEventType(kind), Decimal(amount),
                source, destination, task_id, contract_id, key, note,
            )
            self._ledger.events.append(event)
            self._ledger._event_ids.add(event.id)
        # Freeze tracking: an event is frozen iff its freeze:<id> record exists
        # in the append-only log (self-contained and replay-safe).
        self._ledger._frozen_events = {
            target.sequence: {1}
            for target in self._ledger.events
            if target.kind == LedgerEventType.MINT
            and f"freeze:{target.id}" in self._ledger._event_ids
        }
        self._ledger._minted_evidence = {
            event.evidence_key for event in self._ledger.events
            if event.kind == LedgerEventType.MINT
            and event.sequence not in self._ledger._frozen_events
        }
        self._ledger._settled_contracts = {
            contract.id for contract in self._ledger.contracts.values()
            if contract.status == ContractStatus.SETTLED
        }

    # ------------------------------------------------------------- persistence

    @staticmethod
    def _insert_project(conn, project: TokenProject):
        conn.execute(
            "INSERT INTO token_projects (id, name, treasury_id, member_ids) VALUES (?, ?, ?, ?)",
            (project.id, project.name, project.treasury_id,
             json.dumps(list(project.member_ids))),
        )

    def _insert_task(self, conn, task: TokenTask):
        conn.execute(
            "INSERT INTO token_tasks (id, project_id, name, value_type, mint_cap, acceptance_criteria) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (task.id, task.project_id, task.name, task.value_type.value,
             str(task.mint_cap), task.acceptance_criteria),
        )

    def _insert_contract(self, conn, contract: CommissionContract):
        row_sequence = conn.execute("SELECT COUNT(*) FROM commission_contracts").fetchone()[0]
        conn.execute(
            "INSERT INTO commission_contracts (id, project_id, task_id, principal_id, contractor_id, "
            "value_type, contract_price, maximum_mint_value, acceptance_criteria_hash, status, "
            "evidence_hashes, approver_ids, verified_mint_value, row_sequence) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (contract.id, contract.project_id, contract.task_id, contract.principal_id,
             contract.contractor_id, contract.value_type.value, str(contract.contract_price),
             str(contract.maximum_mint_value), contract.acceptance_criteria_hash,
             contract.status.value, json.dumps(contract.evidence_hashes),
             json.dumps(contract.approver_ids),
             str(contract.verified_mint_value) if contract.verified_mint_value is not None else None,
             row_sequence),
        )

    def _update_contract(self, conn, contract: CommissionContract):
        conn.execute(
            "UPDATE commission_contracts SET status = ?, evidence_hashes = ?, approver_ids = ?, "
            "verified_mint_value = ? WHERE id = ?",
            (contract.status.value, json.dumps(contract.evidence_hashes),
             json.dumps(contract.approver_ids),
             str(contract.verified_mint_value) if contract.verified_mint_value is not None else None,
             contract.id),
        )

    def _insert_events(self, conn, events):
        for event in events:
            conn.execute(
                "INSERT INTO ledger_events (sequence, id, project_id, kind, amount, source_id, "
                "destination_id, task_id, contract_id, evidence_key, note) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (event.sequence, event.id, event.project_id, event.kind.value, str(event.amount),
                 event.source_id, event.destination_id, event.task_id, event.contract_id,
                 event.evidence_key, event.note),
            )

    # ----------------------------------------------------------- public writes

    def add_task(self, task: TokenTask) -> TokenTask:
        with self._write() as conn:
            self._ledger.add_task(task)
            self._insert_task(conn, task)
        return task

    def create_commission(self, contract_id, task_id, principal_id, contractor_id,
                          contract_price, maximum_mint_value) -> CommissionContract:
        with self._write() as conn:
            contract = self._ledger.create_commission(
                contract_id, task_id, principal_id, contractor_id,
                contract_price, maximum_mint_value,
            )
            self._insert_contract(conn, contract)
        return contract

    def advance_contract(self, contract_id: str, status: ContractStatus) -> CommissionContract:
        with self._write() as conn:
            before = len(self._ledger.events)
            contract = self._ledger.advance_contract(contract_id, status)
            self._update_contract(conn, contract)
            self._insert_events(conn, self._ledger.events[before:])
        return contract

    def mint_direct(self, event_id, task_id, recipient_id, amount, evidence_hashes) -> LedgerEvent:
        with self._write() as conn:
            before = len(self._ledger.events)
            event = self._ledger.mint_direct(event_id, task_id, recipient_id, amount, evidence_hashes)
            self._insert_events(conn, self._ledger.events[before:])
        return event

    def settle_commission(self, contract_id, verified_mint_value, evidence_hashes,
                          approver_ids) -> tuple[LedgerEvent, LedgerEvent]:
        with self._write() as conn:
            before = len(self._ledger.events)
            mint, transfer = self._ledger.settle_commission(
                contract_id, verified_mint_value, evidence_hashes, approver_ids,
            )
            self._update_contract(conn, self._ledger.contracts[contract_id])
            self._insert_events(conn, self._ledger.events[before:])
        return mint, transfer

    def transfer(self, event_id, source_id, destination_id, amount, task_id,
                 evidence_hashes) -> LedgerEvent:
        with self._write() as conn:
            before = len(self._ledger.events)
            event = self._ledger.transfer(
                event_id, source_id, destination_id, amount, task_id, evidence_hashes,
            )
            self._insert_events(conn, self._ledger.events[before:])
        return event

    def freeze_events(self, sequences, reason: str = "", tag: str | None = None) -> list[LedgerEvent]:
        with self._write() as conn:
            before = len(self._ledger.events)
            events = self._ledger.freeze_events(sequences, reason, tag)
            self._insert_events(conn, self._ledger.events[before:])
        return events

    def release_events(self, sequences, note: str = "", tag: str | None = None) -> list[LedgerEvent]:
        with self._write() as conn:
            before = len(self._ledger.events)
            events = self._ledger.release_events(sequences, note, tag)
            self._insert_events(conn, self._ledger.events[before:])
        return events

    # ---------------------------------------------------------- read delegates

    def balance(self, member_id) -> Decimal:
        return self._ledger.balance(member_id)

    def balances(self) -> dict[str, Decimal]:
        return self._ledger.balances()

    def total_supply(self) -> Decimal:
        return self._ledger.total_supply()

    def minted_for_task(self, task_id) -> Decimal:
        return self._ledger.minted_for_task(task_id)

    def task_budget(self, task_id) -> dict[str, Decimal]:
        return self._ledger.task_budget(task_id)

    def graph(self):
        return self._ledger.graph()

    def contracts_payload(self) -> list[dict]:
        """JSON-ready list of commission contracts for the API layer."""
        return [
            {
                "id": contract.id,
                "taskId": contract.task_id,
                "principalId": contract.principal_id,
                "contractorId": contract.contractor_id,
                "valueType": contract.value_type.value,
                "contractPrice": float(contract.contract_price),
                "maximumMintValue": float(contract.maximum_mint_value),
                "status": contract.status.value,
                "evidenceHashes": list(contract.evidence_hashes),
                "approverIds": list(contract.approver_ids),
                "verifiedMintValue": (float(contract.verified_mint_value)
                                      if contract.verified_mint_value is not None else None),
            }
            for contract in self._ledger.contracts.values()
        ]

    def graph_payload(self) -> dict:
        """JSON-ready SourceCred-style graph projection for the API layer."""
        graph = self._ledger.graph()
        return {
            "nodes": [{"address": list(node.address), "kind": node.kind, "label": node.label}
                      for node in graph.nodes],
            "edges": [{"address": list(edge.address), "kind": edge.kind,
                       "source": list(edge.source), "destination": list(edge.destination),
                       "amount": float(edge.amount) if edge.amount is not None else None}
                      for edge in graph.edges],
        }

    def ledger_payload(self) -> dict:
        """JSON-ready snapshot of events, balances, and totals for the API layer."""
        events = [
            {
                "sequence": event.sequence,
                "id": event.id,
                "kind": event.kind.value,
                "amount": float(event.amount),
                "sourceId": event.source_id,
                "destinationId": event.destination_id,
                "taskId": event.task_id,
                "contractId": event.contract_id,
                "evidenceKey": event.evidence_key,
                "note": event.note,
            }
            for event in self._ledger.events
        ]
        return {
            "projectId": self.project.id,
            "treasuryId": self.project.treasury_id,
            "memberIds": list(self.project.member_ids),
            "totalSupply": float(self._ledger.total_supply()),
            "balances": {member: float(balance) for member, balance in self._ledger.balances().items()},
            "events": events,
        }

