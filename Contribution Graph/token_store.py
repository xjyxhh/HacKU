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
import os
import sqlite3
from contextlib import closing, contextmanager
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
    _amount,
    evidence_key,
)


def _marker_target(event, target_ids):
    """Resolve current sequence markers and older id-based freeze markers."""
    for prefix in ("freeze-seq:", "release-seq:"):
        if event.id.startswith(prefix):
            sequence = event.id[len(prefix):].split(":", 1)[0]
            return int(sequence) if sequence.isdigit() else None
    for prefix in ("freeze:", "release:"):
        if event.id.startswith(prefix):
            tail = event.id[len(prefix):]
            if tail in target_ids:
                return target_ids[tail]
            base, separator, suffix = tail.rpartition(":")
            if separator and suffix.isdigit():
                return target_ids.get(base)
    return None


class TokenStore:
    """Durable TokenLedger: in-memory rules + append-only SQLite storage."""

    def __init__(self, path, project: TokenProject | None = None, project_id=None):
        self.path = Path(path)
        self.project_id = project.id if project is not None else project_id
        if project is not None:
            self._ledger = TokenLedger(project)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            except FileExistsError:
                pass
            with self._write(initializing=True) as conn:
                if conn.execute("SELECT 1 FROM token_projects WHERE id = ?", (project.id,)).fetchone():
                    raise ValueError("token project already exists; refusing to overwrite")
                if (not conn.execute("SELECT 1 FROM token_projects LIMIT 1").fetchone()
                        and any(conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
                                for table in ("token_tasks", "commission_contracts", "ledger_events"))):
                    raise ValueError("incomplete token ledger contains records; repair it manually")
                self._insert_project(conn, project)
        else:
            if not self.path.is_file():
                raise ValueError("no token ledger stored; pass a TokenProject to create one")
            try:
                with closing(sqlite3.connect(f"file:{self.path.resolve()}?mode=ro", uri=True, timeout=1)) as conn:
                    conn.execute("PRAGMA foreign_keys = ON")
                    conn.execute("BEGIN")
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
    def _write(self, initializing=False):
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
                if not initializing:
                    self._load_locked(conn)
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                if hasattr(self, "_ledger") and not initializing:
                    try:
                        self._reload(conn)
                    except Exception:
                        pass  # Preserve the original transaction failure.
                raise

    def _reload(self, conn):
        self._load_locked(conn)

    def _load_locked(self, conn):
        """Rebuild the in-memory ledger from stored definitions and events.

        Writes call this after obtaining BEGIN IMMEDIATE; ordinary opens use
        a read-only connection and observe one committed SQLite snapshot.
        """
        stored = conn.execute(
            "SELECT id, name, treasury_id, member_ids FROM token_projects ORDER BY rowid"
        ).fetchall()
        if not stored:
            raise ValueError("no token project stored; recreate the incomplete ledger")
        if self.project_id is None:
            if len(stored) > 1:
                raise ValueError("token project id is required when a database contains multiple projects")
            selected = stored[0]
        else:
            selected = next((item for item in stored if item[0] == self.project_id), None)
            if selected is None:
                raise ValueError(f"unknown token project {self.project_id}")
        project_id, name, treasury_id, member_ids = selected
        self.project_id = project_id
        members = json.loads(member_ids)
        if not isinstance(members, list) or not all(isinstance(item, str) for item in members):
            raise ValueError("token project member_ids must be a JSON string array")
        self._ledger = TokenLedger(
            TokenProject(project_id, name, treasury_id, tuple(members))
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
            (stored_contract_id, task_id, principal_id, contractor_id, value_type, price,
             maximum, criteria_hash, status, evidence, approvers, verified, _seq) = row
            contract_id = self._unscope_id(stored_contract_id, project_id)
            evidence_values, approver_values = json.loads(evidence), json.loads(approvers)
            if (not isinstance(evidence_values, list) or not isinstance(approver_values, list)
                    or not all(isinstance(value, str) for value in evidence_values + approver_values)):
                raise ValueError("contract evidence and approvers must be JSON string arrays")
            self._ledger._task(task_id)
            self._ledger._member(principal_id)
            self._ledger._member(contractor_id)
            price_value = _amount(price, "stored contract price")
            maximum_value = _amount(maximum, "stored maximum mint value", allow_zero=False)
            verified_value = (_amount(verified, "stored verified mint value", allow_zero=False)
                              if verified is not None else None)
            if price_value > maximum_value:
                raise ValueError("stored contract price exceeds its maximum")
            contract = CommissionContract(
                contract_id, self.project.id, task_id, principal_id, contractor_id,
                ValueType(value_type), price_value, maximum_value, criteria_hash,
                ContractStatus(status),
                evidence_hashes=evidence_values,
                approver_ids=approver_values,
                verified_mint_value=verified_value,
            )
            self._ledger.contracts[contract_id] = contract
            contracts.append(contract)
        for local_sequence, row in enumerate(conn.execute(
            "SELECT sequence, id, kind, amount, source_id, destination_id, task_id, "
            "contract_id, evidence_key, note FROM ledger_events "
            "WHERE project_id = ? ORDER BY sequence",
            (self.project.id,),
        ), start=1):
            _stored_sequence, stored_event_id, kind, amount, source, destination, task_id, stored_contract_id, key, note = row
            event_id = self._unscope_id(stored_event_id, self.project.id)
            contract_id = (self._unscope_id(stored_contract_id, self.project.id)
                           if stored_contract_id is not None else None)
            event_kind = LedgerEventType(kind)
            self._ledger._task(task_id)
            if contract_id is not None and contract_id not in self._ledger.contracts:
                raise ValueError("ledger event refers to an unknown contract")
            if event_kind == LedgerEventType.MINT:
                if source != self.project.treasury_id:
                    raise ValueError("mint source must be the treasury")
                self._ledger._member(destination)
            elif event_kind in {LedgerEventType.TRANSFER, LedgerEventType.SPLIT,
                                LedgerEventType.REFUND}:
                self._ledger._member(source)
                if destination != self.project.treasury_id:
                    self._ledger._member(destination)
                if event_kind == LedgerEventType.REFUND and destination != self.project.treasury_id:
                    raise ValueError("refund destination must be the treasury")
            elif event_kind in (LedgerEventType.FREEZE, LedgerEventType.RELEASE):
                self._ledger._member(source)
            value = _amount(amount, "stored event amount")
            event = LedgerEvent(
                local_sequence, event_id, self.project.id, event_kind, value,
                source, destination, task_id, contract_id, key, note,
            )
            self._ledger.events.append(event)
            self._ledger._event_ids.add(event.id)
        # Replay freeze state in one pass, including older id-based markers.
        target_ids = {event.id: event.sequence for event in self._ledger.events
                      if event.kind in (LedgerEventType.MINT, LedgerEventType.TRANSFER,
                                        LedgerEventType.SPLIT)}
        targets_by_sequence = {event.sequence: event for event in self._ledger.events
                               if event.kind in (LedgerEventType.MINT, LedgerEventType.TRANSFER,
                                                 LedgerEventType.SPLIT)}
        marker_counts = {}
        for event in self._ledger.events:
            if event.kind not in (LedgerEventType.FREEZE, LedgerEventType.RELEASE):
                continue
            sequence = _marker_target(event, target_ids)
            target = targets_by_sequence.get(sequence)
            if (target is None or event.amount != target.amount
                    or event.source_id != target.destination_id
                    or event.task_id != target.task_id):
                raise ValueError("invalid freeze or release marker")
            change = 1 if event.kind == LedgerEventType.FREEZE else -1
            marker_counts[sequence] = marker_counts.get(sequence, 0) + change
        self._ledger._frozen_events = {sequence: {1} for sequence, count in marker_counts.items()
                                       if count > 0}
        self._ledger._minted_evidence = {
            event.evidence_key for event in self._ledger.events
            if event.kind == LedgerEventType.MINT
        }
        self._ledger._minted_by_task = {}
        for event in self._ledger.events:
            if event.kind == LedgerEventType.MINT:
                self._ledger._minted_by_task[event.task_id] = (
                    self._ledger._minted_by_task.get(event.task_id, Decimal("0")) + event.amount
                )
        self._ledger._settled_contracts = {
            contract.id for contract in self._ledger.contracts.values()
            if contract.status == ContractStatus.SETTLED
        }
        balances = self._ledger.balances()
        if (any(value < 0 for value in balances.values())
                or sum(balances.values(), Decimal("0")) != self._ledger.total_supply()
                or any(count not in (0, 1) for count in marker_counts.values())):
            raise ValueError("token ledger violates balance or freeze invariants")

    # ------------------------------------------------------------- persistence

    @staticmethod
    def _insert_project(conn, project: TokenProject):
        conn.execute(
            "INSERT INTO token_projects (id, name, treasury_id, member_ids) VALUES (?, ?, ?, ?)",
            (project.id, project.name, project.treasury_id,
             json.dumps(list(project.member_ids))),
        )

    @staticmethod
    def _scope_id(project_id, value):
        return f"{len(project_id)}:{project_id}:{value}"

    @staticmethod
    def _unscope_id(value, project_id):
        prefix = f"{len(project_id)}:{project_id}:"
        return value[len(prefix):] if value.startswith(prefix) else value

    def _stored_contract_id(self, conn, project_id, contract_id):
        row = conn.execute(
            "SELECT id FROM commission_contracts WHERE project_id = ? AND id IN (?, ?) LIMIT 1",
            (project_id, contract_id, self._scope_id(project_id, contract_id)),
        ).fetchone()
        return row[0] if row else self._scope_id(project_id, contract_id)

    def _insert_task(self, conn, task: TokenTask):
        conn.execute(
            "INSERT INTO token_tasks (id, project_id, name, value_type, mint_cap, acceptance_criteria) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (task.id, task.project_id, task.name, task.value_type.value,
             str(task.mint_cap), task.acceptance_criteria),
        )

    def _insert_contract(self, conn, contract: CommissionContract):
        row_sequence = conn.execute(
            "SELECT COUNT(*) FROM commission_contracts WHERE project_id = ?",
            (contract.project_id,),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO commission_contracts (id, project_id, task_id, principal_id, contractor_id, "
            "value_type, contract_price, maximum_mint_value, acceptance_criteria_hash, status, "
            "evidence_hashes, approver_ids, verified_mint_value, row_sequence) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (self._scope_id(contract.project_id, contract.id), contract.project_id,
             contract.task_id, contract.principal_id,
             contract.contractor_id, contract.value_type.value, str(contract.contract_price),
             str(contract.maximum_mint_value), contract.acceptance_criteria_hash,
             contract.status.value, json.dumps(contract.evidence_hashes),
             json.dumps(contract.approver_ids),
             str(contract.verified_mint_value) if contract.verified_mint_value is not None else None,
             row_sequence),
        )

    def _update_contract(self, conn, contract: CommissionContract):
        stored_id = self._stored_contract_id(conn, contract.project_id, contract.id)
        conn.execute(
            "UPDATE commission_contracts SET status = ?, evidence_hashes = ?, approver_ids = ?, "
            "verified_mint_value = ? WHERE id = ? AND project_id = ?",
            (contract.status.value, json.dumps(contract.evidence_hashes),
             json.dumps(contract.approver_ids),
             str(contract.verified_mint_value) if contract.verified_mint_value is not None else None,
             stored_id, contract.project_id),
        )

    def _insert_events(self, conn, events):
        for event in events:
            conn.execute(
                "INSERT INTO ledger_events (id, project_id, kind, amount, source_id, "
                "destination_id, task_id, contract_id, evidence_key, note) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (self._scope_id(event.project_id, event.id), event.project_id,
                 event.kind.value, str(event.amount),
                 event.source_id, event.destination_id, event.task_id,
                  (self._stored_contract_id(conn, event.project_id, event.contract_id)
                  if event.contract_id is not None else None),
                 event.evidence_key, event.note),
            )

    # ----------------------------------------------------------- public writes

    def add_task(self, task: TokenTask) -> TokenTask:
        with self._write() as conn:
            self._ledger.add_task(task)
            self._insert_task(conn, task)
        return task

    def add_member(self, member_id: str) -> None:
        with self._write() as conn:
            self._ledger.add_member(member_id)
            conn.execute("UPDATE token_projects SET member_ids = ? WHERE id = ?",
                         (json.dumps(self.project.member_ids), self.project.id))

    def set_mint_cap(self, task_id: str, mint_cap) -> TokenTask:
        with self._write() as conn:
            task = self._ledger.set_mint_cap(task_id, mint_cap)
            conn.execute("UPDATE token_tasks SET mint_cap = ? WHERE project_id = ? AND id = ?",
                         (str(task.mint_cap), self.project.id, task_id))
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

    def deliver_commission(self, contract_id: str, evidence_hashes) -> CommissionContract:
        with self._write() as conn:
            contract = self._ledger.deliver_commission(contract_id, evidence_hashes)
            self._update_contract(conn, contract)
        return contract

    def mint_direct(self, event_id, task_id, recipient_id, amount, evidence_hashes) -> LedgerEvent:
        with self._write() as conn:
            before = len(self._ledger.events)
            event = self._ledger.mint_direct(event_id, task_id, recipient_id, amount, evidence_hashes)
            self._insert_events(conn, self._ledger.events[before:])
        return event

    def refund(self, event_id, source_id, amount, task_id, evidence_hashes,
               note="dispute refund") -> LedgerEvent:
        with self._write() as conn:
            self._ledger._member(source_id)
            self._ledger._task(task_id)
            value = _amount(amount, "refund amount", allow_zero=False)
            if self._ledger.balance(source_id) < value:
                raise ValueError("insufficient token balance")
            key = evidence_key(evidence_hashes)
            before = len(self._ledger.events)
            event = self._ledger._event(
                event_id, LedgerEventType.REFUND, value, source_id,
                self.project.treasury_id, task_id, None, key, note,
            )
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

    def settle_legacy_commission(self, contract_id, task_id, principal_id, contractor_id,
                                 amount, evidence_hashes, approver_ids):
        """Create and settle a projected legacy commission in one transaction."""
        with self._write() as conn:
            before = len(self._ledger.events)
            contract = self._ledger.create_commission(
                contract_id, task_id, principal_id, contractor_id, amount, amount,
            )
            for status in (ContractStatus.OFFERED, ContractStatus.ACCEPTED,
                           ContractStatus.CREDIT_RESERVED):
                self._ledger.advance_contract(contract_id, status)
            self._ledger.deliver_commission(contract_id, evidence_hashes)
            self._ledger.advance_contract(contract_id, ContractStatus.VERIFIED)
            mint, transfer = self._ledger.settle_commission(
                contract_id, amount, evidence_hashes, approver_ids,
            )
            self._insert_contract(conn, contract)
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

    def reconcile_refund(self, contribution_id, debtor_id, task_id, amount, evidence_hashes):
        """Return available tokens and record any shortfall for later collection."""
        with self._write() as conn:
            self._ledger._member(debtor_id)
            self._ledger._task(task_id)
            requested = _amount(amount, "refund amount", allow_zero=False)
            available = max(Decimal("0"), self._ledger.balance(debtor_id))
            paid = min(requested, available)
            event = None
            if paid:
                before = len(self._ledger.events)
                event = self._ledger._event(
                    f"{contribution_id}:refund", LedgerEventType.REFUND, paid,
                    debtor_id, self.project.treasury_id, task_id, None,
                    evidence_key(evidence_hashes), "dispute refund",
                )
                self._insert_events(conn, self._ledger.events[before:])
            remaining = requested - paid
            if remaining:
                conn.execute(
                    "INSERT INTO reconciliation_debts (id, project_id, debtor_id, task_id, amount, remaining, reason) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (self._scope_id(self.project.id, contribution_id), self.project.id,
                     debtor_id, task_id,
                     str(requested), str(remaining), "resolved contribution score reduction"),
                )
        return event, remaining

    def debts_payload(self):
        with closing(sqlite3.connect(f"file:{self.path.resolve()}?mode=ro", uri=True)) as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='reconciliation_debts'").fetchone():
                return []
            return [
                {"id": self._unscope_id(debt_id, self.project.id),
                 "debtorId": debtor_id, "taskId": task_id,
                 "amountExact": amount, "remainingExact": remaining, "reason": reason}
                for debt_id, debtor_id, task_id, amount, remaining, reason in conn.execute(
                    "SELECT id, debtor_id, task_id, amount, remaining, reason FROM reconciliation_debts "
                    "WHERE project_id = ? ORDER BY rowid", (self.project.id,),
                )
            ]

    def collect_debt(self, contribution_id):
        with self._write() as conn:
            row = conn.execute(
                "SELECT id, debtor_id, task_id, remaining FROM reconciliation_debts "
                "WHERE id IN (?, ?) AND project_id = ?",
                (contribution_id, self._scope_id(self.project.id, contribution_id), self.project.id),
            ).fetchone()
            if row is None:
                raise ValueError("unknown reconciliation debt")
            stored_id, debtor_id, task_id, remaining_text = row
            remaining = Decimal(remaining_text)
            paid = min(remaining, max(Decimal("0"), self._ledger.balance(debtor_id)))
            event = None
            if paid:
                before = len(self._ledger.events)
                count = sum(event.id.startswith(f"{contribution_id}:debt-payment:")
                            for event in self._ledger.events)
                key = [f"legacy:{contribution_id}:debt-payment:{count + 1}"]
                value = _amount(paid, "debt payment", allow_zero=False)
                event = self._ledger._event(
                    f"{contribution_id}:debt-payment:{count + 1}",
                    LedgerEventType.REFUND, value, debtor_id, self.project.treasury_id,
                    task_id, None, evidence_key(key), "reconciliation debt payment",
                )
                self._insert_events(conn, self._ledger.events[before:])
                conn.execute(
                    "UPDATE reconciliation_debts SET remaining = ? WHERE id = ? AND project_id = ?",
                    (str(remaining - paid), stored_id, self.project.id),
                )
        return {"paidExact": str(paid), "remainingExact": str(remaining - paid),
                "eventId": event.id if event else None}

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
                "contractPriceExact": str(contract.contract_price),
                "maximumMintValue": float(contract.maximum_mint_value),
                "maximumMintValueExact": str(contract.maximum_mint_value),
                "status": contract.status.value,
                "evidenceHashes": list(contract.evidence_hashes),
                "approverIds": list(contract.approver_ids),
                "verifiedMintValue": (float(contract.verified_mint_value)
                                      if contract.verified_mint_value is not None else None),
                "verifiedMintValueExact": (str(contract.verified_mint_value)
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
                       "amount": float(edge.amount) if edge.amount is not None else None,
                       "amountExact": str(edge.amount) if edge.amount is not None else None}
                      for edge in graph.edges],
        }

    def ledger_payload(self) -> dict:
        """JSON-ready snapshot of events, balances, and totals for the API layer."""
        target_ids = {event.id: event.sequence for event in self._ledger.events
                      if event.kind in (LedgerEventType.MINT, LedgerEventType.TRANSFER)}
        freeze_tags = {}
        for marker in self._ledger.events:
            if marker.kind == LedgerEventType.FREEZE:
                sequence = _marker_target(marker, target_ids)
                if sequence is not None:
                    freeze_tags[sequence] = marker.destination_id
        events = [
            {
                "sequence": event.sequence,
                "id": event.id,
                "kind": event.kind.value,
                "amount": float(event.amount),
                "amountExact": str(event.amount),
                "sourceId": event.source_id,
                "destinationId": event.destination_id,
                "taskId": event.task_id,
                "contractId": event.contract_id,
                "evidenceKey": event.evidence_key,
                "note": event.note,
                "frozen": event.sequence in self._ledger._frozen_events
                if event.kind in (LedgerEventType.MINT, LedgerEventType.TRANSFER) else False,
                "freezeTag": freeze_tags.get(event.sequence),
            }
            for event in self._ledger.events
        ]
        return {
            "projectId": self.project.id,
            "treasuryId": self.project.treasury_id,
            "memberIds": list(self.project.member_ids),
            "totalSupply": float(self._ledger.total_supply()),
            "totalSupplyExact": str(self._ledger.total_supply()),
            "grossMintedExact": str(sum((event.amount for event in self._ledger.events
                                          if event.kind == LedgerEventType.MINT), Decimal("0"))),
            "balances": {member: float(balance) for member, balance in self._ledger.balances().items()},
            "balancesExact": {member: str(balance) for member, balance in self._ledger.balances().items()},
            "events": events,
        }
