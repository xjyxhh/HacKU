"""FastAPI service for the dashboard and contribution workflow."""

import argparse
import sqlite3
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from contribution_engine import (
    ContributionType,
    EvidenceType,
    VerificationDecision,
    contribution_score,
)
from contribution_store import ContributionStore
from token_engine import (
    ContractStatus,
    TokenProject,
    TokenTask,
    ValueType,
)
from token_store import TokenStore


ROOT = Path(__file__).with_name("dashboard")
DEFAULT_DB = Path(__file__).with_name("data.sqlite3")
DEFAULT_TOKEN_DB = Path(__file__).with_name("token.sqlite3")


class ProjectInput(BaseModel):
    id: str
    name: str


class MemberInput(BaseModel):
    id: str
    name: str


class TaskInput(BaseModel):
    id: str
    name: str
    task_value: Decimal
    description: str = ""


class ContributionInput(BaseModel):
    id: str
    contributor_id: str
    task_id: str
    type: ContributionType
    description: str
    completion: Decimal = Decimal("1")
    support_value: Decimal = Decimal("0")
    helped_member_id: str | None = None


class EvidenceInput(BaseModel):
    submitted_by: str
    kind: EvidenceType
    reference: str


class ReviewInput(BaseModel):
    reviewer_id: str
    decision: VerificationDecision
    note: str = ""
    completion: Decimal | None = None
    support_value: Decimal | None = None
    quality: Decimal | None = None


class ResolutionInput(BaseModel):
    resolved_by: str
    resolution: str
    completion: Decimal | None = None
    support_value: Decimal | None = None
    quality: Decimal | None = None


class ScorePreviewInput(BaseModel):
    completion: Decimal | None = None
    support_value: Decimal | None = None
    quality: Decimal | None = None


class TokenProjectInput(BaseModel):
    id: str
    name: str
    treasury_id: str
    member_ids: list[str]


class TokenTaskInput(BaseModel):
    id: str
    name: str
    value_type: str
    mint_cap: Decimal
    acceptance_criteria: str


class CommissionInput(BaseModel):
    id: str
    task_id: str
    principal_id: str
    contractor_id: str
    contract_price: Decimal
    maximum_mint_value: Decimal


class ContractAdvanceInput(BaseModel):
    status: str


class MintInput(BaseModel):
    event_id: str
    task_id: str
    recipient_id: str
    amount: Decimal
    evidence_hashes: list[str]


class SettleInput(BaseModel):
    verified_mint_value: Decimal
    evidence_hashes: list[str]
    approver_ids: list[str]


class TransferInput(BaseModel):
    event_id: str
    source_id: str
    destination_id: str
    amount: Decimal
    task_id: str
    evidence_hashes: list[str]


def create_app(db_path=DEFAULT_DB, token_db_path=None):
    app = FastAPI(title="Contribution Graph API")
    db_path = Path(db_path)
    token_db_path = Path(token_db_path) if token_db_path else DEFAULT_TOKEN_DB

    @app.exception_handler(ValueError)
    @app.exception_handler(InvalidOperation)
    async def bad_input(_request: Request, error: Exception):
        status = 404 if str(error).startswith("unknown ") else 400
        return JSONResponse(status_code=status, content={"detail": str(error), "error": str(error)})

    @app.exception_handler(sqlite3.Error)
    @app.exception_handler(OSError)
    async def storage_error(_request: Request, error: Exception):
        return JSONResponse(status_code=500, content={"detail": str(error), "error": str(error)})

    def read():
        return ContributionStore(db_path)

    def write(method, *args):
        result = getattr(read(), method)(*args)
        return jsonable_encoder(asdict(result), custom_encoder={Decimal: str})

    @app.get("/api/projects")
    def projects(response: Response):
        response.headers["Cache-Control"] = "no-store"
        store = read()
        return [{"id": project.id, "name": project.name} for project in store.projects.values()]

    @app.get("/api/dashboard")
    def dashboard(response: Response):
        response.headers["Cache-Control"] = "no-store"
        return read().dashboard_data("fintech")

    @app.get("/api/projects/{project_id}/dashboard")
    def project_dashboard(project_id: str):
        return read().dashboard_data(project_id)

    @app.get("/api/projects/{project_id}/token-view")
    def token_view(project_id: str, response: Response):
        """Read-only stage-1 projection of legacy contributions into the token model."""
        response.headers["Cache-Control"] = "no-store"
        return read().token_view(project_id)

    # --- Token ledger routes (durable, additive) ---
    # The token store lives in its own SQLite file (token.sqlite3 by default)
    # so the legacy eight tables stay untouched. Read routes return 404 when
    # the ledger database has not been created yet; the write routes create or
    # reuse it.

    def token_read() -> TokenStore:
        if not token_db_path.is_file():
            raise ValueError("unknown token ledger; create it via POST /api/token/project "
                             "or migrate with migrate_token_ledger.py")
        return TokenStore(token_db_path)

    def token_write(operation, *args):
        store = TokenStore(token_db_path) if token_db_path.is_file() else None
        try:
            if operation == "create_project":
                store = TokenStore(token_db_path, *args)
                return store.ledger_payload()
            if store is None:
                raise ValueError("unknown token ledger; create it via POST /api/token/project")
            result = getattr(store, operation)(*args)
            return jsonable_encoder(result, custom_encoder={Decimal: str})
        except sqlite3.Error as error:
            # Storage-level failures (locks, corruption, constraint races) are
            # reported as bad requests, not unhandled 500s.
            raise ValueError(f"token ledger storage error: {error}") from error

    @app.get("/api/token/ledger")
    def token_ledger(response: Response):
        response.headers["Cache-Control"] = "no-store"
        return token_read().ledger_payload()

    @app.get("/api/token/graph")
    def token_graph(response: Response):
        response.headers["Cache-Control"] = "no-store"
        return token_read().graph_payload()

    @app.get("/api/token/contracts")
    def token_contracts(response: Response):
        response.headers["Cache-Control"] = "no-store"
        return token_read().contracts_payload()

    @app.get("/api/token/tasks/{task_id}/budget")
    def token_task_budget(task_id: str, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return jsonable_encoder(token_read().task_budget(task_id), custom_encoder={Decimal: str})

    @app.post("/api/token/project", status_code=201)
    def token_create_project(body: TokenProjectInput):
        project = TokenProject(body.id, body.name, body.treasury_id, tuple(body.member_ids))
        return token_write("create_project", project)

    @app.post("/api/token/tasks", status_code=201)
    def token_add_task(body: TokenTaskInput):
        task = TokenTask(body.id, token_read().project.id, body.name, ValueType(body.value_type),
                         body.mint_cap, body.acceptance_criteria)
        return token_write("add_task", task)

    @app.post("/api/token/contracts", status_code=201)
    def token_create_contract(body: CommissionInput):
        return token_write("create_commission", body.id, body.task_id, body.principal_id,
                           body.contractor_id, body.contract_price, body.maximum_mint_value)

    @app.post("/api/token/contracts/{contract_id}/advance")
    def token_advance_contract(contract_id: str, body: ContractAdvanceInput):
        return token_write("advance_contract", contract_id, ContractStatus(body.status))

    @app.post("/api/token/mint", status_code=201)
    def token_mint(body: MintInput):
        return token_write("mint_direct", body.event_id, body.task_id, body.recipient_id,
                           body.amount, body.evidence_hashes)

    @app.post("/api/token/contracts/{contract_id}/settle")
    def token_settle(contract_id: str, body: SettleInput):
        mint, transfer = token_write("settle_commission", contract_id, body.verified_mint_value,
                                     body.evidence_hashes, body.approver_ids)
        return {"mint": mint, "transfer": transfer}

    @app.post("/api/token/transfer", status_code=201)
    def token_transfer(body: TransferInput):
        return token_write("transfer", body.event_id, body.source_id, body.destination_id,
                           body.amount, body.task_id, body.evidence_hashes)

    @app.get("/api/contributions/{contribution_id}")
    def contribution(contribution_id: str):
        return read().contribution_data(contribution_id)

    @app.post("/api/contributions/{contribution_id}/preview")
    def preview_score(contribution_id: str, body: ScorePreviewInput):
        return read().preview_score(contribution_id, body.completion, body.support_value, body.quality)

    @app.post("/api/projects", status_code=201)
    def create_project(body: ProjectInput):
        return write("create_project", body.id, body.name)

    @app.post("/api/projects/{project_id}/members", status_code=201)
    def add_member(project_id: str, body: MemberInput):
        return write("add_member", project_id, body.id, body.name)

    @app.post("/api/projects/{project_id}/tasks", status_code=201)
    def add_task(project_id: str, body: TaskInput):
        return write("add_task", project_id, body.id, body.name, body.task_value, body.description)

    @app.post("/api/projects/{project_id}/contributions", status_code=201)
    def submit_contribution(project_id: str, body: ContributionInput):
        return write("submit_contribution", project_id, body.id, body.contributor_id,
                     body.task_id, body.type, body.description, body.completion,
                     body.support_value, body.helped_member_id)

    @app.post("/api/contributions/{contribution_id}/evidence", status_code=201)
    def add_evidence(contribution_id: str, body: EvidenceInput):
        return write("add_evidence", contribution_id, body.submitted_by, body.kind, body.reference)

    @app.post("/api/contributions/{contribution_id}/reviews")
    def review_contribution(contribution_id: str, body: ReviewInput):
        result = write("review_contribution", contribution_id, body.reviewer_id, body.decision,
                       body.note, body.completion, body.support_value, body.quality)
        # CONFIRM and ADJUST both move a PENDING contribution to VERIFIED, so
        # both must mint; DISPUTE freezes any tokens the contribution already
        # minted. Every outcome is best-effort and never changes the legacy
        # review result that was already committed above.
        if body.decision in (VerificationDecision.CONFIRM, VerificationDecision.ADJUST):
            minted = _token_mint_for_contribution(contribution_id, body.reviewer_id)
            if minted is not None:
                result["tokenMint"] = minted
        elif body.decision == VerificationDecision.DISPUTE:
            frozen = _token_freeze_for_contribution(contribution_id, body.note)
            if frozen is not None:
                result["tokenFrozen"] = frozen
        return result

    @app.post("/api/contributions/{contribution_id}/resolve")
    def resolve_dispute(contribution_id: str, body: ResolutionInput):
        result = write("resolve_dispute", contribution_id, body.resolved_by, body.resolution,
                       body.completion, body.support_value, body.quality)
        # Dispute resolution restores frozen tokens first, then corrects the
        # released amount to the dispute's final score. When the final score
        # equals the frozen amount this is exactly "release"; when it differs
        # the delta is minted (higher) or paid back to the treasury (lower).
        # All best-effort: failures are reported, never thrown, and the
        # already-committed legacy resolution is never affected.
        token_result = _token_resolve_for_contribution(contribution_id, body.resolved_by,
                                                       body.resolution)
        if token_result is not None:
            result["tokenResolved"] = token_result
        return result

    def _legacy_score(contribution_id):
        legacy = read()
        item = legacy.contributions[contribution_id]
        project = legacy.projects[item.project_id]
        return item, contribution_score(item, project, legacy.members, legacy.tasks)

    def _token_mint_for_contribution(contribution_id: str, approver_id: str):
        """Best-effort token minting after a legacy VERIFIED / RESOLVED transition.

        A missing token ledger, an unmappable contribution, or an engine
        rejection is reported in the response as a skip reason instead of
        failing the review itself. Evidence idempotency keys ("legacy:<id>")
        make repeat calls no-ops-safe.
        """
        if not token_db_path.is_file():
            return None
        try:
            item, amount = _legacy_score(contribution_id)
            if amount <= 0:
                return {"skipped": "有效得分为 0，无法铸币"}
            key = [f"legacy:{item.id}"]
            store = _open_token_store()
            if item.type == ContributionType.SUPPORT:
                if item.helped_member_id is None:
                    return {"skipped": "SUPPORT 缺少受帮助成员，无法构成委托合约"}
                contract_id = f"{item.id}:commission"
                if contract_id in store.ledger.contracts:
                    return {"skipped": "委托合约已存在（此前已铸币或已结算）"}
                store.create_commission(contract_id, item.task_id, item.helped_member_id,
                                        item.contributor_id, amount, amount)
                for status in ("OFFERED", "ACCEPTED", "CREDIT_RESERVED", "DELIVERED", "VERIFIED"):
                    store.advance_contract(contract_id, status)
                approvers = [member for member in store.project.member_ids
                             if member not in (item.helped_member_id, item.contributor_id)]
                mint, transfer = store.settle_commission(contract_id, amount, key,
                                                         approvers[:1] or [approver_id])
                return {"kind": "COMMISSION", "contractId": contract_id,
                        "mintEventId": mint.id, "transferEventId": transfer.id,
                        "amount": float(amount)}
            mint_event_id = f"{item.id}:mint"
            if any(event.id == mint_event_id for event in store.ledger.events):
                return {"skipped": "直接铸币已存在（此前已铸币）"}
            event = store.mint_direct(mint_event_id, item.task_id, item.contributor_id,
                                      amount, key)
            return {"kind": "DIRECT", "eventId": event.id, "amount": float(amount)}
        except Exception as error:
            # Any ledger failure (engine rejection, sqlite, disk, schema drift)
            # must never surface as an error after the legacy write already
            # committed; the dashboard behaves exactly as before fusion.
            return {"skipped": f"{type(error).__name__}: {error}"}

    def _frozen_legacy_mints(contribution_id: str):
        """Sequences of MINT events already recorded for this contribution."""
        store = _open_token_store()
        frozen = {event.destination_id for event in store.ledger.events
                  if event.kind.name == "FREEZE"}
        return [
            event.sequence for event in store.ledger.events
            if event.kind.name == "MINT"
            and (event.id == f"{contribution_id}:mint"
                 or event.contract_id == f"{contribution_id}:commission")
            and event.sequence not in frozen
        ]

    def _token_freeze_for_contribution(contribution_id: str, reason: str):
        """Freeze tokens minted for this contribution when it enters DISPUTED."""
        if not token_db_path.is_file():
            return None
        try:
            sequences = _frozen_legacy_mints(contribution_id)
            if not sequences:
                return {"skipped": "没有需要冻结的铸币记录"}
            store = _open_token_store()
            events = store.freeze_events(sequences, reason.strip() or "争议冻结",
                                         tag=contribution_id)
            return {"kind": "FREEZE", "eventIds": [event.id for event in events],
                    "sequences": [event.sequence for event in events]}
        except Exception as error:
            return {"skipped": f"{type(error).__name__}: {error}"}

    def _open_token_store():
        """Open the ledger, converting storage failures into skipped markers."""
        try:
            return TokenStore(token_db_path)
        except sqlite3.Error as error:
            raise ValueError(f"token ledger storage error: {error}") from error

    def _token_release_for_contribution(contribution_id: str, note: str):
        """Release frozen tokens; returns None when nothing is frozen."""
        if not token_db_path.is_file():
            return None
        try:
            store = _open_token_store()
            sequences = [
                event.sequence for event in store.ledger.events
                if event.kind.name == "MINT"
                and (event.id == f"{contribution_id}:mint"
                     or event.contract_id == f"{contribution_id}:commission")
                and event.sequence in store.ledger._frozen_events
            ]
            if not sequences:
                return None
            events = store.release_events(sequences, note.strip() or "争议已解决",
                                          tag=contribution_id)
            return {"kind": "RELEASE", "eventIds": [event.id for event in events],
                    "sequences": [event.sequence for event in events]}
        except Exception as error:
            return {"skipped": f"{type(error).__name__}: {error}"}

    def _token_resolve_for_contribution(contribution_id: str, approver_id: str, note: str):
        """Reconcile the token ledger after a dispute resolves.

        Releases any tokens frozen during the dispute, then corrects the
        released amount to the dispute's final score: mints the difference
        when the final score is higher, or transfers the difference back to
        the treasury when it is lower. When there is nothing frozen (the
        contribution was disputed before minting), falls back to a normal
        mint for the final score.
        """
        if not token_db_path.is_file():
            return None
        try:
            released = _token_release_for_contribution(contribution_id, note)
            item, final_amount = _legacy_score(contribution_id)
            store = _open_token_store()
            mints = [
                event for event in store.ledger.events
                if event.kind.name == "MINT"
                and (event.id == f"{contribution_id}:mint"
                     or event.contract_id == f"{contribution_id}:commission")
            ]
            frozen_amount = sum((event.amount for event in mints), Decimal("0"))
            if not mints:
                # Disputed before any mint happened: resolve mints the final score.
                minted = _token_mint_for_contribution(contribution_id, approver_id)
                if minted is not None and "skipped" not in minted:
                    return {"released": released, "minted": minted,
                            "finalAmount": float(final_amount)}
                return {"released": released, "finalAmount": float(final_amount)}
            if final_amount <= 0:
                # Resolved to zero: the release already removed the tokens.
                return {"released": released, "finalAmount": 0.0}
            delta = final_amount - frozen_amount
            if delta == 0:
                return {"released": released, "finalAmount": float(final_amount)}
            if delta > 0:
                event = store.mint_direct(
                    f"{contribution_id}:adjust-mint", item.task_id, item.contributor_id,
                    delta, [f"legacy:{item.id}:resolve:{note.strip() or 'resolved'}"],
                )
                correction = {"kind": "MINT", "eventId": event.id, "amount": float(delta)}
            else:
                event = store.transfer(
                    f"{contribution_id}:refund", item.contributor_id,
                    store.project.treasury_id, -delta, item.task_id,
                    [f"legacy:{item.id}:resolve:{note.strip() or 'resolved'}"],
                )
                correction = {"kind": "REFUND", "eventId": event.id, "amount": float(-delta)}
            return {"released": released, "correction": correction,
                    "finalAmount": float(final_amount)}
        except Exception as error:
            return {"skipped": f"{type(error).__name__}: {error}"}

    app.mount("/", StaticFiles(directory=ROOT, html=True), name="dashboard")
    return app


app = create_app()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--token-db", type=Path, default=DEFAULT_TOKEN_DB,
                        help="durable token ledger database (created on first use)")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.db == DEFAULT_DB and not args.db.is_file():
        parser.error(f"database not found: {args.db}; import data.json with import_json.py first")
    print(f"SQLite database: {args.db.resolve()}", flush=True)
    print(f"Token ledger database: {args.token_db.resolve()}", flush=True)
    uvicorn.run(create_app(args.db, args.token_db), host="127.0.0.1", port=args.port)
