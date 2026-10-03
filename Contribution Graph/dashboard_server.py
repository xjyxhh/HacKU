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

from contribution_engine import ContributionType, EvidenceType, VerificationDecision
from contribution_store import ContributionStore
from token_engine import TokenProject
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
        if operation == "create_project":
            if store is not None:
                raise ValueError("token ledger already exists for this server; refusing to overwrite")
            store = TokenStore(token_db_path, *args)
            return store.ledger_payload()
        if store is None:
            raise ValueError("unknown token ledger; create it via POST /api/token/project")
        result = getattr(store, operation)(*args)
        return jsonable_encoder(result, custom_encoder={Decimal: str})

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
        from token_engine import TokenTask, ValueType
        task = TokenTask(body.id, token_read().project.id, body.name, ValueType(body.value_type),
                         body.mint_cap, body.acceptance_criteria)
        return token_write("add_task", task)

    @app.post("/api/token/contracts", status_code=201)
    def token_create_contract(body: CommissionInput):
        return token_write("create_commission", body.id, body.task_id, body.principal_id,
                           body.contractor_id, body.contract_price, body.maximum_mint_value)

    @app.post("/api/token/contracts/{contract_id}/advance")
    def token_advance_contract(contract_id: str, body: ContractAdvanceInput):
        from token_engine import ContractStatus
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
        if body.decision == VerificationDecision.CONFIRM:
            minted = _token_mint_for_contribution(contribution_id, body.reviewer_id)
            if minted is not None:
                result["tokenMint"] = minted
        return result

    @app.post("/api/contributions/{contribution_id}/resolve")
    def resolve_dispute(contribution_id: str, body: ResolutionInput):
        result = write("resolve_dispute", contribution_id, body.resolved_by, body.resolution,
                       body.completion, body.support_value, body.quality)
        minted = _token_mint_for_contribution(contribution_id, body.resolved_by)
        if minted is not None:
            result["tokenMint"] = minted
        return result

    def _token_mint_for_contribution(contribution_id: str, approver_id: str):
        """Best-effort token minting after a legacy VERIFIED / RESOLVED transition.

        The legacy write is already committed at this point. A missing token
        ledger, an unmappable contribution (SUPPORT without helped member,
        zero score), or an engine rejection is reported in the response as a
        skip reason instead of failing the review itself. Evidence idempotency
        keys ("legacy:<id>") make repeat calls no-ops-safe.
        """
        if not token_db_path.is_file():
            return None
        try:
            legacy = read()
            item = legacy.contributions[contribution_id]
            store = TokenStore(token_db_path)
            from contribution_engine import contribution_score
            amount = contribution_score(item, legacy.projects[item.project_id],
                                        legacy.members, legacy.tasks)
            if amount <= 0:
                return {"skipped": "有效得分为 0，无法铸币"}
            key = [f"legacy:{item.id}"]
            if item.type == ContributionType.SUPPORT:
                if item.helped_member_id is None:
                    return {"skipped": "SUPPORT 缺少受帮助成员，无法构成委托合约"}
                contract_id = f"{item.id}:commission"
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
            event = store.mint_direct(f"{item.id}:mint", item.task_id, item.contributor_id,
                                      amount, key)
            return {"kind": "DIRECT", "eventId": event.id, "amount": float(amount)}
        except ValueError as error:
            return {"skipped": str(error)}

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
