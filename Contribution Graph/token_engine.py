"""Token ledger, commission settlement, and graph projection for role A."""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from hashlib import sha256
from typing import Iterable


ZERO = Decimal("0")


class ValueType(str, Enum):
    CORE = "CORE"
    REVIEW = "REVIEW"
    COORDINATION = "COORDINATION"


class ProductionMode(str, Enum):
    DIRECT = "DIRECT"
    COMMISSIONED = "COMMISSIONED"


class ContractStatus(str, Enum):
    DRAFT = "DRAFT"
    OFFERED = "OFFERED"
    ACCEPTED = "ACCEPTED"
    CREDIT_RESERVED = "CREDIT_RESERVED"
    DELIVERED = "DELIVERED"
    VERIFIED = "VERIFIED"
    DISPUTED = "DISPUTED"
    FROZEN = "FROZEN"
    SETTLED = "SETTLED"


class LedgerEventType(str, Enum):
    MINT = "MINT"
    TRANSFER = "TRANSFER"
    FREEZE = "FREEZE"
    RELEASE = "RELEASE"
    REFUND = "REFUND"
    SPLIT = "SPLIT"


@dataclass(frozen=True)
class TokenProject:
    id: str
    name: str
    treasury_id: str
    member_ids: tuple[str, ...]


@dataclass(frozen=True)
class TokenTask:
    id: str
    project_id: str
    name: str
    value_type: ValueType
    mint_cap: Decimal
    acceptance_criteria: str


@dataclass
class CommissionContract:
    id: str
    project_id: str
    task_id: str
    principal_id: str
    contractor_id: str
    value_type: ValueType
    contract_price: Decimal
    maximum_mint_value: Decimal
    acceptance_criteria_hash: str
    status: ContractStatus = ContractStatus.DRAFT
    evidence_hashes: list[str] = field(default_factory=list)
    approver_ids: list[str] = field(default_factory=list)
    verified_mint_value: Decimal | None = None


@dataclass(frozen=True)
class LedgerEvent:
    sequence: int
    id: str
    project_id: str
    kind: LedgerEventType
    amount: Decimal
    source_id: str | None
    destination_id: str | None
    task_id: str
    contract_id: str | None
    evidence_key: str
    note: str = ""


@dataclass(frozen=True)
class GraphNode:
    address: tuple[str, ...]
    kind: str
    label: str


@dataclass(frozen=True)
class GraphEdge:
    address: tuple[str, ...]
    kind: str
    source: tuple[str, ...]
    destination: tuple[str, ...]
    amount: Decimal | None = None


@dataclass(frozen=True)
class ContributionGraph:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]


def criteria_hash(criteria: str) -> str:
    if not criteria.strip():
        raise ValueError("acceptance criteria must be nonempty")
    return sha256(criteria.encode("utf-8")).hexdigest()


def evidence_key(hashes: Iterable[str]) -> str:
    values = sorted(set(hashes))
    if not values or any(not value.strip() for value in values):
        raise ValueError("at least one nonempty evidence hash is required")
    return sha256("\n".join(values).encode("utf-8")).hexdigest()


def _amount(value, name: str, *, allow_zero: bool = True) -> Decimal:
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < ZERO or (not allow_zero and amount == ZERO):
        qualifier = "positive" if not allow_zero else "nonnegative"
        raise ValueError(f"{name} must be a {qualifier} finite number")
    return amount


class TokenLedger:
    """Append-only in-memory ledger with deterministic balances and graph output."""

    def __init__(self, project: TokenProject):
        if not project.id or not project.name.strip() or not project.treasury_id:
            raise ValueError("project id, name, and treasury id are required")
        if len(set(project.member_ids)) != len(project.member_ids):
            raise ValueError("project member ids must be unique")
        self.project = project
        self.tasks: dict[str, TokenTask] = {}
        self.contracts: dict[str, CommissionContract] = {}
        self.events: list[LedgerEvent] = []
        self._event_ids: set[str] = set()
        self._minted_evidence: set[str] = set()
        self._settled_contracts: set[str] = set()
        self._frozen_events: dict[int, set[int]] = {}

    def add_task(self, task: TokenTask) -> None:
        if task.id in self.tasks or task.project_id != self.project.id:
            raise ValueError("task id must be new and belong to the project")
        if not task.name.strip():
            raise ValueError("task name must be nonempty")
        _amount(task.mint_cap, "mint cap")
        if not task.acceptance_criteria.strip():
            raise ValueError("acceptance criteria must be nonempty")
        self.tasks[task.id] = task

    def create_commission(
        self,
        contract_id: str,
        task_id: str,
        principal_id: str,
        contractor_id: str,
        contract_price,
        maximum_mint_value,
    ) -> CommissionContract:
        task = self._task(task_id)
        if not contract_id or contract_id in self.contracts:
            raise ValueError("contract id must be new")
        self._member(principal_id)
        self._member(contractor_id)
        if principal_id == contractor_id:
            raise ValueError("principal and contractor must be different members")
        price = _amount(contract_price, "contract price")
        maximum = _amount(maximum_mint_value, "maximum mint value", allow_zero=False)
        if price > maximum:
            raise ValueError("contract price cannot exceed maximum mint value")
        if maximum > task.mint_cap:
            raise ValueError("maximum mint value cannot exceed task mint cap")
        contract = CommissionContract(
            contract_id,
            self.project.id,
            task.id,
            principal_id,
            contractor_id,
            task.value_type,
            price,
            maximum,
            criteria_hash(task.acceptance_criteria),
        )
        self.contracts[contract_id] = contract
        return contract

    def advance_contract(self, contract_id: str, status: ContractStatus) -> CommissionContract:
        contract = self._contract(contract_id)
        allowed = {
            ContractStatus.DRAFT: {ContractStatus.OFFERED},
            ContractStatus.OFFERED: {ContractStatus.ACCEPTED},
            ContractStatus.ACCEPTED: {ContractStatus.CREDIT_RESERVED},
            ContractStatus.CREDIT_RESERVED: {ContractStatus.DELIVERED},
            ContractStatus.DELIVERED: {ContractStatus.VERIFIED, ContractStatus.DISPUTED},
            ContractStatus.VERIFIED: {ContractStatus.DISPUTED},
            ContractStatus.DISPUTED: {ContractStatus.FROZEN},
        }
        status = ContractStatus(status)
        if status not in allowed.get(contract.status, set()):
            raise ValueError(f"invalid contract transition: {contract.status.value} -> {status.value}")
        contract.status = status
        return contract

    def mint_direct(self, event_id: str, task_id: str, recipient_id: str, amount, evidence_hashes) -> LedgerEvent:
        task = self._task(task_id)
        self._member(recipient_id)
        value = _amount(amount, "mint amount", allow_zero=False)
        key = evidence_key(evidence_hashes)
        self._validate_mint(task, value, key)
        event = self._event(event_id, LedgerEventType.MINT, value, self.project.treasury_id,
                            recipient_id, task.id, None, key, "direct production")
        self._minted_evidence.add(key)
        return event

    def settle_commission(
        self,
        contract_id: str,
        verified_mint_value,
        evidence_hashes,
        approver_ids: Iterable[str],
    ) -> tuple[LedgerEvent, LedgerEvent]:
        contract = self._contract(contract_id)
        if contract.id in self._settled_contracts:
            raise ValueError("contract is already settled")
        if contract.status != ContractStatus.VERIFIED:
            raise ValueError("only verified contracts can be settled")
        value = _amount(verified_mint_value, "verified mint value", allow_zero=False)
        if value > contract.maximum_mint_value:
            raise ValueError("verified mint value exceeds contract maximum")
        key = evidence_key(evidence_hashes)
        task = self._task(contract.task_id)
        self._validate_mint(task, value, key)
        approvers = list(dict.fromkeys(approver_ids))
        if not approvers:
            raise ValueError("at least one independent approver is required")
        for member_id in approvers:
            self._member(member_id)
        if set(approvers) & {contract.principal_id, contract.contractor_id}:
            raise ValueError("principal and contractor cannot independently approve their contract")
        payment = min(contract.contract_price, value)
        next_sequence = len(self.events) + 1
        mint = LedgerEvent(next_sequence, f"{contract.id}:mint", self.project.id, LedgerEventType.MINT,
                           value, self.project.treasury_id, contract.principal_id, task.id,
                           contract.id, key, "commissioned production")
        transfer = LedgerEvent(next_sequence + 1, f"{contract.id}:payment", self.project.id,
                               LedgerEventType.TRANSFER, payment, contract.principal_id,
                               contract.contractor_id, task.id, contract.id, key,
                               "atomic commission payment")
        if mint.id in self._event_ids or transfer.id in self._event_ids:
            raise ValueError("settlement event id already exists")
        self.events.extend((mint, transfer))
        self._event_ids.update((mint.id, transfer.id))
        self._minted_evidence.add(key)
        self._settled_contracts.add(contract.id)
        contract.evidence_hashes = sorted(set(evidence_hashes))
        contract.approver_ids = approvers
        contract.verified_mint_value = value
        contract.status = ContractStatus.SETTLED
        return mint, transfer

    def transfer(self, event_id: str, source_id: str, destination_id: str, amount, task_id: str,
                 evidence_hashes) -> LedgerEvent:
        self._member(source_id)
        if destination_id != self.project.treasury_id:
            self._member(destination_id)
        self._task(task_id)
        if source_id == destination_id:
            raise ValueError("source and destination must be different")
        value = _amount(amount, "transfer amount", allow_zero=False)
        if self.balance(source_id) < value:
            raise ValueError("insufficient token balance")
        return self._event(event_id, LedgerEventType.TRANSFER, value, source_id, destination_id,
                           task_id, None, evidence_key(evidence_hashes), "member transfer")

    def freeze_events(self, sequences: Iterable[int], reason: str = "",
                      tag: str | None = None) -> list[LedgerEvent]:
        """Freeze previously settled events so they stop counting in balances.

        Creates an append-only FREEZE record per settled event instead of
        reversing it, matching the dispute state machine (DISPUTED -> FROZEN).
        Already frozen sequences are skipped so repeated calls stay idempotent.
        ``tag`` labels the freeze record (e.g. the contribution id) in
        destination_id so callers can find freezes by business key later.
        """
        events: list[LedgerEvent] = []
        reason = reason.strip()
        for sequence in sequences:
            target = self._event_by_sequence(sequence)
            if target.kind != LedgerEventType.MINT:
                raise ValueError("only MINT events can be frozen")
            frozen = self._frozen_events.setdefault(sequence, set())
            if len(frozen) >= 1:
                continue
            events.append(self._event(
                f"freeze:{target.id}", LedgerEventType.FREEZE, target.amount,
                target.destination_id, tag or str(sequence), target.task_id,
                target.contract_id, target.evidence_key,
                reason or "dispute freeze",
            ))
            frozen.add(len(events))
        return events

    def release_events(self, sequences: Iterable[int], note: str = "",
                       tag: str | None = None) -> list[LedgerEvent]:
        """Release frozen events back into balances after a dispute resolves.

        ``tag`` must match the tag the FREEZE records were created with.
        """
        events: list[LedgerEvent] = []
        for sequence in sequences:
            target = self._event_by_sequence(sequence)
            if len(self._frozen_events.get(sequence, ())) < 1:
                raise ValueError(f"event {sequence} is not frozen")
            events.append(self._event(
                f"release:{target.id}", LedgerEventType.RELEASE, target.amount,
                target.destination_id, tag or str(sequence), target.task_id,
                target.contract_id, target.evidence_key,
                note.strip() or "dispute resolved",
            ))
            if target.kind == LedgerEventType.MINT:
                self._minted_evidence.add(target.evidence_key)
            self._frozen_events[sequence].clear()
        return events

    def balance(self, member_id: str) -> Decimal:
        self._member(member_id)
        balance = ZERO
        for event in self.events:
            if event.kind not in {LedgerEventType.MINT, LedgerEventType.TRANSFER,
                                  LedgerEventType.RELEASE, LedgerEventType.REFUND,
                                  LedgerEventType.SPLIT, LedgerEventType.FREEZE}:
                continue
            if event.kind == LedgerEventType.FREEZE:
                # FREEZE pauses the holder's balance: subtract only. The
                # frozen event's sequence is kept in destination_id.
                if event.source_id == member_id:
                    balance -= event.amount
            elif event.kind == LedgerEventType.RELEASE:
                # RELEASE restores the amount that FREEZE subtracted, as one
                # atomic reversal. It does not change treasury: the MINT the
                # FREEZE paused is still outstanding, so total supply is
                # unchanged and the holder's balance returns to its pre-FREEZE
                # value. The unfrozen event's sequence is in destination_id.
                if event.source_id == member_id:
                    balance += event.amount
            else:
                if event.destination_id == member_id:
                    balance += event.amount
                if event.source_id == member_id:
                    balance -= event.amount
        return balance

    def balances(self) -> dict[str, Decimal]:
        return {member_id: self.balance(member_id) for member_id in self.project.member_ids}

    def total_supply(self) -> Decimal:
        return sum((event.amount for event in self.events if event.kind == LedgerEventType.MINT), ZERO)

    def minted_for_task(self, task_id: str) -> Decimal:
        self._task(task_id)
        return sum((event.amount for event in self.events
                    if event.kind == LedgerEventType.MINT and event.task_id == task_id), ZERO)

    def task_budget(self, task_id: str) -> dict[str, Decimal]:
        task = self._task(task_id)
        minted = self.minted_for_task(task_id)
        reserved = sum((contract.maximum_mint_value for contract in self.contracts.values()
                        if contract.task_id == task_id and contract.status not in
                        {ContractStatus.SETTLED, ContractStatus.DISPUTED, ContractStatus.FROZEN}), ZERO)
        return {"mintCap": task.mint_cap, "minted": minted, "reserved": reserved,
                "available": max(ZERO, task.mint_cap - minted - reserved)}

    def graph(self) -> ContributionGraph:
        prefix = ("cvn", self.project.id)
        project_addr = prefix + ("project", self.project.id)
        treasury_addr = prefix + ("treasury", self.project.treasury_id)
        nodes = {
            project_addr: GraphNode(project_addr, "PROJECT", self.project.name),
            treasury_addr: GraphNode(treasury_addr, "TREASURY", self.project.treasury_id),
        }
        for member_id in self.project.member_ids:
            address = prefix + ("member", member_id)
            nodes[address] = GraphNode(address, "MEMBER", member_id)
        for task in self.tasks.values():
            address = prefix + ("task", task.id)
            nodes[address] = GraphNode(address, "TASK", task.name)
        for contract in self.contracts.values():
            address = prefix + ("contract", contract.id)
            nodes[address] = GraphNode(address, "COMMISSION_CONTRACT", contract.id)
        edges: list[GraphEdge] = []
        for contract in self.contracts.values():
            contract_addr = prefix + ("contract", contract.id)
            principal_addr = prefix + ("member", contract.principal_id)
            contractor_addr = prefix + ("member", contract.contractor_id)
            task_addr = prefix + ("task", contract.task_id)
            edges.extend((
                GraphEdge(prefix + ("edge", "commissioned", contract.id), "COMMISSIONED",
                          principal_addr, contract_addr, contract.contract_price),
                GraphEdge(prefix + ("edge", "executed", contract.id), "EXECUTED",
                          contractor_addr, task_addr),
                GraphEdge(prefix + ("edge", "relates-to", contract.id), "CONTRIBUTES_TO",
                          contract_addr, task_addr),
            ))
        for event in self.events:
            source = treasury_addr if event.source_id == self.project.treasury_id else prefix + ("member", event.source_id or "")
            destination = prefix + ("member", event.destination_id or "")
            edges.append(GraphEdge(prefix + ("edge", event.kind.value.lower(), event.id),
                                   "MINTED" if event.kind == LedgerEventType.MINT else "PAID",
                                   source, destination, event.amount))
        return ContributionGraph(tuple(nodes[key] for key in sorted(nodes)), tuple(edges))

    def _validate_mint(self, task: TokenTask, value: Decimal, key: str) -> None:
        if key in self._minted_evidence:
            raise ValueError("evidence has already been used for minting")
        if self.minted_for_task(task.id) + value > task.mint_cap:
            raise ValueError("task mint cap exceeded")

    def _event_by_sequence(self, sequence: int) -> LedgerEvent:
        if not isinstance(sequence, int) or sequence < 1 or sequence > len(self.events):
            raise ValueError(f"unknown event sequence: {sequence}")
        return self.events[sequence - 1]

    def _event(self, event_id, kind, amount, source, destination, task_id, contract_id, key, note):
        if not event_id or event_id in self._event_ids:
            raise ValueError("event id must be new")
        event = LedgerEvent(len(self.events) + 1, event_id, self.project.id, kind, amount,
                            source, destination, task_id, contract_id, key, note)
        self.events.append(event)
        self._event_ids.add(event_id)
        if kind == LedgerEventType.FREEZE:
            # A frozen mint's evidence may not mint again while frozen.
            self._minted_evidence.discard(key)
        return event

    def _task(self, task_id: str) -> TokenTask:
        try:
            return self.tasks[task_id]
        except KeyError:
            raise ValueError(f"unknown task: {task_id}") from None

    def _contract(self, contract_id: str) -> CommissionContract:
        try:
            return self.contracts[contract_id]
        except KeyError:
            raise ValueError(f"unknown contract: {contract_id}") from None

    def _member(self, member_id: str) -> None:
        if member_id not in self.project.member_ids:
            raise ValueError("member is not part of the project")
