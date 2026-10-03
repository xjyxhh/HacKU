"""FastAPI service for the dashboard and contribution workflow."""

import argparse
import hmac
import json
import os
import sqlite3
from dataclasses import asdict, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from auth_store import AuthStore
from contribution_engine import (
    ContributionStatus,
    ContributionType,
    EvidenceType,
    VerificationDecision,
    contribution_score,
    demo_data,
    score_members,
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
DATA_DIR = Path(os.environ.get("POCKETBAY_DATA_DIR", Path(__file__).parent))
DEFAULT_DB = DATA_DIR / "data.sqlite3"
DEFAULT_TOKEN_DB = DATA_DIR / "token.sqlite3"


def token_issue(error: Exception) -> str:
    detail = str(error)
    known = {
        "task mint cap exceeded": "任务铸币上限不足；请先提高上限，再补同步",
        "evidence has already been used for minting": "证据标识已经用于铸币；请核对贡献与账本事件",
        "insufficient token balance to freeze": "持有人余额不足，无法冻结关联 Token",
        "insufficient token balance": "成员余额不足，无法完成 Token 处理",
        "token ledger storage error": "Token 账本读取失败；请检查数据库并重试",
    }
    return next((message for key, message in known.items() if key in detail),
                "Token 处理失败；请检查账本状态后补同步")


class ProjectInput(BaseModel):
    id: str
    name: str


class MemberInput(BaseModel):
    id: str
    name: str
    role: str = "MEMBER"


class MemberInviteInput(BaseModel):
    identifier: str
    role: str = "MEMBER"


class MemberRoleInput(BaseModel):
    role: str


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


class TokenCapInput(BaseModel):
    mint_cap: Decimal


class CommissionInput(BaseModel):
    id: str
    task_id: str
    principal_id: str
    contractor_id: str
    contract_price: Decimal
    maximum_mint_value: Decimal


class ContractAdvanceInput(BaseModel):
    status: str
    evidence_hashes: list[str] = Field(default_factory=list)


class MintInput(BaseModel):
    event_id: str
    task_id: str
    recipient_id: str
    amount: Decimal
    evidence_hashes: list[str]
    contribution_id: str | None = None


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


class FreezeInput(BaseModel):
    sequences: list[int]
    reason: str = ""
    tag: str | None = None


class ReleaseInput(BaseModel):
    sequences: list[int]
    note: str = ""
    tag: str | None = None


class LoginInput(BaseModel):
    member_id: str | None = None
    identifier: str | None = None
    password: str


class RegisterInput(BaseModel):
    email: str
    display_name: str
    password: str


class ProfileInput(BaseModel):
    display_name: str
    email: str
    bio: str = ""
    avatar_url: str = ""
    wallet_address: str = ""


class MemberAccountInput(BaseModel):
    member_id: str
    password: str


def create_app(db_path=DEFAULT_DB, token_db_path=None, token_admin_key=None):
    app = FastAPI(title="Contribution Graph API")
    db_path = Path(db_path)
    token_db_path = Path(token_db_path) if token_db_path else DEFAULT_TOKEN_DB
    token_admin_key = token_admin_key if token_admin_key is not None else os.environ.get("TOKEN_ADMIN_KEY")
    if os.environ.get("POCKETBAY_DATA_DIR") and db_path == DEFAULT_DB and not db_path.exists():
        from import_json import import_json
        import_json(Path(__file__).with_name("data.json"), db_path)

    auth_store_instance = None

    def auth_store(create=False):
        nonlocal auth_store_instance
        if not db_path.is_file() and not create:
            return None
        if create:
            read()
        if auth_store_instance is None:
            auth_store_instance = AuthStore(db_path)
        return auth_store_instance

    @app.middleware("http")
    async def authenticate_api_requests(request: Request, call_next):
        length = request.headers.get("content-length", "0")
        if request.method in ("POST", "PATCH") and length.isdigit() and int(length) > 1_000_000:
            return JSONResponse(status_code=413, content={"detail": "request body exceeds 1 MB"})
        if request.method in ("POST", "PATCH"):
            if len(await request.body()) > 1_000_000:
                return JSONResponse(status_code=413, content={"detail": "request body exceeds 1 MB"})
        if request.method == "POST" and request.headers.get("content-type", "").startswith("application/json"):
            def reject_nonfinite(value):
                raise ValueError("invalid JSON number")
            def check_float(value):
                number = Decimal(value)
                if not number.is_finite() or abs(number) > Decimal("1000000000000"):
                    raise ValueError("invalid JSON number")
                return number
            try:
                json.loads(await request.body(), parse_constant=reject_nonfinite,
                           parse_float=check_float)
            except ValueError as error:
                if str(error) == "invalid JSON number":
                    return JSONResponse(status_code=422, content={"detail": "invalid JSON number"})
        path = request.url.path
        api_request = path.startswith("/api/")
        is_login = path == "/api/auth/login" and request.method == "POST"
        is_register = path == "/api/auth/register" and request.method == "POST"
        is_account_provision = path == "/api/admin/member-accounts" and request.method == "POST"
        is_public_demo = path == "/api/demo" and request.method == "GET"
        if request.method == "POST" and (is_login or is_register):
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc.casefold() != request.headers.get("host", "").casefold():
                return JSONResponse(status_code=403, content={"detail": "cross-origin request rejected"})
        if (api_request and not is_login and not is_register
                and not is_account_provision and not is_public_demo):
            supplied = request.headers.get("X-Token-Admin-Key", "")
            is_admin = bool(token_admin_key) and hmac.compare_digest(supplied, token_admin_key)
            origin = request.headers.get("origin")
            if request.method in ("POST", "PATCH", "PUT", "DELETE") and origin:
                if urlsplit(origin).netloc.casefold() != request.headers.get("host", "").casefold():
                    return JSONResponse(status_code=403, content={"detail": "cross-origin request rejected"})

            accounts = auth_store()
            session_member = accounts.session_member(request.cookies.get("cg_session")) if accounts else None
            if session_member is None and not is_admin:
                return JSONResponse(status_code=401, content={"detail": "authentication required"})
            request.state.member_id = session_member
            request.state.is_admin = is_admin
        elif is_account_provision:
            if not token_admin_key:
                return JSONResponse(status_code=503, content={"detail": "TOKEN_ADMIN_KEY is not configured"})
            supplied = request.headers.get("X-Token-Admin-Key", "")
            if not hmac.compare_digest(supplied, token_admin_key):
                return JSONResponse(status_code=403, content={"detail": "invalid token admin key"})
        result = await call_next(request)
        if api_request:
            result.headers["Cache-Control"] = "no-store"
        return result

    @app.exception_handler(ValueError)
    @app.exception_handler(InvalidOperation)
    async def bad_input(_request: Request, error: Exception):
        status = 404 if str(error).startswith("unknown ") else 400
        message = str(error)
        if "Out of range float" in message:
            message = "numeric value is out of range"
        return JSONResponse(status_code=status, content={"detail": message, "error": message})

    @app.exception_handler(sqlite3.Error)
    @app.exception_handler(OSError)
    async def storage_error(_request: Request, error: Exception):
        return JSONResponse(status_code=500, content={"detail": "storage error", "error": "storage error"})

    def read():
        return ContributionStore(db_path)

    def require_project_member(project_id: str, request: Request):
        store = read()
        project = store.projects.get(project_id)
        if project is None:
            raise ValueError(f"unknown project {project_id}")
        if (not getattr(request.state, "is_admin", False)
                and request.state.member_id not in project.member_ids):
            raise HTTPException(status_code=403, detail="project membership required")
        return store

    def require_project_role(project_id: str, request: Request, *roles):
        store = require_project_member(project_id, request)
        if (not getattr(request.state, "is_admin", False)
                and store.membership_roles.get((project_id, request.state.member_id)) not in roles):
            raise HTTPException(status_code=403, detail="project role does not allow this action")
        return store

    def require_contribution_member(contribution_id: str, request: Request):
        store = read()
        item = store.contributions.get(contribution_id)
        if item is None:
            raise ValueError(f"unknown contribution {contribution_id}")
        if (not getattr(request.state, "is_admin", False)
                and request.state.member_id not in store.projects[item.project_id].member_ids):
            raise HTTPException(status_code=403, detail="project membership required")
        return store, item

    def require_token_member(request: Request):
        store = token_read(request.headers.get("X-Project-ID"))
        if (not getattr(request.state, "is_admin", False)
                and request.state.member_id not in store.project.member_ids):
            raise HTTPException(status_code=403, detail="token project membership required")
        return store

    def require_token_role(request: Request, *roles, project_id=None):
        store = token_read(project_id or request.headers.get("X-Project-ID"))
        if getattr(request.state, "is_admin", False):
            return store
        role = store_role(store.project.id, request.state.member_id)
        if role not in roles:
            raise HTTPException(status_code=403, detail="project role does not allow this token action")
        return store

    def store_role(project_id, member_id):
        return read().membership_roles.get((project_id, member_id))

    def write(method, *args):
        result = getattr(read(), method)(*args)
        return jsonable_encoder(asdict(result), custom_encoder={Decimal: str})

    @app.post("/api/auth/register", status_code=201)
    def register(body: RegisterInput, request: Request, response: Response):
        store = auth_store(create=True)
        member_id = store.register(body.email, body.display_name, body.password)
        token = store.create_session(member_id, body.password)
        secure = (request.url.scheme == "https"
                  or request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https")
        response.set_cookie(
            "cg_session", token, max_age=7 * 24 * 60 * 60, httponly=True,
            secure=secure, samesite="lax", path="/",
        )
        return {"memberId": member_id, "memberName": body.display_name.strip()}

    @app.post("/api/auth/login")
    def login(body: LoginInput, request: Request, response: Response):
        store = auth_store(create=True)
        identifier = body.identifier or body.member_id
        token = store.create_session(identifier, body.password) if identifier else None
        if token is None:
            return JSONResponse(status_code=401, content={"detail": "invalid member ID, email, or password"})
        member_id = store.session_member(token)
        secure = (request.url.scheme == "https"
                  or request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https")
        response.set_cookie(
            "cg_session", token, max_age=7 * 24 * 60 * 60, httponly=True,
            secure=secure, samesite="lax", path="/",
        )
        return {"memberId": member_id, "memberName": store.member_name(member_id)}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response):
        store = auth_store()
        if store:
            store.delete_session(request.cookies.get("cg_session"))
        response.delete_cookie("cg_session", path="/", httponly=True, samesite="lax")
        return {"ok": True}

    @app.get("/api/auth/session")
    def current_session(request: Request, response: Response):
        store = auth_store()
        member_id = store.session_member(request.cookies.get("cg_session")) if store else None
        if member_id is None:
            return JSONResponse(status_code=401, content={"detail": "authentication required"})
        response.headers["Cache-Control"] = "no-store"
        return {"memberId": member_id, "memberName": store.member_name(member_id)}

    @app.get("/api/profile")
    def profile(request: Request):
        if request.state.member_id is None:
            raise HTTPException(status_code=401, detail="member session required")
        return auth_store().profile(request.state.member_id)

    @app.patch("/api/profile")
    def update_profile(body: ProfileInput, request: Request):
        if request.state.member_id is None:
            raise HTTPException(status_code=401, detail="member session required")
        return auth_store().update_profile(
            request.state.member_id, body.display_name, body.email, body.bio,
            body.avatar_url, body.wallet_address,
        )

    @app.post("/api/admin/member-accounts", status_code=201)
    def provision_member_account(body: MemberAccountInput):
        store = auth_store(create=True)
        store.provision_account(body.member_id, body.password)
        return {"memberId": body.member_id, "configured": True}

    @app.get("/api/demo")
    def demo():
        project, members, tasks, contributions = demo_data()
        scores = score_members(project, members, tasks, contributions)
        return {
            "project": {"id": project.id, "name": project.name},
            "members": [{
                "id": member_id,
                "name": members[member_id].name,
                "totalScore": str(scores[member_id].total_score),
                "contributionShare": str(scores[member_id].contribution_share),
            } for member_id in project.member_ids],
            "tasks": [{
                "id": task.id, "name": task.name,
                "taskValue": str(task.task_value),
            } for task in tasks.values()],
            "contributions": [{
                "id": item.id, "contributorId": item.contributor_id,
                "taskId": item.task_id, "type": item.type.value,
                "status": item.status.value, "description": item.description,
                "score": str(contribution_score(item, project, members, tasks)),
            } for item in contributions],
        }

    @app.get("/api/projects")
    def projects(response: Response, request: Request):
        response.headers["Cache-Control"] = "no-store"
        store = read()
        return [{"id": project.id, "name": project.name} for project in store.projects.values()
                if getattr(request.state, "is_admin", False)
                or request.state.member_id in project.member_ids]

    @app.get("/api/workspace")
    def workspace(request: Request):
        member_id = request.state.member_id
        if member_id is None:
            raise HTTPException(status_code=401, detail="member session required")
        store = read()
        profile_data = auth_store().profile(member_id)
        projects_data = []
        for project in store.projects.values():
            if member_id not in project.member_ids:
                continue
            contributions = [
                item for item in store.contributions.values()
                if item.project_id == project.id
            ]
            token_balance = None
            try:
                token_balance = str(token_read(project.id).balance(member_id))
            except ValueError as error:
                if "unknown token project" not in str(error) and "unknown token ledger" not in str(error):
                    raise
            projects_data.append({
                "id": project.id,
                "name": project.name,
                "role": store.membership_roles[(project.id, member_id)],
                "memberCount": len(project.member_ids),
                "taskCount": len(project.task_ids),
                "contributionCount": len(contributions),
                "pendingCount": sum(item.status == ContributionStatus.PENDING for item in contributions),
                "tokenBalance": token_balance,
            })
        return {
            "profile": profile_data,
            "createdProjects": [item for item in projects_data if item["role"] == "OWNER"],
            "joinedProjects": [item for item in projects_data if item["role"] != "OWNER"],
            "projects": projects_data,
        }

    @app.get("/api/dashboard")
    def dashboard(response: Response, request: Request):
        response.headers["Cache-Control"] = "no-store"
        return project_data("fintech", request)

    @app.get("/api/projects/{project_id}/dashboard")
    def project_dashboard(project_id: str, request: Request):
        return project_data(project_id, request)

    def project_data(project_id: str, request: Request):
        legacy = require_project_member(project_id, request)
        data = legacy.dashboard_data(project_id)
        if token_db_path.is_file() and token_db_path.stat().st_size:
            try:
                token = token_read(project_id)
            except ValueError as error:
                if "unknown token project" not in str(error):
                    raise
                token = None
            if token is not None:
                minted = {event.id for event in token.ledger.events if event.kind.name == "MINT"}
                pending = [
                    item.id for item in legacy.contributions.values()
                    if item.project_id == project_id
                    and item.status.value in ("VERIFIED", "RESOLVED")
                    and contribution_score(item, legacy.projects[project_id],
                                           legacy.members, legacy.tasks) > 0
                    and f"{item.id}:mint" not in minted
                    and f"{item.id}:commission:mint" not in minted
                ]
                frozen_balances = {
                    member: Decimal("0") for member in legacy.projects[project_id].member_ids
                }
                for event in token.ledger.events:
                    if (event.kind.name in {"MINT", "TRANSFER"}
                            and event.sequence in token.ledger._frozen_events
                            and event.destination_id in frozen_balances):
                        frozen_balances[event.destination_id] += event.amount
                pending_mints = {
                    member: Decimal("0") for member in legacy.projects[project_id].member_ids
                }
                for item_id in pending:
                    item = legacy.contributions[item_id]
                    pending_mints[item.contributor_id] += contribution_score(
                        item, legacy.projects[item.project_id], legacy.members, legacy.tasks
                    )
                data["tokenRecognition"] = {
                    "balances": {member: float(value) for member, value in token.balances().items()},
                    "balancesExact": {member: str(value) for member, value in token.balances().items()},
                    "lockedBalancesExact": {member: str(value) for member, value in frozen_balances.items()},
                    "pendingMintsExact": {member: str(value) for member, value in pending_mints.items()},
                    "totalSupply": float(token.total_supply()),
                    "totalSupplyExact": str(token.total_supply()),
                    "pendingContributions": pending,
                    "missingMembers": [member for member in legacy.projects[project_id].member_ids
                                       if member not in token.project.member_ids],
                    "missingTasks": [task for task in legacy.projects[project_id].task_ids
                                     if task not in token.ledger.tasks],
                }
                events_by_id = {event.id: event for event in token.ledger.events}
                pending_ids = set(pending)
                for record in data["contributions"]:
                    item = legacy.contributions[record["id"]]
                    mint_id = (f"{item.id}:commission:mint"
                               if item.type == ContributionType.SUPPORT and item.helped_member_id
                               else f"{item.id}:mint")
                    event = events_by_id.get(mint_id) or events_by_id.get(f"{item.id}:mint")
                    if event:
                        record["tokenEventId"] = event.id
                        record["tokenEventSequence"] = event.sequence
                        holder_id = (f"{item.id}:commission:payment"
                                     if event.id.endswith(":commission:mint")
                                     else f"{item.id}:mint")
                        holder = events_by_id.get(holder_id)
                        record["tokenFrozen"] = bool(
                            holder and holder.sequence in token.ledger._frozen_events)
                    elif item.id in pending_ids:
                        record["tokenPending"] = True
        return data

    @app.get("/api/projects/{project_id}/token-view")
    def token_view(project_id: str, response: Response, request: Request):
        """Read-only stage-1 projection of legacy contributions into the token model."""
        response.headers["Cache-Control"] = "no-store"
        return require_project_member(project_id, request).token_view(project_id)

    # --- Token ledger routes (durable, additive) ---
    # The token store lives in its own SQLite file (token.sqlite3 by default)
    # so the legacy eight tables stay untouched. Read routes return 404 when
    # the ledger database has not been created yet; the write routes create or
    # reuse it.

    def token_read(project_id=None) -> TokenStore:
        if not token_db_path.is_file() or token_db_path.stat().st_size == 0:
            raise ValueError("unknown token ledger; create it via POST /api/token/project "
                             "or migrate with migrate_token_ledger.py")
        return TokenStore(token_db_path, project_id=project_id)

    def token_write(operation, *args, project_id=None):
        try:
            if operation == "create_project":
                store = TokenStore(token_db_path, *args)
                return store.ledger_payload()
            store = (TokenStore(token_db_path, project_id=project_id)
                     if token_db_path.is_file() else None)
            if store is None:
                raise ValueError("unknown token ledger; create it via POST /api/token/project")
            result = getattr(store, operation)(*args)
            return jsonable_encoder(result, custom_encoder={Decimal: str})
        except sqlite3.Error as error:
            raise ValueError(f"token ledger storage error: {error}") from error

    def sync_token_entities(project_id: str):
        """Add legacy members and tasks missing from the matching Token ledger."""
        if not token_db_path.is_file() or token_db_path.stat().st_size == 0:
            return {"members": [], "tasks": []}
        legacy = read()
        project = legacy.projects[project_id]
        try:
            token = token_read(project_id)
        except ValueError as error:
            if "unknown token project" in str(error):
                return {"skipped": "此项目尚未启用 Token 账本", "members": [], "tasks": []}
            raise
        added = {"members": [], "tasks": []}
        for member_id in project.member_ids:
            if member_id not in token.project.member_ids:
                token.add_member(member_id)
                added["members"].append(member_id)
        for task_id in project.task_ids:
            if task_id not in token.ledger.tasks:
                source = legacy.tasks[task_id]
                token.add_task(TokenTask(
                    source.id, project_id, source.name,
                    legacy._token_value_type(
                        [item for item in legacy.contributions.values() if item.project_id == project_id],
                        task_id,
                    ),
                    source.task_value, source.description.strip() or source.name,
                ))
                added["tasks"].append(task_id)
        return added

    @app.post("/api/token/sync")
    def token_sync(request: Request):
        token = require_token_role(request, "OWNER")
        return sync_token_entities(token.project.id)

    @app.post("/api/token/reconcile")
    def token_reconcile(request: Request):
        token = require_token_role(request, "OWNER", "VERIFIER")
        sync = sync_token_entities(token.project.id)
        legacy = read()
        results = []
        for item in legacy.contributions.values():
            if item.project_id != token.project.id:
                continue
            if item.status in (ContributionStatus.VERIFIED, ContributionStatus.RESOLVED):
                current = token_read(token.project.id).ledger
                existing = next((event for event in current.events
                                 if event.id in (f"{item.id}:mint", f"{item.id}:commission:mint")), None)
                if existing is not None:
                    if item.status == ContributionStatus.RESOLVED:
                        holder_event = next((
                            event for event in current.events
                            if event.id in (f"{item.id}:mint", f"{item.id}:commission:payment")
                        ), None)
                        score = contribution_score(item, legacy.projects[item.project_id],
                                                   legacy.members, legacy.tasks)
                        has_correction = any(
                            event.id in (f"{item.id}:adjust-mint", f"{item.id}:refund")
                            for event in current.events
                        ) or any(debt["id"] == item.id for debt in token_read(token.project.id).debts_payload())
                        if ((holder_event and holder_event.sequence in current._frozen_events)
                                or (score != existing.amount and not has_correction)):
                            result = _token_resolve_for_contribution(item.id, "补同步争议结论")
                            results.append({"contributionId": item.id, "result": result})
                    continue
                result = _token_mint_for_contribution(item.id)
                results.append({"contributionId": item.id, "result": result})
            elif item.status == ContributionStatus.DISPUTED:
                result = _token_freeze_for_contribution(item.id, "补同步争议冻结")
                if result and "skipped" not in result:
                    results.append({"contributionId": item.id, "result": result})
        return {"sync": sync, "contributions": results}

    @app.get("/api/token/ledger")
    def token_ledger(response: Response, request: Request):
        response.headers["Cache-Control"] = "no-store"
        return require_token_member(request).ledger_payload()

    @app.get("/api/token/graph")
    def token_graph(response: Response, request: Request):
        response.headers["Cache-Control"] = "no-store"
        return require_token_member(request).graph_payload()

    @app.get("/api/token/contracts")
    def token_contracts(response: Response, request: Request):
        response.headers["Cache-Control"] = "no-store"
        return require_token_member(request).contracts_payload()

    @app.get("/api/token/tasks")
    def token_tasks(response: Response, request: Request):
        response.headers["Cache-Control"] = "no-store"
        return [{
            "id": task.id, "name": task.name, "valueType": task.value_type.value,
            "mintCap": str(task.mint_cap), "acceptanceCriteria": task.acceptance_criteria,
        } for task in require_token_member(request).ledger.tasks.values()]

    @app.get("/api/token/tasks/{task_id}/budget")
    def token_task_budget(task_id: str, response: Response, request: Request):
        response.headers["Cache-Control"] = "no-store"
        return jsonable_encoder(require_token_member(request).task_budget(task_id),
                                custom_encoder={Decimal: str})

    @app.get("/api/token/debts")
    def token_debts(response: Response, request: Request):
        response.headers["Cache-Control"] = "no-store"
        return require_token_member(request).debts_payload()

    @app.post("/api/token/debts/{contribution_id}/collect")
    def token_collect_debt(contribution_id: str, request: Request):
        token = require_token_role(request, "OWNER", "VERIFIER")
        return token_write("collect_debt", contribution_id,
                           project_id=token.project.id)

    @app.post("/api/token/migrate", status_code=201)
    def token_migrate(request: Request, project_id: str):
        """Import one legacy project into the shared, project-scoped token database."""
        require_project_role(project_id, request, "OWNER")
        from migrate_token_ledger import migrate_project
        return migrate_project(db_path, token_db_path, project_id)

    @app.post("/api/token/project", status_code=201)
    def token_create_project(body: TokenProjectInput, request: Request):
        legacy = require_project_role(body.id, request, "OWNER")
        if set(body.member_ids) != set(legacy.projects[body.id].member_ids):
            raise ValueError("Token project members must match project membership")
        if body.id in legacy.projects:
            project = legacy.projects[body.id]
            if any(
                item.project_id == body.id
                and item.status in (ContributionStatus.VERIFIED, ContributionStatus.RESOLVED)
                and contribution_score(item, project, legacy.members, legacy.tasks) > 0
                for item in legacy.contributions.values()
            ):
                raise ValueError("此项目已有已审核贡献，请选择迁移历史贡献建立账本")
        project = TokenProject(body.id, body.name, body.treasury_id, tuple(body.member_ids))
        return token_write("create_project", project)

    @app.post("/api/token/tasks", status_code=201)
    def token_add_task(body: TokenTaskInput, request: Request):
        token = require_token_role(request, "OWNER", "MEMBER")
        task = TokenTask(body.id, token.project.id, body.name, ValueType(body.value_type),
                         body.mint_cap, body.acceptance_criteria)
        return token_write("add_task", task, project_id=token.project.id)

    @app.post("/api/token/tasks/{task_id}/cap")
    def token_set_task_cap(task_id: str, body: TokenCapInput, request: Request):
        token = require_token_role(request, "OWNER")
        return token_write("set_mint_cap", task_id, body.mint_cap,
                           project_id=token.project.id)

    @app.post("/api/token/contracts", status_code=201)
    def token_create_contract(body: CommissionInput, request: Request):
        token = require_token_role(request, "OWNER", "MEMBER")
        if (not getattr(request.state, "is_admin", False)
                and body.principal_id != request.state.member_id):
            raise HTTPException(status_code=403, detail="commission principal must match the signed-in member")
        return token_write("create_commission", body.id, body.task_id, body.principal_id,
                           body.contractor_id, body.contract_price, body.maximum_mint_value,
                           project_id=token.project.id)

    @app.post("/api/token/contracts/{contract_id}/advance")
    def token_advance_contract(contract_id: str, body: ContractAdvanceInput, request: Request):
        token = require_token_role(request, "OWNER", "MEMBER", "VERIFIER")
        contract = token.ledger.contracts.get(contract_id)
        if contract is None:
            raise ValueError(f"unknown contract {contract_id}")
        status = ContractStatus(body.status)
        if not getattr(request.state, "is_admin", False):
            current = request.state.member_id
            if status == ContractStatus.ACCEPTED and current != contract.contractor_id:
                raise HTTPException(status_code=403, detail="only the contractor can accept a commission")
            if status == ContractStatus.CREDIT_RESERVED and current != contract.principal_id:
                raise HTTPException(status_code=403, detail="only the principal can reserve a commission")
            if status == ContractStatus.OFFERED and current != contract.principal_id:
                raise HTTPException(status_code=403, detail="only the principal can offer a commission")
            if status == ContractStatus.DELIVERED and current != contract.contractor_id:
                raise HTTPException(status_code=403, detail="only the contractor can deliver a commission")
            if status == ContractStatus.VERIFIED and current in {
                    contract.principal_id, contract.contractor_id}:
                raise HTTPException(status_code=403, detail="commission parties cannot verify their own contract")
            if status == ContractStatus.DISPUTED and current not in {
                    contract.principal_id, contract.contractor_id} and store_role(
                        token.project.id, current
                    ) not in {"OWNER", "VERIFIER"}:
                raise HTTPException(status_code=403, detail="only a commission party or verifier can raise a dispute")
            if status == ContractStatus.FROZEN and store_role(
                    token.project.id, current
            ) not in {"OWNER", "VERIFIER"}:
                raise HTTPException(status_code=403, detail="a verifier is required for this contract transition")
        if status == ContractStatus.DELIVERED:
            return token_write("deliver_commission", contract_id, body.evidence_hashes,
                               project_id=token.project.id)
        return token_write("advance_contract", contract_id, status, project_id=token.project.id)

    @app.post("/api/token/mint", status_code=201)
    def token_mint(body: MintInput, request: Request):
        token = require_token_role(request, "OWNER", "VERIFIER")
        legacy = read()
        if body.contribution_id:
            item = legacy.contributions.get(body.contribution_id)
            if item is None or item.project_id != token.project.id or item.task_id != body.task_id:
                raise ValueError("贡献 ID 与当前项目任务不匹配")
            if item.status not in (ContributionStatus.VERIFIED, ContributionStatus.RESOLVED):
                raise ValueError("只有已审核或已解决的贡献可以补铸")
            expected = contribution_score(item, legacy.projects[item.project_id],
                                          legacy.members, legacy.tasks)
            expected_event_id = (f"{item.id}:commission:mint"
                                 if item.type == ContributionType.SUPPORT and item.helped_member_id
                                 and legacy._legacy_token_approver(item)
                                 else f"{item.id}:mint")
            if (body.recipient_id != item.contributor_id or body.amount != expected
                    or body.evidence_hashes != [f"legacy:{item.id}"]
                    or body.event_id != expected_event_id):
                raise ValueError("事件 ID、接收成员、数量和证据标识必须与已审核贡献一致")
            result = _token_mint_for_contribution(item.id)
            if result is None or "skipped" in result:
                raise ValueError(result["skipped"] if result else "Token 账本不可用")
            return result
        return token_write("mint_direct", body.event_id, body.task_id, body.recipient_id,
                           body.amount, body.evidence_hashes, project_id=token.project.id)

    @app.post("/api/token/contracts/{contract_id}/settle")
    def token_settle(contract_id: str, body: SettleInput, request: Request):
        token = require_token_role(request, "OWNER", "VERIFIER")
        if (not getattr(request.state, "is_admin", False)
                and request.state.member_id not in body.approver_ids):
            raise HTTPException(status_code=403, detail="the signed-in verifier must be an approver")
        mint, split = token_write("settle_commission", contract_id, body.verified_mint_value,
                                  body.evidence_hashes, body.approver_ids,
                                  project_id=token.project.id)
        return {"mint": mint, "split": split, "transfer": split}

    @app.post("/api/token/transfer", status_code=201)
    def token_transfer(body: TransferInput, request: Request):
        token = require_token_role(request, "OWNER", "MEMBER")
        if (not getattr(request.state, "is_admin", False)
                and body.source_id != request.state.member_id):
            raise HTTPException(status_code=403, detail="transfer source must match the signed-in member")
        return token_write("transfer", body.event_id, body.source_id, body.destination_id,
                           body.amount, body.task_id, body.evidence_hashes,
                           project_id=token.project.id)

    @app.post("/api/token/freeze", status_code=201)
    def token_freeze(body: FreezeInput, request: Request):
        token = require_token_role(request, "OWNER", "VERIFIER")
        return token_write("freeze_events", body.sequences, body.reason, body.tag,
                           project_id=token.project.id)

    @app.post("/api/token/release", status_code=201)
    def token_release(body: ReleaseInput, request: Request):
        token = require_token_role(request, "OWNER", "VERIFIER")
        return token_write("release_events", body.sequences, body.note, body.tag,
                           project_id=token.project.id)

    @app.get("/api/contributions/{contribution_id}")
    def contribution(contribution_id: str, request: Request):
        store, _item = require_contribution_member(contribution_id, request)
        return store.contribution_data(contribution_id)

    @app.post("/api/contributions/{contribution_id}/preview")
    def preview_score(contribution_id: str, body: ScorePreviewInput, request: Request):
        store, _item = require_contribution_member(contribution_id, request)
        return store.preview_score(contribution_id, body.completion, body.support_value, body.quality)

    @app.post("/api/projects", status_code=201)
    def create_project(body: ProjectInput, request: Request):
        owner_id = request.state.member_id
        if getattr(request.state, "is_admin", False) and owner_id is None:
            return write("create_project", body.id, body.name)
        result = write("create_project", body.id, body.name, owner_id)
        token_project = TokenProject(body.id, body.name, f"{body.id}-treasury", (owner_id,))
        result["tokenLedger"] = token_write("create_project", token_project)
        return result

    @app.post("/api/projects/{project_id}/members", status_code=201)
    def add_member(project_id: str, body: MemberInput, request: Request):
        require_project_role(project_id, request, "OWNER")
        result = write("add_member", project_id, body.id, body.name, body.role)
        try:
            result["tokenSync"] = sync_token_entities(project_id)
        except Exception as error:
            result["tokenSync"] = {"skipped": str(error)}
        return result

    @app.get("/api/projects/{project_id}/members")
    def project_members(project_id: str, request: Request):
        store = require_project_member(project_id, request)
        return [{
            "id": member_id,
            "name": store.members[member_id].name,
            "role": store.membership_roles[(project_id, member_id)],
            "hasAccount": bool(auth_store().find_member(member_id)),
        } for member_id in store.projects[project_id].member_ids]

    @app.post("/api/projects/{project_id}/members/invite", status_code=201)
    def invite_registered_member(project_id: str, body: MemberInviteInput, request: Request):
        store = require_project_role(project_id, request, "OWNER")
        account = auth_store().find_member(body.identifier)
        if account is None:
            raise ValueError("only registered accounts can be added by invitation")
        result = write("add_existing_member", project_id, account[0], body.role)
        try:
            result["tokenSync"] = sync_token_entities(project_id)
        except Exception as error:
            result["tokenSync"] = {"skipped": str(error)}
        return result

    @app.patch("/api/projects/{project_id}/members/{member_id}")
    def update_project_member_role(project_id: str, member_id: str,
                                   body: MemberRoleInput, request: Request):
        require_project_role(project_id, request, "OWNER")
        return write("set_member_role", project_id, member_id, body.role)

    @app.post("/api/projects/{project_id}/tasks", status_code=201)
    def add_task(project_id: str, body: TaskInput, request: Request):
        require_project_role(project_id, request, "OWNER", "MEMBER")
        result = write("add_task", project_id, body.id, body.name, body.task_value, body.description)
        try:
            result["tokenSync"] = sync_token_entities(project_id)
        except Exception as error:
            result["tokenSync"] = {"skipped": str(error)}
        return result

    @app.post("/api/projects/{project_id}/contributions", status_code=201)
    def submit_contribution(project_id: str, body: ContributionInput, request: Request):
        require_project_role(project_id, request, "OWNER", "MEMBER", "VERIFIER")
        if (not getattr(request.state, "is_admin", False)
                and body.contributor_id != request.state.member_id):
            raise HTTPException(status_code=403, detail="contributor must match the signed-in member")
        return write("submit_contribution", project_id, body.id, body.contributor_id,
                     body.task_id, body.type, body.description, body.completion,
                     body.support_value, body.helped_member_id)

    @app.post("/api/contributions/{contribution_id}/evidence", status_code=201)
    def add_evidence(contribution_id: str, body: EvidenceInput, request: Request):
        _, item = require_contribution_member(contribution_id, request)
        require_project_role(item.project_id, request, "OWNER", "MEMBER", "VERIFIER")
        if (not getattr(request.state, "is_admin", False)
                and body.submitted_by != request.state.member_id):
            raise HTTPException(status_code=403, detail="evidence submitter must match the signed-in member")
        return write("add_evidence", contribution_id, body.submitted_by, body.kind, body.reference)

    @app.post("/api/contributions/{contribution_id}/reviews")
    def review_contribution(contribution_id: str, body: ReviewInput, request: Request):
        _, item = require_contribution_member(contribution_id, request)
        require_project_role(item.project_id, request, "OWNER", "VERIFIER")
        if (not getattr(request.state, "is_admin", False)
                and body.reviewer_id != request.state.member_id):
            raise HTTPException(status_code=403, detail="reviewer must match the signed-in member")
        if token_db_path.is_file() and token_db_path.stat().st_size:
            legacy = read()
            item = legacy.contributions[contribution_id]
            try:
                token = token_read(item.project_id)
            except (ValueError, sqlite3.Error):
                token = None  # The committed legacy review reports a skipped token hook below.
            if token is not None and token.project.id == item.project_id and body.decision in (
                VerificationDecision.CONFIRM, VerificationDecision.ADJUST
            ):
                sync_token_entities(item.project_id)
                token = token_read(item.project_id)
                if (item.type == ContributionType.SUPPORT and item.helped_member_id
                        and body.reviewer_id in (item.contributor_id, item.helped_member_id)):
                    raise ValueError("SUPPORT 的 Token 合约必须由贡献者和受帮助成员以外的成员审核")
                proposed = replace(
                    item, status=ContributionStatus.VERIFIED,
                    **legacy._score_changes(body.completion, body.support_value, body.quality),
                )
                amount = contribution_score(proposed, legacy.projects[item.project_id],
                                            legacy.members, legacy.tasks)
                if amount > token.task_budget(item.task_id)["available"]:
                    raise ValueError("任务铸币上限不足；请先在 Token 工作台提高上限")
        result = write("review_contribution", contribution_id, body.reviewer_id, body.decision,
                       body.note, body.completion, body.support_value, body.quality)
        # CONFIRM and ADJUST both move a PENDING contribution to VERIFIED, so
        # both must mint; DISPUTE freezes any tokens the contribution already
        # minted. Every outcome is best-effort and never changes the legacy
        # review result that was already committed above.
        if body.decision in (VerificationDecision.CONFIRM, VerificationDecision.ADJUST):
            minted = _token_mint_for_contribution(contribution_id)
            if minted is not None:
                result["tokenMint"] = minted
        elif body.decision == VerificationDecision.DISPUTE:
            frozen = _token_freeze_for_contribution(contribution_id, body.note)
            if frozen is not None:
                result["tokenFrozen"] = frozen
        return result

    @app.post("/api/contributions/{contribution_id}/resolve")
    def resolve_dispute(contribution_id: str, body: ResolutionInput, request: Request):
        _, item = require_contribution_member(contribution_id, request)
        require_project_role(item.project_id, request, "OWNER", "VERIFIER")
        if (not getattr(request.state, "is_admin", False)
                and body.resolved_by != request.state.member_id):
            raise HTTPException(status_code=403, detail="resolver must match the signed-in member")
        result = write("resolve_dispute", contribution_id, body.resolved_by, body.resolution,
                       body.completion, body.support_value, body.quality)
        # Dispute resolution restores frozen tokens first, then corrects the
        # released amount to the dispute's final score. When the final score
        # equals the frozen amount this is exactly "release"; when it differs
        # the delta is minted (higher) or paid back to the treasury (lower).
        # All best-effort: failures are reported, never thrown, and the
        # already-committed legacy resolution is never affected.
        token_result = _token_resolve_for_contribution(contribution_id, body.resolution)
        if token_result is not None:
            result["tokenResolved"] = token_result
        return result

    def _legacy_score(contribution_id):
        legacy = read()
        item = legacy.contributions[contribution_id]
        project = legacy.projects[item.project_id]
        return item, contribution_score(item, project, legacy.members, legacy.tasks)

    def _token_mint_for_contribution(contribution_id: str):
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
            store = _open_token_store(item.project_id)
            independent_approver = (read()._legacy_token_approver(item)
                                    if item.type == ContributionType.SUPPORT and item.helped_member_id
                                    else None)
            if independent_approver:
                contract_id = f"{item.id}:commission"
                if contract_id in store.ledger.contracts:
                    return {"skipped": "委托合约已存在（此前已铸币或已结算）"}
                mint, transfer = store.settle_legacy_commission(
                    contract_id, item.task_id, item.helped_member_id,
                    item.contributor_id, amount, key, [independent_approver],
                )
                return {"kind": "COMMISSION", "contractId": contract_id,
                        "mintEventId": mint.id, "transferEventId": transfer.id,
                        "amount": float(amount)}
            mint_event_id = f"{item.id}:mint"
            if any(event.id == mint_event_id for event in store.ledger.events):
                return {"skipped": "直接铸币已存在（此前已铸币）"}
            event = store.mint_direct(mint_event_id, item.task_id, item.contributor_id,
                                      amount, key)
            return {"kind": "DIRECT", "eventId": event.id, "amount": float(amount)}
        except ValueError as error:
            if "task mint cap exceeded" in str(error):
                return {"code": "cap_exceeded",
                        "skipped": "任务铸币上限不足；请在 Token 工作台提高上限后补同步"}
            return {"code": "validation_failed", "skipped": token_issue(error)}
        except Exception as error:
            # Any ledger failure (engine rejection, sqlite, disk, schema drift)
            # must never surface as an error after the legacy write already
            # committed; the dashboard behaves exactly as before fusion.
            return {"code": "storage_failed", "skipped": "Token 账本写入失败；请稍后补同步"}

    def _frozen_legacy_mints(contribution_id: str):
        """Sequences whose current holder received this contribution's value."""
        item, _ = _legacy_score(contribution_id)
        store = _open_token_store(item.project_id)
        frozen = store.ledger._frozen_events
        return [
            event.sequence for event in store.ledger.events
            if (event.id == f"{contribution_id}:mint"
                or event.id == f"{contribution_id}:commission:payment")
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
            item, _ = _legacy_score(contribution_id)
            store = _open_token_store(item.project_id)
            events = store.freeze_events(sequences, reason.strip() or "争议冻结",
                                         tag=contribution_id)
            return {"kind": "FREEZE", "eventIds": [event.id for event in events],
                    "sequences": [event.sequence for event in events]}
        except Exception as error:
            return {"skipped": token_issue(error)}

    def _open_token_store(project_id):
        """Open the ledger, converting storage failures into skipped markers."""
        try:
            return TokenStore(token_db_path, project_id=project_id)
        except sqlite3.Error as error:
            raise ValueError(f"token ledger storage error: {error}") from error

    def _token_release_for_contribution(contribution_id: str, note: str):
        """Release frozen tokens; returns None when nothing is frozen."""
        if not token_db_path.is_file():
            return None
        try:
            item, _ = _legacy_score(contribution_id)
            store = _open_token_store(item.project_id)
            sequences = [
                event.sequence for event in store.ledger.events
                if (event.id == f"{contribution_id}:mint"
                     or event.id == f"{contribution_id}:commission:payment")
                and event.sequence in store.ledger._frozen_events
            ]
            if not sequences:
                return None
            events = store.release_events(sequences, note.strip() or "争议已解决",
                                          tag=contribution_id)
            return {"kind": "RELEASE", "eventIds": [event.id for event in events],
                    "sequences": [event.sequence for event in events]}
        except Exception as error:
            return {"skipped": token_issue(error)}

    def _token_resolve_for_contribution(contribution_id: str, note: str):
        """Reconcile the token ledger after a dispute resolves.

        Releases any tokens frozen during the dispute, then corrects the
        released amount to the dispute's final score: mints the difference
        when the final score is higher, or refunds the difference back to
        the treasury when it is lower. When there is nothing frozen (the
        contribution was disputed before minting), falls back to a normal
        mint for the final score.
        """
        if not token_db_path.is_file():
            return None
        try:
            item, final_amount = _legacy_score(contribution_id)
            released = _token_release_for_contribution(contribution_id, note)
            if released and "skipped" in released:
                return {"code": "release_failed", "skipped": released["skipped"]}
            store = _open_token_store(item.project_id)
            mints = [
                event for event in store.ledger.events
                if event.kind.name == "MINT"
                and (event.id == f"{contribution_id}:mint"
                     or event.contract_id == f"{contribution_id}:commission")
            ]
            frozen_amount = sum((event.amount for event in mints), Decimal("0"))
            if not mints:
                # Disputed before any mint happened: resolve mints the final score.
                minted = _token_mint_for_contribution(contribution_id)
                if minted is not None and "skipped" not in minted:
                    return {"released": released, "minted": minted,
                            "finalAmount": float(final_amount)}
                return {"code": "mint_failed",
                        "skipped": minted["skipped"] if minted else "Token 账本未启用"}
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
                event, remaining = store.reconcile_refund(
                    contribution_id, item.contributor_id, item.task_id, -delta,
                    [f"legacy:{item.id}:resolve:{note.strip() or 'resolved'}"],
                )
                correction = {"kind": "REFUND", "eventId": event.id if event else None,
                              "destinationId": store.project.treasury_id,
                              "amount": float(-delta - remaining),
                              "debtExact": str(remaining)}
            return {"released": released, "correction": correction,
                    "finalAmount": float(final_amount)}
        except Exception as error:
            return {"skipped": token_issue(error)}

    app.mount("/", StaticFiles(directory=ROOT, html=True), name="dashboard")
    return app


app = create_app()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--token-db", type=Path, default=DEFAULT_TOKEN_DB,
                        help="durable token ledger database (created on first use)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()
    if args.db == DEFAULT_DB and not args.db.is_file():
        parser.error(f"database not found: {args.db}; import data.json with import_json.py first")
    print(f"SQLite database: {args.db.resolve()}", flush=True)
    print(f"Token ledger database: {args.token_db.resolve()}", flush=True)
    print(f"Admin account provisioning and Token writes: "
          f"{'enabled' if os.environ.get('TOKEN_ADMIN_KEY') else 'disabled; set TOKEN_ADMIN_KEY'}",
          flush=True)
    host = "0.0.0.0" if os.environ.get("POCKETBAY_DATA_DIR") else "127.0.0.1"
    uvicorn.run(create_app(args.db, args.token_db), host=host, port=args.port)
