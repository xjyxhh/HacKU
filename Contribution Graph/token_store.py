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

    def __init__(self, path, project: TokenProject | None = None):
        self.path = Path(path)
        if project is not None:
            self._ledger = TokenLedger(project)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            except FileExistsError:
                pass
            with self._write(initializing=True) as conn:
                if conn.execute("SELECT 1 FROM token_projects LIMIT 1").fetchone():
                    raise ValueError("token ledger already exists; refusing to overwrite")
                if any(conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
                       for table in ("token_tasks", "commission_contracts", "ledger_events")):
                    raise ValueError("incomplete token ledger contains records; repair it manually")
                self._insert_project(conn, project)
        else:
            if not self.path.is_file():
                raise ValueError("no token ledger stored; pass a TokenProject to create one")
            try:
                self._ensure_schema()
                with closing(sqlite3.connect(f"file:{self.path.resolve()}?mode=ro", uri=True, timeout=1)) as conn:
                    conn.execute("PRAGMA foreign_keys = ON")
                    conn.execute("BEGIN")
                    self._load_locked(conn)
            except sqlite3.Error as error:
                raise ValueError(f"token ledger storage error: {error}") from error

    def _ensure_schema(self):
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            schema = Path(__file__).with_name("token_schema.sql").read_text(encoding="utf-8")
            conn.executescript(schema)
            self._migrate_contract_status(conn)
            conn.executescript(schema)
            conn.execute("PRAGMA foreign_keys = ON")

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
            self._ensure_schema()
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

    @staticmethod
    def _migrate_contract_status(conn):
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='commission_contracts'").fetchone()
        if not row or "'RESOLVED'" in row[0]:
            return
        conn.execute("""CREATE TABLE commission_contracts_rebuild (
            id TEXT PRIMARY KEY CHECK (length(trim(id)) > 0),
            project_id TEXT NOT NULL REFERENCES token_projects(id),
            task_id TEXT NOT NULL, principal_id TEXT NOT NULL, contractor_id TEXT NOT NULL,
            value_type TEXT NOT NULL CHECK (value_type IN ('CORE','REVIEW','COORDINATION')),
            contract_price TEXT NOT NULL CHECK (json_valid(contract_price) AND json_type(contract_price) IN ('integer','real') AND CAST(contract_price AS REAL) BETWEEN 0 AND 1000000000000),
            maximum_mint_value TEXT NOT NULL CHECK (json_valid(maximum_mint_value) AND json_type(maximum_mint_value) IN ('integer','real') AND CAST(maximum_mint_value AS REAL) > 0 AND CAST(maximum_mint_value AS REAL) <= 1000000000000),
            acceptance_criteria_hash TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('DRAFT','OFFERED','ACCEPTED','CREDIT_RESERVED','DELIVERED','VERIFIED','DISPUTED','FROZEN','SETTLED','RESOLVED')),
            evidence_hashes TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(evidence_hashes) AND json_type(evidence_hashes) = 'array'),
            approver_ids TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(approver_ids) AND json_type(approver_ids) = 'array'),
            verified_mint_value TEXT CHECK (verified_mint_value IS NULL OR (json_valid(verified_mint_value) AND json_type(verified_mint_value) IN ('integer','real') AND CAST(verified_mint_value AS REAL)>0 AND CAST(verified_mint_value AS REAL)<=1000000000000)),
            row_sequence INTEGER NOT NULL,
            FOREIGN KEY (project_id, task_id) REFERENCES token_tasks(project_id, id)
        )""")
        conn.execute("INSERT INTO commission_contracts_rebuild SELECT * FROM commission_contracts")
        conn.execute("DROP TABLE commission_contracts")
        conn.execute("ALTER TABLE commission_contracts_rebuild RENAME TO commission_contracts")
        conn.execute("PRAGMA user_version = 2")

    def _reload(self, conn):
        self._load_locked(conn)

    def _load_locked(self, conn):
        """Rebuild the in-memory ledger from stored definitions and events.

        Writes call this after obtaining BEGIN IMMEDIATE; ordinary opens use
        a read-only connection and observe one committed SQLite snapshot.
        """
        stored = conn.execute(
            "SELECT id, name, treasury_id, member_ids FROM token_projects"
        ).fetchall()
        if not stored:
            raise ValueError("no token project stored; recreate the incomplete ledger")
        if len(stored) > 1:
            raise ValueError("TokenStore supports exactly one token project per database file")
        project_id, name, treasury_id, member_ids = stored[0]
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
            (contract_id, task_id, principal_id, contractor_id, value_type, price,
             maximum, criteria_hash, status, evidence, approvers, verified, _seq) = row
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
        for row in conn.execute(
            "SELECT sequence, id, kind, amount, source_id, destination_id, task_id, "
            "contract_id, evidence_key, note FROM ledger_events "
            "WHERE project_id = ? ORDER BY sequence",
            (self.project.id,),
        ):
            sequence, event_id, kind, amount, source, destination, task_id, contract_id, key, note = row
            event_kind = LedgerEventType(kind)
            self._ledger._task(task_id)
            if contract_id is not None and contract_id not in self._ledger.contracts:
                raise ValueError("ledger event refers to an unknown contract")
            if event_kind == LedgerEventType.MINT:
                if source != self.project.treasury_id:
                    raise ValueError("mint source must be the treasury")
                self._ledger._member(destination)
            elif event_kind == LedgerEventType.TRANSFER:
                self._ledger._member(source)
                if destination != self.project.treasury_id:
                    self._ledger._member(destination)
            elif event_kind in (LedgerEventType.FREEZE, LedgerEventType.RELEASE):
                self._ledger._member(source)
            elif event_kind in (LedgerEventType.REFUND, LedgerEventType.SPLIT):
                if source not in {self.project.treasury_id} and not str(source).startswith("escrow:"):
                    self._ledger._member(source)
                self._ledger._member(destination)
            value = _amount(amount, "stored event amount")
            event = LedgerEvent(
                sequence, event_id, self.project.id, event_kind, value,
                source, destination, task_id, contract_id, key, note,
            )
            self._ledger.events.append(event)
            self._ledger._event_ids.add(event.id)
        # Replay freeze state in one pass, including older id-based markers.
        target_ids = {event.id: event.sequence for event in self._ledger.events
                      if event.kind in (LedgerEventType.MINT, LedgerEventType.TRANSFER)}
        targets_by_sequence = {event.sequence: event for event in self._ledger.events
                               if event.kind in (LedgerEventType.MINT, LedgerEventType.TRANSFER)}
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
        settled_ids = {event.contract_id for event in self._ledger.events
                       if event.contract_id and event.id.endswith(":payment")}
        self._ledger._settled_contracts = settled_ids
        for row in conn.execute("SELECT contract_id,raised_by,reason FROM contract_disputes ORDER BY id"):
            self._ledger.contract_disputes[row[0]] = {"contractId": row[0], "raisedBy": row[1], "reason": row[2]}
        for row in conn.execute("SELECT contract_id,payment_sequence,freeze_sequence,handled_by,outcome,refund_amount,retained_amount,note FROM contract_resolutions"):
            self._ledger.contract_resolutions[row[0]] = {
                "contractId": row[0], "paymentSequence": row[1], "freezeSequence": row[2],
                "handledBy": row[3], "outcome": row[4], "refundAmount": Decimal(row[5]),
                "retainedAmount": Decimal(row[6]), "note": row[7],
            }
            if row[1] is not None and row[4] in {"REFUND", "SPLIT"}:
                marker_counts[row[1]] = 0
        self._ledger._frozen_events = {sequence: {1} for sequence, count in marker_counts.items()
                                       if count > 0}
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

    def submit_delivery(self, contract_id: str, member_id: str, evidence: list[str]) -> CommissionContract:
        cleaned = [value.strip() for value in evidence if isinstance(value, str) and value.strip()]
        if not cleaned or len(cleaned) > 10 or any(len(value) > 4096 for value in cleaned):
            raise ValueError("delivery requires 1 to 10 evidence references of at most 4096 characters")
        with self._write() as conn:
            contract = self._ledger.contracts.get(contract_id)
            if contract is None:
                raise ValueError(f"unknown contract {contract_id}")
            if contract.contractor_id != member_id:
                raise ValueError("only the assigned contractor can submit delivery evidence")
            if contract.status != ContractStatus.CREDIT_RESERVED:
                raise ValueError("delivery evidence can only be submitted after credit is reserved")
            if conn.execute("SELECT 1 FROM contract_delivery_evidence WHERE contract_id=?", (contract_id,)).fetchone():
                raise ValueError("delivery evidence has already been submitted")
            before = len(self._ledger.events)
            self._ledger.advance_contract(contract_id, ContractStatus.DELIVERED)
            contract = self._ledger.contracts[contract_id]
            self._update_contract(conn, contract)
            conn.executemany("INSERT INTO contract_delivery_evidence(contract_id,member_id,evidence) VALUES(?,?,?)",
                             [(contract_id, member_id, value) for value in cleaned])
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

    def settle_legacy_commission(self, contract_id, task_id, principal_id, contractor_id,
                                 amount, evidence_hashes, approver_ids):
        """Create and settle a projected legacy commission in one transaction."""
        with self._write() as conn:
            before = len(self._ledger.events)
            contract = self._ledger.create_commission(
                contract_id, task_id, principal_id, contractor_id, amount, amount,
            )
            for status in (ContractStatus.OFFERED, ContractStatus.ACCEPTED,
                           ContractStatus.CREDIT_RESERVED, ContractStatus.DELIVERED,
                           ContractStatus.VERIFIED):
                self._ledger.advance_contract(contract_id, status)
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

    def reconcile_refund(self, contribution_id, debtor_id, task_id, amount, evidence_hashes,
                         reason="resolved contribution score reduction"):
        """Return available tokens and record any shortfall for later collection."""
        with self._write() as conn:
            self._ledger._member(debtor_id)
            self._ledger._task(task_id)
            requested = _amount(amount, "refund amount", allow_zero=False)
            existing_debt = conn.execute(
                "SELECT remaining FROM reconciliation_debts WHERE id = ? AND project_id = ?",
                (contribution_id, self.project.id),
            ).fetchone()
            existing_event = next((item for item in self._ledger.events
                                   if item.id == f"{contribution_id}:refund"), None)
            if existing_debt or existing_event:
                return existing_event, Decimal(existing_debt[0]) if existing_debt else Decimal("0")
            available = max(Decimal("0"), self._ledger.balance(debtor_id))
            paid = min(requested, available)
            event = None
            if paid:
                before = len(self._ledger.events)
                event = self._ledger.transfer(
                    f"{contribution_id}:refund", debtor_id, self.project.treasury_id,
                    paid, task_id, evidence_hashes,
                )
                self._insert_events(conn, self._ledger.events[before:])
            remaining = requested - paid
            if remaining:
                conn.execute(
                    "INSERT INTO reconciliation_debts (id, project_id, debtor_id, task_id, amount, remaining, reason) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (contribution_id, self.project.id, debtor_id, task_id,
                     str(requested), str(remaining), reason),
                )
        return event, remaining

    def debts_payload(self):
        with closing(sqlite3.connect(f"file:{self.path.resolve()}?mode=ro", uri=True)) as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='reconciliation_debts'").fetchone():
                return []
            return [
                {"id": debt_id, "debtorId": debtor_id, "taskId": task_id,
                 "amountExact": amount, "remainingExact": remaining, "reason": reason}
                for debt_id, debtor_id, task_id, amount, remaining, reason in conn.execute(
                    "SELECT id, debtor_id, task_id, amount, remaining, reason FROM reconciliation_debts "
                    "WHERE project_id = ? ORDER BY rowid", (self.project.id,),
                )
            ]

    def collect_debt(self, contribution_id):
        with self._write() as conn:
            row = conn.execute(
                "SELECT debtor_id, task_id, remaining FROM reconciliation_debts WHERE id = ? AND project_id = ?",
                (contribution_id, self.project.id),
            ).fetchone()
            if row is None:
                raise ValueError("unknown reconciliation debt")
            debtor_id, task_id, remaining_text = row
            remaining = Decimal(remaining_text)
            paid = min(remaining, max(Decimal("0"), self._ledger.balance(debtor_id)))
            event = None
            if paid:
                before = len(self._ledger.events)
                count = sum(event.id.startswith(f"{contribution_id}:debt-payment:")
                            for event in self._ledger.events)
                event = self._ledger.transfer(
                    f"{contribution_id}:debt-payment:{count + 1}", debtor_id,
                    self.project.treasury_id, paid, task_id,
                    [f"legacy:{contribution_id}:debt-payment:{count + 1}"],
                )
                self._insert_events(conn, self._ledger.events[before:])
                conn.execute("UPDATE reconciliation_debts SET remaining = ? WHERE id = ?",
                             (str(remaining - paid), contribution_id))
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

    def dispute_contract(self, contract_id, raised_by, reason):
        with self._write() as conn:
            record = self._ledger.dispute_contract(contract_id, raised_by, reason)
            conn.execute("INSERT INTO contract_disputes(contract_id,raised_by,reason) VALUES(?,?,?)",
                         (contract_id, raised_by, record["reason"]))
            self._update_contract(conn, self._ledger.contracts[contract_id])
        return record

    def freeze_contract_payment(self, contract_id, reason):
        with self._write() as conn:
            before = len(self._ledger.events)
            event = self._ledger.freeze_contract_payment(contract_id, reason)
            self._insert_events(conn, self._ledger.events[before:])
            self._update_contract(conn, self._ledger.contracts[contract_id])
            payment = next(item for item in self._ledger.events if item.id == f"{contract_id}:payment")
            conn.execute("UPDATE contract_disputes SET created_at=created_at WHERE contract_id=?", (contract_id,))
        return event, payment.sequence

    def resolve_contract(self, contract_id, outcome, note, handled_by, refund_amount=None):
        with self._write() as conn:
            record, events = self._ledger.resolve_contract(contract_id, outcome, note, refund_amount)
            self._insert_events(conn, events)
            self._update_contract(conn, self._ledger.contracts[contract_id])
            conn.execute("INSERT INTO contract_resolutions(contract_id,payment_sequence,freeze_sequence,handled_by,outcome,refund_amount,retained_amount,note) VALUES(?,?,?,?,?,?,?,?)",
                         (contract_id, record["paymentSequence"], record["freezeSequence"], handled_by,
                          record["outcome"], str(record["refundAmount"]), str(record["retainedAmount"]), record["note"]))
        return self._ledger.contract_resolutions[contract_id], events

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
        with self._connect() as conn:
            approvals = {}
            for contract_id, member_id in conn.execute(
                "SELECT contract_id,member_id FROM contract_approvals ORDER BY approved_at,member_id"
            ):
                approvals.setdefault(contract_id, []).append(member_id)
            delivery = {}
            for contract_id, member_id, evidence in conn.execute(
                "SELECT contract_id,member_id,evidence FROM contract_delivery_evidence ORDER BY created_at,evidence"
            ):
                delivery.setdefault(contract_id, []).append({"memberId": member_id, "reference": evidence})
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
                "deliveryEvidence": delivery.get(contract.id, []),
                "approverIds": approvals.get(contract.id, list(contract.approver_ids)),
                "settled": contract.id in self._ledger._settled_contracts,
                "verifiedMintValue": (float(contract.verified_mint_value)
                                      if contract.verified_mint_value is not None else None),
                "verifiedMintValueExact": (str(contract.verified_mint_value)
                                           if contract.verified_mint_value is not None else None),
                "dispute": self._ledger.contract_disputes.get(contract.id),
                "resolution": self._ledger.contract_resolutions.get(contract.id),
            }
            for contract in self._ledger.contracts.values()
        ]

    def graph_payload(self) -> dict:
        """JSON-ready SourceCred-style graph projection for the API layer."""
        graph = self._ledger.graph()
        nodes = [{"address": list(node.address), "kind": node.kind, "label": node.label}
                 for node in graph.nodes]
        edges = [{"address": list(edge.address), "kind": edge.kind,
                  "source": list(edge.source), "destination": list(edge.destination),
                  "amount": float(edge.amount) if edge.amount is not None else None,
                  "amountExact": str(edge.amount) if edge.amount is not None else None}
                 for edge in graph.edges]
        # Add persisted trust signals to the same graph payload. Approval edges
        # are sourced only from contract_approvals, never from request data.
        prefix = ("cvn", self.project.id)
        with self._connect() as conn:
            trust_rows = conn.execute(
                "SELECT a.contract_id,a.member_id,'APPROVED',a.approved_at FROM contract_approvals a "
                "JOIN commission_contracts c ON c.id=a.contract_id WHERE c.project_id=? "
                "UNION ALL SELECT d.contract_id,d.raised_by,'DISPUTED',d.created_at FROM contract_disputes d "
                "JOIN commission_contracts c ON c.id=d.contract_id WHERE c.project_id=?",
                (self.project.id, self.project.id),
            ).fetchall()
        for contract_id, member_id, kind, _timestamp in trust_rows:
            edges.append({"address": list(prefix + ("edge", kind.lower(), contract_id, member_id)),
                          "kind": kind, "source": list(prefix + ("member", member_id)),
                          "destination": list(prefix + ("contract", contract_id)),
                          "amount": None, "amountExact": None})
        for event in self._ledger.events:
            if event.kind not in (LedgerEventType.FREEZE, LedgerEventType.RELEASE) or not event.contract_id:
                continue
            kind = "FROZEN" if event.kind == LedgerEventType.FREEZE else "RELEASED"
            edges.append({"address": list(prefix + ("edge", kind.lower(), event.id)),
                          "kind": kind,
                          "source": list(prefix + ("member", event.source_id or "")),
                          "destination": list(prefix + ("contract", event.contract_id)),
                          "amount": float(event.amount), "amountExact": str(event.amount)})
        return {
            "nodes": nodes,
            "edges": edges,
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
