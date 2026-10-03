"""FastAPI service for the dashboard and contribution workflow."""

import argparse
import asyncio
import fcntl
import hmac
import hashlib
import json
import os
import secrets
import sqlite3
import time
from urllib.parse import urlsplit
from contextvars import ContextVar
from uuid import uuid4
from dataclasses import asdict, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from contribution_engine import (
    ContributionStatus,
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
DATA_DIR = Path(os.environ.get("POCKETBAY_DATA_DIR", Path(__file__).parent))
DEFAULT_DB = DATA_DIR / "data.sqlite3"
DEFAULT_TOKEN_DB = DATA_DIR / "token.sqlite3"

def _is_withdrawn(db_path, contribution_id):
    with sqlite3.connect(db_path) as conn:
        return bool(conn.execute("SELECT 1 FROM contribution_withdrawals WHERE contribution_id=?", (contribution_id,)).fetchone())


def cookie_is_secure(request: Request) -> bool:
    """Use secure cookies for deployments even when TLS ends at a proxy."""
    configured = os.environ.get("POCKETBAY_COOKIE_SECURE")
    if configured is not None:
        return configured.strip().lower() in {"1", "true", "yes", "on"}
    # POCKETBAY_DATA_DIR is set by PocketBay deployments. Only trust the
    # forwarded scheme when the operator explicitly configures a trusted proxy.
    if os.environ.get("POCKETBAY_DATA_DIR"):
        if os.environ.get("POCKETBAY_TRUST_PROXY", "").lower() in {"1", "true", "yes"}:
            forwarded = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
            if forwarded in {"http", "https"}:
                return forwarded == "https"
        return True
    return request.url.scheme == "https"


def valid_password(password: str) -> bool:
    return (len(password) >= 8 and any(char.islower() for char in password)
            and any(char.isupper() for char in password)
            and any(char.isdigit() for char in password))


def request_origin_matches(request: Request, origin: str | None) -> bool:
    try:
        scheme = request.url.scheme.lower()
        host = request.headers.get("host", "").split(",", 1)[0].strip()
        # PocketBay terminates TLS before forwarding to the local app. Trust
        # its forwarded host/scheme only inside the managed deployment.
        if os.environ.get("POCKETBAY_DATA_DIR"):
            host = request.headers.get("x-forwarded-host", host).split(",", 1)[0].strip()
            forwarded_scheme = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
            scheme = forwarded_scheme if forwarded_scheme in {"http", "https"} else scheme
        expected = urlsplit(f"{scheme}://{host}")
        if (not os.environ.get("POCKETBAY_DATA_DIR")
                and expected.hostname in {"localhost", "127.0.0.1", "::1"}
                and request.headers.get("sec-fetch-site") == "same-origin"):
            # Chrome supplies this browser-controlled marker for same-origin
            # requests even when Origin is omitted or rewritten locally.
            return True
        if not origin:
            return False
        supplied = urlsplit(origin)
        same_host = supplied.netloc.lower() == expected.netloc.lower()
        if not same_host and not os.environ.get("POCKETBAY_DATA_DIR"):
            local_names = {"localhost", "127.0.0.1", "::1"}
            same_host = (supplied.hostname in local_names and expected.hostname in local_names
                         and supplied.port == expected.port)
        return (supplied.scheme.lower() == expected.scheme and same_host and
                not supplied.username and not supplied.password and
                supplied.path in ("", "/") and not supplied.query and not supplied.fragment)
    except ValueError:
        return False


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

class LifecycleReasonInput(BaseModel):
    reason: str

class UnwindDecisionInput(BaseModel):
    decision: str
    note: str = ""


class MemberInput(BaseModel):
    id: str
    name: str


class SiteAdminInput(BaseModel):
    member_id: str
    password: str


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


class ContractApprovalInput(BaseModel):
    note: str = ""


class ContractDisputeInput(BaseModel):
    reason: str


class ContractResolutionInput(BaseModel):
    outcome: str
    note: str
    refund_amount: Decimal | None = None


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
    approver_ids: list[str] = []


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


def create_app(db_path=DEFAULT_DB, token_db_path=None):
    app = FastAPI(title="Contribution Graph API")
    db_path = Path(db_path)
    app.state.db_path = str(db_path)
    token_db_path = Path(token_db_path) if token_db_path else DEFAULT_TOKEN_DB
    token_project_context = ContextVar("token_project_id", default=None)
    # Identity tables are additive; business tables and data remain untouched.
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if os.environ.get("POCKETBAY_DATA_DIR") and db_path == DEFAULT_DB and not db_path.exists():
        from import_json import import_json
        import_json(Path(__file__).with_name("data.json"), db_path)
    with sqlite3.connect(db_path) as auth_conn:
        auth_conn.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
        auth_conn.executescript(Path(__file__).with_name("auth_schema.sql").read_text(encoding="utf-8"))
        # Additive, repeatable lifecycle schema. Historical project/member rows remain intact.
        auth_conn.executescript(Path(__file__).with_name("lifecycle_schema.sql").read_text(encoding="utf-8"))
        columns={row[1] for row in auth_conn.execute("PRAGMA table_info(project_lifecycle)")}
        if "token_setup_state" not in columns:
            auth_conn.execute("ALTER TABLE project_lifecycle ADD COLUMN token_setup_state TEXT NOT NULL DEFAULT 'TOKEN_SETUP_PENDING'")
        exit_columns={row[1] for row in auth_conn.execute("PRAGMA table_info(membership_exit_requests)")}
        if "contribution_ids_snapshot" not in exit_columns:
            auth_conn.execute("ALTER TABLE membership_exit_requests ADD COLUMN contribution_ids_snapshot TEXT NOT NULL DEFAULT '[]'")
        if "decision_note" not in exit_columns:
            auth_conn.execute("ALTER TABLE membership_exit_requests ADD COLUMN decision_note TEXT NOT NULL DEFAULT ''")
        if auth_conn.execute("PRAGMA user_version").fetchone()[0] < 1:
            auth_conn.execute("PRAGMA user_version = 1")
        seed_path = Path(os.environ.get("POCKETBAY_PRIVATE_DIR", Path(__file__).parent / "private")) / "hacku-auth-seed.json"
        if seed_path.is_file() and not auth_conn.execute("SELECT 1 FROM auth_accounts WHERE is_site_admin=1 LIMIT 1").fetchone():
            seed = json.loads(seed_path.read_text(encoding="utf-8"))
            member_id = str(seed["member_id"]).strip()
            if member_id:
                auth_conn.execute("INSERT OR IGNORE INTO members(id,name) VALUES(?,?)", (member_id, member_id))
                auth_conn.execute("INSERT INTO auth_accounts(member_id,salt,password_hash,is_site_admin) VALUES(?,?,?,1) "
                                  "ON CONFLICT(member_id) DO UPDATE SET salt=excluded.salt, password_hash=excluded.password_hash, is_site_admin=1",
                                  (member_id, bytes.fromhex(seed["salt"]), bytes.fromhex(seed["password_hash"])))

    def auth_session(request):
        token = request.cookies.get("hacku_session", "")
        if not token:
            return None
        digest = hashlib.sha256(token.encode()).digest()
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT s.member_id, s.csrf_hash, a.is_site_admin FROM auth_sessions s JOIN auth_accounts a USING(member_id) WHERE s.token_hash=? AND s.expires_at>?", (digest, int(time.time()))).fetchone()
        return {"member_id": row[0], "csrf_hash": row[1], "site_admin": bool(row[2])} if row else None
    @app.middleware("http")
    async def protect_token_writes(request: Request, call_next):
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
        protected = (request.method in ("POST", "PATCH", "DELETE")
                     and request.url.path.startswith("/api/")
                     and not request.url.path.endswith("/preview"))
        path_parts=request.url.path.strip("/").split("/")
        scoped_token = False
        project_id = None
        if protected:
            if request.url.path not in ("/api/auth/login", "/api/auth/accept-invite"):
                session = auth_session(request)
                if not session:
                    return JSONResponse(status_code=401, content={"detail": "login required"})
                origin = request.headers.get("origin")
                if not request_origin_matches(request, origin):
                    return JSONResponse(status_code=403, content={"detail": "same-origin request required"})
                csrf = request.headers.get("x-csrf-token", "")
                if not csrf or not hmac.compare_digest(hashlib.sha256(csrf.encode()).digest(), session["csrf_hash"]):
                    return JSONResponse(status_code=403, content={"detail": "invalid CSRF token"})
                if len(path_parts) < 2 or path_parts[0] != "api":
                    return JSONResponse(status_code=404, content={"detail": "not found"})
                body_data = {}
                try: body_data = json.loads(await request.body())
                except (ValueError, TypeError): pass
                project_id = body_data.get("project_id")
                if len(path_parts) > 2 and path_parts[1] == "projects": project_id = path_parts[2]
                scoped_token = len(path_parts) > 3 and path_parts[1] == "projects" and path_parts[3] == "token"
                if scoped_token: project_id=path_parts[2]
                if len(path_parts)>2 and path_parts[1]=="contributions":
                    with sqlite3.connect(db_path) as conn:
                        row=conn.execute("SELECT project_id FROM contributions WHERE id=?",(path_parts[2],)).fetchone()
                    project_id=row[0] if row else None
                is_contribution_write = path_parts[1] == "contributions" or (path_parts[1] == "projects" and "contributions" in path_parts)
                # Archived projects and exited members cannot mutate project data,
                # even through legacy token aliases.
                if project_id and path_parts[1] != "auth":
                    with sqlite3.connect(db_path) as conn:
                        lifecycle = conn.execute("SELECT state FROM project_lifecycle WHERE project_id=?", (project_id,)).fetchone()
                        if lifecycle and lifecycle[0] != "ACTIVE" and not request.url.path.endswith(("/restore","/archive")):
                            return JSONResponse(status_code=410, content={"detail":"project is archived"})
                        active_member = conn.execute("SELECT state FROM project_membership_state WHERE project_id=? AND member_id=?", (project_id, session["member_id"])).fetchone()
                        if (not session["site_admin"] or is_contribution_write) and active_member and active_member[0] != "ACTIVE" and request.url.path not in (
                            f"/api/projects/{project_id}/members/me/exit-requests/cancel",
                        ) and "/decision" not in request.url.path:
                            return JSONResponse(status_code=403, content={"detail":"project membership is not active"})
                if path_parts[1] == "token":
                    if len(path_parts) > 2 and path_parts[2] == "project" and not session["site_admin"]:
                        return JSONResponse(status_code=403, content={"detail":"site administrator required"})
                    with sqlite3.connect(db_path) as conn:
                        original=conn.execute("SELECT project_id FROM token_ledger_migrations ORDER BY migrated_at LIMIT 1").fetchone()
                    # Legacy token aliases operate on the active ledger. Never
                    # authorize them using a project_id supplied in the body.
                    project_id = original[0] if original else None
                    active_path = active_token_path()
                    if not project_id and active_path.is_file():
                        try:
                            with sqlite3.connect(active_path) as conn:
                                row = conn.execute("SELECT id FROM token_projects LIMIT 1").fetchone()
                            project_id = row[0] if row else None
                        except sqlite3.Error:
                            pass
                    if not project_id and len(path_parts) > 2 and path_parts[2] == "migrate":
                        project_id = request.query_params.get("project_id")
                if project_id:
                    with sqlite3.connect(db_path) as conn:
                        lifecycle=conn.execute("SELECT state FROM project_lifecycle WHERE project_id=?",(project_id,)).fetchone()
                        membership=conn.execute("SELECT state FROM project_membership_state WHERE project_id=? AND member_id=?",(project_id,session["member_id"])).fetchone()
                    if lifecycle and lifecycle[0]!="ACTIVE" and not request.url.path.endswith(("/restore","/archive")):
                        return JSONResponse(status_code=410,content={"detail":"project is archived"})
                    if (not session["site_admin"] or is_contribution_write) and membership and membership[0]!="ACTIVE" and not request.url.path.endswith("/cancel") and not request.url.path.endswith("/decision"):
                        return JSONResponse(status_code=403,content={"detail":"project membership is not active"})
                if request.url.path == "/api/projects" and not session["site_admin"]:
                    return JSONResponse(status_code=403, content={"detail":"site administrator required"})
                if project_id and not is_contribution_write:
                    with sqlite3.connect(db_path) as conn:
                        allowed = session["site_admin"] or conn.execute("SELECT 1 FROM auth_project_admins WHERE project_id=? AND member_id=?", (project_id,session["member_id"])).fetchone()
                        if not allowed and (request.url.path.endswith("/decision") or "/members/me/exit-requests" in request.url.path):
                            allowed = conn.execute("SELECT 1 FROM project_membership_state WHERE project_id=? AND member_id=? AND state IN ('ACTIVE','EXIT_REQUESTED')", (project_id,session["member_id"])).fetchone()
                    if not allowed and request.url.path.endswith("/approve"):
                        try:
                            with sqlite3.connect(project_token_path(project_id) if scoped_token else token_db_path) as conn:
                                members = conn.execute("SELECT member_ids FROM token_projects WHERE id=?", (project_id,)).fetchone()
                            allowed = members and session["member_id"] in json.loads(members[0])
                        except (sqlite3.Error, ValueError, TypeError):
                            allowed = False
                    if not allowed and request.url.path.endswith("/dispute"):
                        try:
                            with sqlite3.connect(project_token_path(project_id) if scoped_token else token_db_path) as conn:
                                row = conn.execute("SELECT principal_id,contractor_id FROM commission_contracts WHERE id=?", (path_parts[3],)).fetchone()
                            allowed = row and session["member_id"] in row[:2]
                        except (sqlite3.Error, IndexError):
                            allowed = False
                    if not allowed:
                        return JSONResponse(status_code=403, content={"detail":"project administrator required"})
        scoped = token_project_context.set(project_id if scoped_token else None) if protected else None
        write_lock = bool(protected and project_id)
        lock_file = None
        try:
            if write_lock:
                lock_dir=db_path.parent / "project-locks"
                lock_dir.mkdir(parents=True,exist_ok=True)
                lock_file=(lock_dir / (hashlib.sha256(project_id.encode("utf-8")).hexdigest()+".lock")).open("a+b")
                await asyncio.to_thread(fcntl.flock,lock_file.fileno(),fcntl.LOCK_EX)
                with sqlite3.connect(db_path) as conn:
                    current=conn.execute("SELECT state FROM project_lifecycle WHERE project_id=?",(project_id,)).fetchone()
                    member=conn.execute("SELECT state FROM project_membership_state WHERE project_id=? AND member_id=?",(project_id,session["member_id"])).fetchone()
                if current and current[0]!="ACTIVE" and not request.url.path.endswith(("/restore","/archive")):
                    return JSONResponse(status_code=410,content={"detail":"project is archived"})
                if (not session["site_admin"] or is_contribution_write) and member and member[0]!="ACTIVE" and not request.url.path.endswith(("/cancel","/decision")):
                    return JSONResponse(status_code=403,content={"detail":"project membership is not active"})
            response=await call_next(request)
            if (protected and response.status_code < 400 and request.method in ("POST","PATCH","DELETE")
                    and not request.url.path.endswith(("/archive","/restore"))):
                changed_project=project_id
                if not changed_project and len(path_parts)>2 and path_parts[1]=="contributions":
                    with sqlite3.connect(db_path) as conn:
                        row=conn.execute("SELECT project_id FROM contributions WHERE id=?",(path_parts[2],)).fetchone()
                    changed_project=row[0] if row else None
                if changed_project:
                    with sqlite3.connect(db_path) as conn:
                        conn.execute("UPDATE project_versions SET version=version+1 WHERE project_id=?",(changed_project,))
                        conn.execute("UPDATE project_lifecycle SET version=version+1 WHERE project_id=?",(changed_project,))
            return response
        finally:
            if lock_file:
                fcntl.flock(lock_file.fileno(),fcntl.LOCK_UN)
                lock_file.close()
            if scoped is not None: token_project_context.reset(scoped)

    @app.get("/api/auth/me")
    def auth_me(request: Request, response: Response):
        response.headers["Cache-Control"] = "no-store"
        session = auth_session(request)
        if not session:
            return {"authenticated": False}
        with sqlite3.connect(db_path) as conn:
            projects = conn.execute("SELECT pm.project_id, p.name, EXISTS(SELECT 1 FROM auth_project_admins pa WHERE pa.project_id=pm.project_id AND pa.member_id=pm.member_id) FROM project_members pm JOIN projects p ON p.id=pm.project_id LEFT JOIN project_lifecycle l ON l.project_id=p.id LEFT JOIN project_membership_state ms ON ms.project_id=pm.project_id AND ms.member_id=pm.member_id WHERE pm.member_id=? AND COALESCE(l.state,'ACTIVE')='ACTIVE' AND COALESCE(ms.state,'ACTIVE')='ACTIVE'", (session["member_id"],)).fetchall()
        return {"authenticated": True, "memberId": session["member_id"], "siteAdmin": session["site_admin"], "projects": [{"id":p[0],"name":p[1],"admin":bool(p[2])} for p in projects], "csrf": request.cookies.get("hacku_csrf", "")}

    @app.post("/api/auth/login")
    async def auth_login(request: Request, response: Response):
        origin = request.headers.get("origin")
        if not request_origin_matches(request, origin):
            return JSONResponse(status_code=403, content={"detail":"same-origin request required"})
        body = await request.json()
        member_id, password = str(body.get("member_id", "")), str(body.get("password", ""))
        if len(member_id) > 256 or len(password) > 1024:
            return JSONResponse(status_code=401, content={"detail":"invalid member ID or password"})
        address = request.client.host if request.client else "unknown"
        attempt_key = hashlib.sha256(f"{member_id}\0{address}".encode()).hexdigest()
        now = int(time.time())
        with sqlite3.connect(db_path) as conn:
            conn.execute("DELETE FROM auth_login_attempts WHERE window_start<?", (now-900,))
            attempt = conn.execute("SELECT failures,window_start FROM auth_login_attempts WHERE attempt_key=?",(attempt_key,)).fetchone()
            if attempt and attempt[0] >= 5 and now-attempt[1] < 900:
                return JSONResponse(status_code=429, content={"detail":"invalid member ID or password"})
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT salt,password_hash FROM auth_accounts WHERE member_id=?", (member_id,)).fetchone()
        valid = False
        if row:
            try: valid = hmac.compare_digest(hashlib.scrypt(password.encode(), salt=row[0], n=2**14, r=8, p=1, dklen=32), row[1])
            except ValueError: pass
        if not valid:
            with sqlite3.connect(db_path) as conn:
                conn.execute("INSERT INTO auth_login_attempts VALUES(?,?,?) ON CONFLICT(attempt_key) DO UPDATE SET failures=auth_login_attempts.failures+1",(attempt_key,1,now))
            return JSONResponse(status_code=401, content={"detail":"invalid member ID or password"})
        with sqlite3.connect(db_path) as conn: conn.execute("DELETE FROM auth_login_attempts WHERE attempt_key=?",(attempt_key,))
        raw, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with sqlite3.connect(db_path) as conn:
            conn.execute("INSERT INTO auth_sessions VALUES(?,?,?,?)", (hashlib.sha256(raw.encode()).digest(), member_id, hashlib.sha256(csrf.encode()).digest(), int(time.time())+43200))
        secure = cookie_is_secure(request)
        response.set_cookie("hacku_session", raw, httponly=True, secure=secure, samesite="lax", max_age=43200, path="/")
        response.set_cookie("hacku_csrf", csrf, httponly=False, secure=secure, samesite="lax", max_age=43200, path="/")
        return {"authenticated": True, "memberId": member_id}

    @app.post("/api/auth/logout")
    def auth_logout(request: Request, response: Response):
        raw=request.cookies.get("hacku_session", "")
        if raw:
            with sqlite3.connect(db_path) as conn: conn.execute("DELETE FROM auth_sessions WHERE token_hash=?", (hashlib.sha256(raw.encode()).digest(),))
        response.delete_cookie("hacku_session", path="/"); response.delete_cookie("hacku_csrf", path="/")
        return {"authenticated": False}

    @app.post("/api/admin/site-admins", status_code=201)
    def add_site_admin(body: SiteAdminInput, request: Request):
        session = auth_session(request)
        if not session or not session["site_admin"]:
            return JSONResponse(status_code=403, content={"detail": "site administrator required"})
        member_id = body.member_id.strip()
        if not member_id or len(member_id) > 128:
            return JSONResponse(status_code=400, content={"detail": "member ID is required"})
        if not valid_password(body.password):
            return JSONResponse(status_code=400, content={"detail": "password must be at least 8 characters and include uppercase, lowercase, and a number"})
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(body.password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("INSERT OR IGNORE INTO members(id,name) VALUES(?,?)", (member_id, member_id))
            try:
                conn.execute("INSERT INTO auth_accounts(member_id,salt,password_hash,is_site_admin) VALUES(?,?,?,1)", (member_id, salt, digest))
            except sqlite3.IntegrityError:
                return JSONResponse(status_code=409, content={"detail": "account already exists"})
        return {"memberId": member_id, "siteAdmin": True}

    @app.post("/api/projects/{project_id}/invites")
    async def create_invite(project_id: str, request: Request):
        body = await request.json(); member_id = str(body.get("member_id", ""))
        raw = secrets.token_urlsafe(32); digest = hashlib.sha256(raw.encode()).digest(); now = int(time.time())
        with sqlite3.connect(db_path) as conn:
            if not conn.execute("SELECT 1 FROM project_members WHERE project_id=? AND member_id=?", (project_id,member_id)).fetchone():
                return JSONResponse(status_code=404, content={"detail":"member is not in this project"})
            if conn.execute("SELECT 1 FROM auth_accounts WHERE member_id=?", (member_id,)).fetchone():
                return JSONResponse(status_code=409, content={"detail":"member already has an account"})
            conn.execute("DELETE FROM auth_invites WHERE project_id=? AND member_id=? AND used_at IS NULL", (project_id,member_id))
            conn.execute("INSERT INTO auth_invites VALUES(?,?,?,?,NULL)", (digest,project_id,member_id,now+172800))
        return {"memberId":member_id,"expiresAt":now+172800,"inviteUrl":str(request.base_url).rstrip("/")+"/accept-invite.html#"+raw}

    @app.get("/api/projects/{project_id}/admins")
    def list_project_admins(project_id: str, request: Request):
        session = auth_session(request)
        if not session:
            return JSONResponse(status_code=401, content={"detail": "login required"})
        with sqlite3.connect(db_path) as conn:
            if not session["site_admin"] and not conn.execute("SELECT 1 FROM project_members WHERE project_id=? AND member_id=?", (project_id, session["member_id"])).fetchone():
                return JSONResponse(status_code=403, content={"detail": "project membership required"})
            members = [row[0] for row in conn.execute("SELECT member_id FROM auth_project_admins WHERE project_id=? ORDER BY member_id", (project_id,))]
        return {"projectId": project_id, "memberIds": members}

    @app.post("/api/projects/{project_id}/admins")
    async def appoint_project_admin(project_id: str, request: Request):
        session=auth_session(request); body=await request.json(); member_id=str(body.get("member_id", ""))
        if not session or not session["site_admin"]: return JSONResponse(status_code=403,content={"detail":"site administrator required"})
        with sqlite3.connect(db_path) as conn:
            if not conn.execute("SELECT 1 FROM auth_accounts WHERE member_id=?",(member_id,)).fetchone(): return JSONResponse(status_code=404,content={"detail":"member must have an account"})
            try: conn.execute("INSERT INTO auth_project_admins(project_id,member_id) VALUES(?,?)",(project_id,member_id))
            except sqlite3.IntegrityError: return JSONResponse(status_code=404,content={"detail":"member is not in this project"})
        return {"projectId":project_id,"memberId":member_id,"admin":True}

    @app.post("/api/auth/accept-invite")
    async def accept_invite(request: Request, response: Response):
        origin=request.headers.get("origin")
        if not request_origin_matches(request, origin):
            return JSONResponse(status_code=403, content={"detail":"same-origin request required"})
        body=await request.json(); raw=str(body.get("invite", "")); password=str(body.get("password", ""))
        now=int(time.time())
        address = request.client.host if request.client else "unknown"
        attempt_key = "invite:" + hashlib.sha256(address.encode()).hexdigest()
        with sqlite3.connect(db_path) as conn:
            conn.execute("DELETE FROM auth_login_attempts WHERE window_start<?", (now-900,))
            attempt = conn.execute("SELECT failures,window_start FROM auth_login_attempts WHERE attempt_key=?", (attempt_key,)).fetchone()
            if attempt and attempt[0] >= 10 and now-attempt[1] < 900:
                return JSONResponse(status_code=429, content={"detail":"invite is invalid or expired"})
        if not valid_password(password):
            with sqlite3.connect(db_path) as conn:
                conn.execute("INSERT INTO auth_login_attempts VALUES(?,?,?) ON CONFLICT(attempt_key) DO UPDATE SET failures=auth_login_attempts.failures+1", (attempt_key,1,now))
            return JSONResponse(status_code=400, content={"detail":"password must be at least 8 characters and include uppercase, lowercase, and a number"})
        digest=hashlib.sha256(raw.encode()).digest(); salt=secrets.token_bytes(16)
        pwd=hashlib.scrypt(password.encode(), salt=salt,n=2**14,r=8,p=1,dklen=32)
        with sqlite3.connect(db_path) as conn:
            invite=conn.execute("SELECT project_id,member_id FROM auth_invites WHERE token_hash=? AND used_at IS NULL AND expires_at>?",(digest,now)).fetchone()
            if not invite:
                conn.execute("INSERT INTO auth_login_attempts VALUES(?,?,?) ON CONFLICT(attempt_key) DO UPDATE SET failures=auth_login_attempts.failures+1", (attempt_key,1,now))
                return JSONResponse(status_code=400, content={"detail":"invite is invalid or expired"})
            try:
                conn.execute("INSERT INTO auth_accounts(member_id,salt,password_hash) VALUES(?,?,?)", (invite[1],salt,pwd))
                conn.execute("UPDATE auth_invites SET used_at=? WHERE token_hash=? AND used_at IS NULL",(now,digest))
            except sqlite3.IntegrityError:
                return JSONResponse(status_code=409, content={"detail":"account already exists"})
        with sqlite3.connect(db_path) as conn:
            conn.execute("DELETE FROM auth_login_attempts WHERE attempt_key=?", (attempt_key,))
        raw_session, csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
        with sqlite3.connect(db_path) as conn: conn.execute("INSERT INTO auth_sessions VALUES(?,?,?,?)",(hashlib.sha256(raw_session.encode()).digest(),invite[1],hashlib.sha256(csrf.encode()).digest(),now+43200))
        secure=cookie_is_secure(request)
        response.set_cookie("hacku_session",raw_session,httponly=True,secure=secure,samesite="lax",max_age=43200,path="/")
        response.set_cookie("hacku_csrf",csrf,httponly=False,secure=secure,samesite="lax",max_age=43200,path="/")
        return {"memberId":invite[1],"authenticated":True}

    @app.post("/api/auth/change-password")
    async def change_password(request: Request):
        session=auth_session(request); body=await request.json(); old=str(body.get("old_password", "")); new=str(body.get("new_password", ""))
        if not valid_password(new): return JSONResponse(status_code=400,content={"detail":"password must be at least 8 characters and include uppercase, lowercase, and a number"})
        with sqlite3.connect(db_path) as conn:
            row=conn.execute("SELECT salt,password_hash FROM auth_accounts WHERE member_id=?",(session["member_id"],)).fetchone()
            if not hmac.compare_digest(hashlib.scrypt(old.encode(),salt=row[0],n=2**14,r=8,p=1,dklen=32),row[1]): return JSONResponse(status_code=403,content={"detail":"current password is incorrect"})
            salt=secrets.token_bytes(16); digest=hashlib.scrypt(new.encode(),salt=salt,n=2**14,r=8,p=1,dklen=32)
            conn.execute("UPDATE auth_accounts SET salt=?,password_hash=? WHERE member_id=?",(salt,digest,session["member_id"]))
            conn.execute("DELETE FROM auth_sessions WHERE member_id=?",(session["member_id"],))
        return {"changed":True}

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

    def active_project_member(project_id,member_id):
        with sqlite3.connect(db_path) as conn:
            return bool(conn.execute("SELECT 1 FROM project_members pm LEFT JOIN project_membership_state ms ON ms.project_id=pm.project_id AND ms.member_id=pm.member_id LEFT JOIN project_lifecycle l ON l.project_id=pm.project_id WHERE pm.project_id=? AND pm.member_id=? AND COALESCE(ms.state,'ACTIVE')='ACTIVE' AND COALESCE(l.state,'ACTIVE')='ACTIVE'",(project_id,member_id)).fetchone())

    def write(method, *args):
        result = getattr(read(), method)(*args)
        return jsonable_encoder(asdict(result), custom_encoder={Decimal: str})

    @app.get("/api/projects")
    def projects(response: Response):
        response.headers["Cache-Control"] = "no-store"
        store = read()
        with sqlite3.connect(db_path) as conn:
            archived = {row[0] for row in conn.execute("SELECT project_id FROM project_lifecycle WHERE state <> 'ACTIVE'")}
        return [{"id": project.id, "name": project.name} for project in store.projects.values() if project.id not in archived]

    @app.get("/api/dashboard")
    def dashboard(response: Response):
        response.headers["Cache-Control"] = "no-store"
        store=read()
        with sqlite3.connect(db_path) as conn:
            active=[row[0] for row in conn.execute("SELECT project_id FROM project_lifecycle WHERE state='ACTIVE' ORDER BY rowid")]
        project_id=active[0] if active else None
        if not project_id: return {"project":None,"members":[],"tasks":[],"contributions":[],"relationships":[],"balances":[]}
        return project_data(project_id)

    @app.get("/api/projects/{project_id}/dashboard")
    def project_dashboard(project_id: str):
        return project_data(project_id)

    def project_data(project_id: str):
        with sqlite3.connect(db_path) as conn:
            lifecycle=conn.execute("SELECT state FROM project_lifecycle WHERE project_id=?",(project_id,)).fetchone()
        if not lifecycle: raise ValueError(f"unknown project {project_id}")
        if lifecycle[0] != "ACTIVE": return JSONResponse(status_code=410,content={"detail":"project is archived"})
        legacy = read()
        data = legacy.dashboard_data(project_id)
        ledger_state=project_ledger_state(project_id)
        data["tokenLedgerState"]=ledger_state
        if ledger_state == "READY":
            token = token_read(project_id)
            if token.project.id == project_id:
                minted = {event.id for event in token.ledger.events if event.kind.name == "MINT"}
                pending = [
                    item.id for item in legacy.contributions.values()
                    if item.project_id == project_id
                    and not _is_withdrawn(db_path, item.id)
                    and item.status.value in ("VERIFIED", "RESOLVED")
                    and contribution_score(item, legacy.projects[project_id],
                                           legacy.members, legacy.tasks) > 0
                    and f"{item.id}:mint" not in minted
                    and f"{item.id}:commission:mint" not in minted
                ]
                data["tokenRecognition"] = {
                    "balances": {member: float(value) for member, value in token.balances().items()},
                    "balancesExact": {member: str(value) for member, value in token.balances().items()},
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
                    if record.get("withdrawalState")=="WITHDRAWN":
                        recovered=sum((event.amount for event in token.ledger.events
                                       if event.id==f"withdraw:{item.id}:refund"),Decimal("0"))
                        debt=next((entry for entry in token.debts_payload() if entry["id"]==f"withdraw:{item.id}"),None)
                        with sqlite3.connect(db_path) as conn:
                            outbox=conn.execute("SELECT state,detail,amount FROM unwind_outbox WHERE id=?",(f"contribution:{item.id}:withdraw",)).fetchone()
                        record["tokenRecovery"]={"recoveredExact":str(recovered),"debtExact":debt["remainingExact"] if debt else "0","state":outbox[0] if outbox else "NOT_REQUIRED","detail":outbox[1] if outbox else "No pending accounting","recognizedExact":outbox[2] if outbox else "0"}
        return data

    @app.get("/api/projects/{project_id}/token-view")
    def token_view(project_id: str, response: Response):
        """Read-only stage-1 projection of legacy contributions into the token model."""
        response.headers["Cache-Control"] = "no-store"
        with sqlite3.connect(db_path) as conn:
            lifecycle=conn.execute("SELECT state FROM project_lifecycle WHERE project_id=?",(project_id,)).fetchone()
        if not lifecycle: return JSONResponse(status_code=404,content={"detail":"unknown project"})
        if lifecycle[0]!="ACTIVE": return JSONResponse(status_code=410,content={"detail":"project is archived"})
        return read().token_view(project_id)

    # --- Token ledger routes (durable, additive) ---
    # The token store lives in its own SQLite file (token.sqlite3 by default)
    # so the legacy eight tables stay untouched. Read routes return 404 when
    # the ledger database has not been created yet; the write routes create or
    # reuse it.

    def project_token_path(project_id: str, create=False) -> Path:
        with sqlite3.connect(db_path) as conn:
            if not conn.execute("SELECT 1 FROM projects WHERE id=?",(project_id,)).fetchone():
                raise ValueError(f"unknown project {project_id}")
        root=db_path.parent / "token-ledgers"
        digest=hashlib.sha256(project_id.encode("utf-8")).hexdigest()
        path=root / f"{digest}.sqlite3"
        if create: root.mkdir(parents=True,exist_ok=True)
        return path

    def active_token_path():
        project_id=token_project_context.get()
        if project_id: return project_token_path(project_id)
        try:
            with sqlite3.connect(db_path) as conn:
                row=conn.execute("SELECT project_id FROM token_ledger_migrations ORDER BY migrated_at LIMIT 1").fetchone()
            if row: return project_token_path(row[0])
        except sqlite3.Error: pass
        return token_db_path

    def project_ledger_state(project_id: str) -> str:
        path=project_token_path(project_id)
        if path.is_file() and path.stat().st_size:
            try:
                ledger=TokenStore(path)
                if ledger.project.id == project_id:
                    return "READY"
            except (ValueError,sqlite3.Error): pass
        # Copy the old single ledger exactly once to its owning project.
        if token_db_path.is_file() and token_db_path.stat().st_size and not path.exists():
            try:
                legacy=TokenStore(token_db_path)
                if legacy.project.id == project_id:
                    path.parent.mkdir(parents=True,exist_ok=True)
                    with sqlite3.connect(token_db_path) as source, sqlite3.connect(path) as target:
                        source.backup(target)
                    migrated=TokenStore(path)
                    last=migrated.ledger.events[-1].id if migrated.ledger.events else None
                    old_last=legacy.ledger.events[-1].id if legacy.ledger.events else None
                    if migrated.project.id != project_id or len(migrated.ledger.events) != len(legacy.ledger.events) or last != old_last:
                        path.unlink(missing_ok=True)
                        raise ValueError("legacy ledger verification failed")
                    with sqlite3.connect(db_path) as conn:
                        conn.execute("INSERT OR IGNORE INTO token_ledger_migrations(project_id,source_path,target_path,source_event_count,last_event_id) VALUES(?,?,?,?,?)",(project_id,str(token_db_path),str(path),len(migrated.ledger.events),last))
                        conn.execute("UPDATE project_lifecycle SET token_setup_state='READY' WHERE project_id=?",(project_id,))
                    return "READY"
            except (ValueError,sqlite3.Error,OSError):
                return "TOKEN_SETUP_PENDING"
        return "TOKEN_SETUP_PENDING"

    def ensure_project_ledger(project_id: str) -> TokenStore:
        path=project_token_path(project_id,create=True)
        state=project_ledger_state(project_id)
        if state != "READY":
            legacy=read(); project=legacy.projects[project_id]
            members=tuple(project.member_ids)
            treasury=f"{project_id}-treasury"
            TokenStore(path,TokenProject(project_id,project.name,treasury,members))
            # Mirror task definitions for an immediately usable project ledger.
            store=TokenStore(path)
            for task_id in project.task_ids:
                source=legacy.tasks[task_id]
                store.add_task(TokenTask(source.id,project_id,source.name,legacy._token_value_type(
                    [c for c in legacy.contributions.values() if c.project_id==project_id],task_id),
                    source.task_value,source.description.strip() or source.name))
            with sqlite3.connect(db_path) as conn:
                conn.execute("UPDATE project_lifecycle SET token_setup_state='READY' WHERE project_id=?",(project_id,))
        return TokenStore(path)

    def token_read(project_id=None) -> TokenStore:
        project_id=project_id or token_project_context.get()
        selected=project_token_path(project_id) if project_id else active_token_path()
        if project_id:
            state=project_ledger_state(project_id)
            if state != "READY": raise ValueError("project token ledger is not initialized")
        if not selected.is_file() or selected.stat().st_size == 0:
            raise ValueError("unknown token ledger; create it via POST /api/token/project "
                             "or migrate with migrate_token_ledger.py")
        return TokenStore(selected)

    def legacy_token_project_archived():
        try: project_id=token_read().project.id
        except (ValueError,sqlite3.Error): return None
        with sqlite3.connect(db_path) as conn:
            row=conn.execute("SELECT state FROM project_lifecycle WHERE project_id=?",(project_id,)).fetchone()
        return JSONResponse(status_code=410,content={"detail":"project is archived"}) if row and row[0]!="ACTIVE" else None

    def token_write(operation, *args, project_id=None):
        project_id=project_id or token_project_context.get()
        selected=project_token_path(project_id,create=True) if project_id else active_token_path()
        try:
            if operation == "create_project":
                store = TokenStore(selected, *args)
                return store.ledger_payload()
            store = TokenStore(selected) if selected.is_file() else None
            if store is None:
                raise ValueError("unknown token ledger; create it via POST /api/token/project")
            result = getattr(store, operation)(*args)
            return jsonable_encoder(result, custom_encoder={Decimal: str})
        except sqlite3.Error as error:
            raise ValueError(f"token ledger storage error: {error}") from error

    def sync_token_entities(project_id: str):
        """Add legacy members and tasks missing from the matching Token ledger."""
        if project_ledger_state(project_id) != "READY":
            return {"members": [], "tasks": []}
        legacy = read()
        project = legacy.projects[project_id]
        token = token_read(project_id)
        if token.project.id != project_id:
            return {"skipped": "Token 账本属于其他项目", "members": [], "tasks": []}
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

    def reconcile_project_outbox(project_id: str):
        results=[]
        if project_ledger_state(project_id) != "READY":
            if project_token_path(project_id).exists():
                raise ValueError("project ledger exists but cannot be verified; accounting stays pending")
            if token_db_path.exists() and token_db_path.stat().st_size:
                try:
                    if TokenStore(token_db_path).project.id == project_id:
                        raise ValueError("legacy project ledger migration is pending")
                except ValueError as error:
                    if "legacy project ledger migration" in str(error): raise
            with sqlite3.connect(db_path) as conn:
                pending=conn.execute("SELECT id FROM unwind_outbox WHERE project_id=? AND state='PENDING'",(project_id,)).fetchall()
                conn.executemany("UPDATE unwind_outbox SET state='DONE',amount='0',detail='No project ledger existed; no Tokens were minted' WHERE id=?",pending)
            return [{"id":row[0],"state":"DONE","detail":"No project ledger existed; no Tokens were minted"} for row in pending]
        ledger=token_read(project_id)
        with sqlite3.connect(db_path) as conn:
            pending=conn.execute("SELECT id,contribution_id,member_id,amount FROM unwind_outbox WHERE project_id=? AND state='PENDING' ORDER BY created_at,id",(project_id,)).fetchall()
        for outbox_id,contribution_id,member_id,_amount in pending:
            try:
                if outbox_id.startswith("contribution:"):
                    item=read().contributions.get(contribution_id)
                    if item is None:
                        detail="贡献记录不存在，需管理员人工核对"
                        with sqlite3.connect(db_path) as conn: conn.execute("UPDATE unwind_outbox SET detail=? WHERE id=?",(detail,outbox_id))
                        results.append({"id":outbox_id,"state":"PENDING","detail":detail}); continue
                    mint=next((event for event in ledger.ledger.events if event.kind.name=="MINT" and event.id in (f"{contribution_id}:mint",f"{contribution_id}:commission:mint")),None)
                    amount=contribution_score(item,read().projects[project_id],read().members,read().tasks)
                    related=[event.sequence for event in ledger.ledger.events
                             if event.id in (f"{contribution_id}:mint",f"{contribution_id}:commission:payment")
                             and event.sequence in ledger.ledger._frozen_events]
                    if related:
                        ledger.release_events(related,"撤回账务调和",tag=f"withdraw:{contribution_id}")
                    if mint and amount > 0:
                        ledger.reconcile_refund(f"withdraw:{contribution_id}",member_id,item.task_id,amount,[f"legacy:withdraw:{contribution_id}"],reason=f"withdrawn contribution {contribution_id}")
                    with sqlite3.connect(db_path) as conn:
                        conn.execute("UPDATE unwind_outbox SET amount=?,state='DONE',detail=? WHERE id=?",(str(amount),"Token returned or named debt recorded" if mint and amount>0 else "No refundable mint",outbox_id))
                    results.append({"id":outbox_id,"state":"DONE","amount":str(amount)})
                elif outbox_id.startswith("member:"):
                    for debt in ledger.debts_payload():
                        if debt["debtorId"]==member_id and Decimal(debt["remainingExact"])>0:
                            ledger.collect_debt(debt["id"])
                    available=max(Decimal("0"),ledger.balance(member_id))
                    sweep_id=f"member:{project_id}:{member_id}:exit-sweep:treasury"
                    already=next((event for event in ledger.ledger.events if event.id==sweep_id),None)
                    if available and not already:
                        task_id=next(iter(ledger.ledger.tasks),None)
                        if not task_id: raise ValueError("no task exists for treasury transfer")
                        ledger.transfer(sweep_id,member_id,ledger.project.treasury_id,available,task_id,[f"legacy:{sweep_id}"])
                    with sqlite3.connect(db_path) as conn:
                        conn.execute("UPDATE unwind_outbox SET amount=?,state='DONE',detail=? WHERE id=?",(str(available),"Member debts collected; remaining available balance swept to treasury",outbox_id))
                    results.append({"id":outbox_id,"state":"DONE","swept":str(available)})
            except (ValueError,sqlite3.Error,OSError) as error:
                with sqlite3.connect(db_path) as conn: conn.execute("UPDATE unwind_outbox SET detail=? WHERE id=?",(str(error)[:500],outbox_id))
                results.append({"id":outbox_id,"state":"PENDING","detail":str(error)[:500]})
        return results

    @app.get("/api/projects/{project_id}/unwind-outbox")
    def project_outbox(project_id: str, request: Request):
        session=auth_session(request)
        with sqlite3.connect(db_path) as conn:
            allowed=session and (session["site_admin"] or conn.execute("SELECT 1 FROM auth_project_admins WHERE project_id=? AND member_id=?",(project_id,session["member_id"])).fetchone())
            if not allowed: return JSONResponse(status_code=403,content={"detail":"project administrator required"})
            rows=conn.execute("SELECT id,contribution_id,member_id,amount,state,detail,created_at FROM unwind_outbox WHERE project_id=? ORDER BY created_at,id",(project_id,)).fetchall()
        return [{"id":row[0],"contributionId":row[1],"memberId":row[2],"amountExact":row[3],"state":row[4],"detail":row[5],"createdAt":row[6]} for row in rows]

    @app.post("/api/projects/{project_id}/unwind-outbox/reconcile")
    def retry_project_outbox(project_id: str, request: Request):
        session=auth_session(request)
        with sqlite3.connect(db_path) as conn:
            allowed=session and (session["site_admin"] or conn.execute("SELECT 1 FROM auth_project_admins WHERE project_id=? AND member_id=?",(project_id,session["member_id"])).fetchone())
            if not allowed: return JSONResponse(status_code=403,content={"detail":"project administrator required"})
        return reconcile_project_outbox(project_id)

    @app.post("/api/token/sync")
    def token_sync():
        original=token_read().project.id
        return sync_token_entities(original)

    @app.post("/api/token/reconcile")
    def token_reconcile():
        token = token_read()
        sync = sync_token_entities(token.project.id)
        legacy = read()
        results = []
        for item in legacy.contributions.values():
            if item.project_id != token.project.id:
                continue
            if _is_withdrawn(db_path,item.id):
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
    def token_ledger(response: Response):
        response.headers["Cache-Control"] = "no-store"
        archived=legacy_token_project_archived()
        if archived: return archived
        return token_read().ledger_payload()

    @app.get("/api/token/graph")
    def token_graph(response: Response):
        response.headers["Cache-Control"] = "no-store"
        archived=legacy_token_project_archived()
        if archived: return archived
        return token_read().graph_payload()

    @app.get("/api/token/contracts")
    def token_contracts(response: Response, request: Request):
        response.headers["Cache-Control"] = "no-store"
        archived=legacy_token_project_archived()
        if archived: return archived
        ledger=token_read()
        session=auth_session(request)
        if not session or not (session["site_admin"] or active_project_member(ledger.project.id,session["member_id"])):
            return JSONResponse(status_code=403,content={"detail":"active project membership required"})
        return ledger.contracts_payload()

    @app.get("/api/token/tasks")
    def token_tasks(response: Response):
        response.headers["Cache-Control"] = "no-store"
        archived=legacy_token_project_archived()
        if archived: return archived
        return [{
            "id": task.id, "name": task.name, "valueType": task.value_type.value,
            "mintCap": str(task.mint_cap), "acceptanceCriteria": task.acceptance_criteria,
        } for task in token_read().ledger.tasks.values()]

    @app.get("/api/token/tasks/{task_id}/budget")
    def token_task_budget(task_id: str, response: Response):
        response.headers["Cache-Control"] = "no-store"
        archived=legacy_token_project_archived()
        if archived: return archived
        return jsonable_encoder(token_read().task_budget(task_id), custom_encoder={Decimal: str})

    @app.get("/api/token/debts")
    def token_debts(response: Response, request: Request):
        response.headers["Cache-Control"] = "no-store"
        archived=legacy_token_project_archived()
        if archived: return archived
        ledger=token_read()
        session=auth_session(request)
        if not session or not (session["site_admin"] or active_project_member(ledger.project.id,session["member_id"])):
            return JSONResponse(status_code=403,content={"detail":"active project membership required"})
        return ledger.debts_payload()

    @app.post("/api/token/debts/{contribution_id}/collect")
    def token_collect_debt(contribution_id: str):
        return token_write("collect_debt", contribution_id)

    @app.post("/api/token/migrate", status_code=201)
    def token_migrate(project_id: str):
        """Import a legacy project only when no token ledger exists yet."""
        from migrate_token_ledger import migrate_project
        return migrate_project(db_path, token_db_path, project_id)

    @app.post("/api/token/project", status_code=201)
    def token_create_project(body: TokenProjectInput):
        legacy = read()
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
    def token_add_task(body: TokenTaskInput):
        task = TokenTask(body.id, token_read().project.id, body.name, ValueType(body.value_type),
                         body.mint_cap, body.acceptance_criteria)
        return token_write("add_task", task)

    @app.post("/api/token/tasks/{task_id}/cap")
    def token_set_task_cap(task_id: str, body: TokenCapInput):
        return token_write("set_mint_cap", task_id, body.mint_cap)

    @app.post("/api/token/contracts", status_code=201)
    def token_create_contract(body: CommissionInput):
        return token_write("create_commission", body.id, body.task_id, body.principal_id,
                           body.contractor_id, body.contract_price, body.maximum_mint_value)

    @app.post("/api/token/contracts/{contract_id}/advance")
    def token_advance_contract(contract_id: str, body: ContractAdvanceInput):
        return token_write("advance_contract", contract_id, ContractStatus(body.status))

    @app.post("/api/token/contracts/{contract_id}/approve", status_code=201)
    def token_approve_contract(contract_id: str, body: ContractApprovalInput, request: Request):
        session = auth_session(request)
        member_id = session["member_id"]
        token = token_read()
        contract = token.ledger.contracts.get(contract_id)
        if contract is None:
            return JSONResponse(status_code=404, content={"detail": "unknown contract"})
        if member_id not in token.project.member_ids:
            return JSONResponse(status_code=403, content={"detail": "project membership required"})
        if member_id in {contract.principal_id, contract.contractor_id}:
            return JSONResponse(status_code=403, content={"detail": "contract parties cannot approve"})
        if contract.status != ContractStatus.VERIFIED:
            return JSONResponse(status_code=409, content={"detail": "only verified contracts can be approved"})
        with sqlite3.connect(active_token_path()) as conn:
            try:
                conn.execute("INSERT INTO contract_approvals(contract_id,member_id,note) VALUES(?,?,?)",
                             (contract_id, member_id, body.note.strip()))
            except sqlite3.IntegrityError:
                return JSONResponse(status_code=409, content={"detail": "member already approved this contract"})
        return {"contractId": contract_id, "memberId": member_id, "approved": True}

    @app.post("/api/token/contracts/{contract_id}/dispute", status_code=201)
    def token_dispute_contract(contract_id: str, body: ContractDisputeInput, request: Request):
        session = auth_session(request)
        member_id = session["member_id"]
        token = token_read()
        contract = token.ledger.contracts.get(contract_id)
        if contract is None:
            return JSONResponse(status_code=404, content={"detail": "unknown contract"})
        if member_id not in {contract.principal_id, contract.contractor_id} and not session["site_admin"]:
            with sqlite3.connect(db_path) as conn:
                admin = conn.execute("SELECT 1 FROM auth_project_admins WHERE project_id=? AND member_id=?", (contract.project_id, member_id)).fetchone()
            if not admin:
                return JSONResponse(status_code=403, content={"detail": "contract party or project administrator required"})
        result = TokenStore(active_token_path()).dispute_contract(contract_id, member_id, body.reason)
        return result

    @app.post("/api/token/contracts/{contract_id}/freeze", status_code=201)
    def token_freeze_contract(contract_id: str, body: ContractDisputeInput):
        token = token_read()
        contract = token.ledger.contracts.get(contract_id)
        if contract is None:
            return JSONResponse(status_code=404, content={"detail": "unknown contract"})
        try:
            event, payment_sequence = TokenStore(active_token_path()).freeze_contract_payment(contract_id, body.reason)
        except ValueError as error:
            if "insufficient token balance" in str(error):
                payment = next((item for item in token.ledger.events if item.id == f"{contract_id}:payment"), None)
                available = token.balance(contract.contractor_id)
                shortfall = max(Decimal("0"), (payment.amount if payment else Decimal("0")) - available)
                return JSONResponse(status_code=409, content={"detail": "payment cannot be frozen; pending recovery", "shortfallExact": str(shortfall)})
            raise
        return {"event": asdict(event), "paymentSequence": payment_sequence}

    @app.post("/api/token/contracts/{contract_id}/resolve")
    def token_resolve_contract(contract_id: str, body: ContractResolutionInput, request: Request):
        session = auth_session(request)
        token = token_read()
        contract = token.ledger.contracts.get(contract_id)
        if contract is None:
            return JSONResponse(status_code=404, content={"detail": "unknown contract"})
        if member_id := session["member_id"]:
            if member_id in {contract.principal_id, contract.contractor_id}:
                return JSONResponse(status_code=403, content={"detail": "contract parties cannot resolve their own contract"})
        result, events = TokenStore(active_token_path()).resolve_contract(contract_id, body.outcome, body.note,
                                                                    session["member_id"], body.refund_amount)
        return {"resolution": jsonable_encoder(result, custom_encoder={Decimal: str}),
                "events": [jsonable_encoder(asdict(event), custom_encoder={Decimal: str}) for event in events]}

    @app.post("/api/token/mint", status_code=201)
    def token_mint(body: MintInput):
        token = token_read()
        legacy = read()
        if body.contribution_id:
            item = legacy.contributions.get(body.contribution_id)
            if item is None or item.project_id != token.project.id or item.task_id != body.task_id:
                raise ValueError("贡献 ID 与当前项目任务不匹配")
            with sqlite3.connect(db_path) as conn:
                if conn.execute("SELECT 1 FROM contribution_withdrawals WHERE contribution_id=?",(item.id,)).fetchone():
                    raise ValueError("已撤回贡献不能补铸")
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
                           body.amount, body.evidence_hashes)

    @app.post("/api/token/contracts/{contract_id}/settle")
    def token_settle(contract_id: str, body: SettleInput):
        with sqlite3.connect(active_token_path()) as conn:
            approvers = [row[0] for row in conn.execute(
                "SELECT member_id FROM contract_approvals WHERE contract_id=? ORDER BY approved_at, member_id", (contract_id,))]
        if not approvers:
            return JSONResponse(status_code=409, content={"detail": "an independent member approval is required"})
        if body.approver_ids and set(body.approver_ids) != set(approvers):
            return JSONResponse(status_code=403, content={"detail": "approver IDs must match recorded approvals"})
        mint, transfer = token_write("settle_commission", contract_id, body.verified_mint_value,
                                     body.evidence_hashes, approvers)
        return {"mint": mint, "transfer": transfer}

    @app.post("/api/token/transfer", status_code=201)
    def token_transfer(body: TransferInput):
        return token_write("transfer", body.event_id, body.source_id, body.destination_id,
                           body.amount, body.task_id, body.evidence_hashes)

    @app.post("/api/token/freeze", status_code=201)
    def token_freeze(body: FreezeInput):
        return token_write("freeze_events", body.sequences, body.reason, body.tag)

    @app.post("/api/token/release", status_code=201)
    def token_release(body: ReleaseInput):
        return token_write("release_events", body.sequences, body.note, body.tag)

    @app.get("/api/contributions/{contribution_id}")
    def contribution(contribution_id: str):
        item=read().contributions.get(contribution_id)
        if item is None: return JSONResponse(status_code=404,content={"detail":"unknown contribution"})
        with sqlite3.connect(db_path) as conn:
            state=conn.execute("SELECT state FROM project_lifecycle WHERE project_id=?",(item.project_id,)).fetchone()
        if state and state[0]!="ACTIVE": return JSONResponse(status_code=410,content={"detail":"project is archived"})
        return read().contribution_data(contribution_id)

    @app.post("/api/contributions/{contribution_id}/preview")
    def preview_score(contribution_id: str, body: ScorePreviewInput):
        return read().preview_score(contribution_id, body.completion, body.support_value, body.quality)

    @app.post("/api/projects", status_code=201)
    def create_project(body: ProjectInput, request: Request):
        session = auth_session(request)
        if not body.id.strip() or not body.name.strip(): return JSONResponse(status_code=400,content={"detail":"project id and name are required"})
        # Keep the new project and lifecycle state atomic. The site administrator
        # manages the project but is not automatically a project member.
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM projects WHERE id=?",(body.id,)).fetchone():
                return JSONResponse(status_code=409,content={"detail":"project ID has already been used"})
            conn.execute("INSERT INTO projects(id,name) VALUES(?,?)",(body.id,body.name))
            conn.execute("INSERT INTO project_lifecycle(project_id,state,token_setup_state) VALUES(?,'ACTIVE','TOKEN_SETUP_PENDING')",(body.id,))
            conn.execute("INSERT INTO project_versions(project_id,version) VALUES(?,1)",(body.id,))
            conn.commit()
        try:
            ensure_project_ledger(body.id)
            ledger_state="READY"
        except (ValueError,sqlite3.Error,OSError):
            ledger_state="TOKEN_SETUP_PENDING"
        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE project_lifecycle SET token_setup_state=? WHERE project_id=?",(ledger_state,body.id))
        return {"id":body.id,"name":body.name,"memberId":session["member_id"],"tokenLedgerState":ledger_state}

    @app.post("/api/contributions/{contribution_id}/unwind-requests", status_code=201)
    def request_contribution_unwind(contribution_id: str, body: LifecycleReasonInput, request: Request):
        session = auth_session(request); member_id = session["member_id"]
        if not body.reason.strip(): return JSONResponse(status_code=400, content={"detail":"reason is required"})
        store = read(); item = store.contributions.get(contribution_id)
        if item is None: return JSONResponse(status_code=404, content={"detail":"unknown contribution"})
        if item.contributor_id != member_id: return JSONResponse(status_code=403, content={"detail":"only the contributor may request withdrawal"})
        request_id = uuid4().hex
        with sqlite3.connect(db_path) as conn:
            active = conn.execute("SELECT state FROM project_membership_state WHERE project_id=? AND member_id=?",(item.project_id,member_id)).fetchone()
            life = conn.execute("SELECT state FROM project_lifecycle WHERE project_id=?",(item.project_id,)).fetchone()
            withdrawn = conn.execute("SELECT 1 FROM contribution_withdrawals WHERE contribution_id=?",(contribution_id,)).fetchone()
            pending = conn.execute("SELECT 1 FROM contribution_unwind_requests WHERE contribution_id=? AND state='PENDING'",(contribution_id,)).fetchone()
            if not active or active[0] != "ACTIVE" or not life or life[0] != "ACTIVE": return JSONResponse(status_code=409,content={"detail":"project membership is not active"})
            if withdrawn or pending: return JSONResponse(status_code=409,content={"detail":"withdrawal already requested or completed"})
            conn.execute("INSERT INTO contribution_unwind_requests(id,contribution_id,applicant_id,reason) VALUES(?,?,?,?)",(request_id,contribution_id,member_id,body.reason.strip()))
        return {"id":request_id,"contributionId":contribution_id,"state":"PENDING"}

    @app.post("/api/contributions/{contribution_id}/unwind-requests/{request_id}/decision")
    def decide_contribution_unwind(contribution_id: str, request_id: str, body: UnwindDecisionInput, request: Request):
        session=auth_session(request); reviewer=session["member_id"]
        if body.decision not in ("APPROVE","REJECT"): return JSONResponse(status_code=400,content={"detail":"decision must be APPROVE or REJECT"})
        store=read(); item=store.contributions.get(contribution_id)
        if item is None: return JSONResponse(status_code=404,content={"detail":"unknown contribution"})
        with sqlite3.connect(db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            req=conn.execute("SELECT applicant_id,state,reason FROM contribution_unwind_requests WHERE id=? AND contribution_id=?",(request_id,contribution_id)).fetchone()
            active=conn.execute("SELECT 1 FROM project_membership_state WHERE project_id=? AND member_id=? AND state='ACTIVE'",(item.project_id,reviewer)).fetchone()
            if not req or req[1] != "PENDING": return JSONResponse(status_code=409,content={"detail":"request is no longer pending"})
            if reviewer == req[0] or not active: return JSONResponse(status_code=403,content={"detail":"an independent active project member must decide"})
            if body.decision == "APPROVE":
                conn.execute("INSERT INTO contribution_withdrawals(contribution_id,request_id) VALUES(?,?)",(contribution_id,request_id))
                conn.execute("INSERT OR IGNORE INTO unwind_outbox(id,project_id,contribution_id,member_id,amount) VALUES(?,?,?,?,?)",("contribution:"+contribution_id+":withdraw",item.project_id,contribution_id,item.contributor_id,"0"))
            conn.execute("UPDATE contribution_unwind_requests SET state=?,reviewer_id=?,decision_note=?,decided_at=CURRENT_TIMESTAMP WHERE id=?",(body.decision,reviewer,body.note.strip(),request_id))
            conn.commit()
        accounting="NOT_REQUIRED"
        if body.decision == "APPROVE":
            try:
                results=reconcile_project_outbox(item.project_id)
                accounting="RECONCILED_OR_DEBT_RECORDED" if all(row["state"]=="DONE" for row in results) else "PENDING_RETRY"
            except (ValueError, sqlite3.Error, OSError): accounting="PENDING_RETRY"
        return {"id":request_id,"state":body.decision,"contributionId":contribution_id,"accountingState":accounting}

    @app.get("/api/projects/{project_id}/archive-preview")
    def archive_preview(project_id: str, request: Request):
        session=auth_session(request)
        if not session or not session["site_admin"]: return JSONResponse(status_code=403,content={"detail":"site administrator required"})
        with sqlite3.connect(db_path) as conn:
            project_row=conn.execute("SELECT name FROM projects WHERE id=?",(project_id,)).fetchone()
            if not project_row: return JSONResponse(status_code=404,content={"detail":"unknown project"})
            version,state=conn.execute("SELECT version,state FROM project_lifecycle WHERE project_id=?",(project_id,)).fetchone()
            counts={key:conn.execute(sql,(project_id,)).fetchone()[0] for key,sql in {
                "members":"SELECT count(*) FROM project_members WHERE project_id=?",
                "contributions":"SELECT count(*) FROM contributions WHERE project_id=?",
                "events":"SELECT count(*) FROM project_lifecycle_events WHERE project_id=?",
                "pendingWithdrawals":"SELECT count(*) FROM contribution_unwind_requests r JOIN contributions c ON c.id=r.contribution_id WHERE c.project_id=? AND r.state='PENDING'",
                "pendingExits":"SELECT count(*) FROM membership_exit_requests WHERE project_id=? AND state='PENDING'",
                "pendingOutbox":"SELECT count(*) FROM unwind_outbox WHERE project_id=? AND state='PENDING'",
            }.items()}
        ledger_summary={"state":project_ledger_state(project_id),"eventCount":0,"balances":{},"debts":[],"unsettledContracts":[],"frozenEventSequences":[]}
        try:
            ledger=token_read(project_id)
            ledger_summary.update(eventCount=len(ledger.ledger.events),balances={key:str(value) for key,value in ledger.balances().items()},debts=ledger.debts_payload(),unsettledContracts=[contract.id for contract in ledger.ledger.contracts.values() if contract.status not in (ContractStatus.SETTLED,ContractStatus.RESOLVED)],frozenEventSequences=sorted(ledger.ledger._frozen_events))
        except ValueError: pass
        return {"projectId":project_id,"projectName":project_row[0],"version":version,"state":state,"counts":counts,"tokenLedger":ledger_summary,"message":"归档可恢复，数据不会物理删除。"}

    @app.get("/api/admin/projects")
    def admin_projects(state: str = "archived", request: Request = None):
        session=auth_session(request)
        if not session or not session["site_admin"]: return JSONResponse(status_code=403,content={"detail":"site administrator required"})
        with sqlite3.connect(db_path) as conn:
            return [{"id":row[0],"name":row[1],"state":row[2],"version":row[3]} for row in conn.execute("SELECT p.id,p.name,l.state,l.version FROM projects p JOIN project_lifecycle l ON l.project_id=p.id WHERE l.state=? ORDER BY p.name",(state,))]

    @app.get("/api/admin/projects/{project_id}")
    def admin_project_detail(project_id: str, request: Request):
        session=auth_session(request)
        if not session or not session["site_admin"]: return JSONResponse(status_code=403,content={"detail":"site administrator required"})
        with sqlite3.connect(db_path) as conn:
            row=conn.execute("SELECT state,version,token_setup_state FROM project_lifecycle WHERE project_id=?",(project_id,)).fetchone()
            snapshots=[{"version":item[0],"createdAt":item[1],"payload":json.loads(item[2])} for item in conn.execute("SELECT version,created_at,payload FROM project_archive_snapshots WHERE project_id=? ORDER BY version",(project_id,))]
        if not row: return JSONResponse(status_code=404,content={"detail":"unknown project"})
        return {"projectId":project_id,"state":row[0],"version":row[1],"tokenSetupState":row[2],"dashboard":read().dashboard_data(project_id),"archiveSnapshots":snapshots}

    @app.post("/api/projects/{project_id}/archive")
    def archive_project(project_id: str, body: dict, request: Request):
        session=auth_session(request)
        if not session or not session["site_admin"]: return JSONResponse(status_code=403,content={"detail":"site administrator required"})
        if body.get("project_id") != project_id or not str(body.get("reason","")).strip(): return JSONResponse(status_code=400,content={"detail":"project_id and reason are required"})
        snapshot=archive_preview(project_id,request)
        if isinstance(snapshot,JSONResponse): return snapshot
        with sqlite3.connect(db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            current=conn.execute("SELECT state,version FROM project_lifecycle WHERE project_id=?",(project_id,)).fetchone()
            if not current: return JSONResponse(status_code=404,content={"detail":"unknown project"})
            if current[0]=="ARCHIVED": return {"projectId":project_id,"state":"ARCHIVED","idempotent":True}
            if current[1] != body.get("version"): return JSONResponse(status_code=409,content={"detail":"project changed after preview; load a new preview"})
            if conn.execute("SELECT 1 FROM unwind_outbox WHERE project_id=? AND state='PENDING' LIMIT 1",(project_id,)).fetchone(): return JSONResponse(status_code=409,content={"detail":"pending unwind accounting must be reconciled first"})
            conn.execute("INSERT INTO project_archive_snapshots(project_id,version,payload) VALUES(?,?,?)",(project_id,current[1],json.dumps({**snapshot,"reason":str(body["reason"]).strip()},ensure_ascii=False)))
            conn.execute("UPDATE project_lifecycle SET state='ARCHIVED',version=version+1,changed_at=CURRENT_TIMESTAMP WHERE project_id=?",(project_id,))
            conn.execute("INSERT INTO project_lifecycle_events(project_id,actor_id,action,reason,before_state,after_state) VALUES(?,?,'ARCHIVE',?,?, 'ARCHIVED')",(project_id,session["member_id"],str(body["reason"]).strip(),current[0]))
            conn.commit()
        return {"projectId":project_id,"state":"ARCHIVED"}

    @app.post("/api/projects/{project_id}/restore")
    def restore_project(project_id: str, body: LifecycleReasonInput, request: Request):
        session=auth_session(request)
        if not session or not session["site_admin"]: return JSONResponse(status_code=403,content={"detail":"site administrator required"})
        if not body.reason.strip(): return JSONResponse(status_code=400,content={"detail":"reason is required"})
        with sqlite3.connect(db_path) as conn:
            row=conn.execute("SELECT state FROM project_lifecycle WHERE project_id=?",(project_id,)).fetchone()
            if not row: return JSONResponse(status_code=404,content={"detail":"unknown project"})
            if row[0]=="ACTIVE": return {"projectId":project_id,"state":"ACTIVE","idempotent":True}
            conn.execute("UPDATE project_lifecycle SET state='ACTIVE',version=version+1,changed_at=CURRENT_TIMESTAMP WHERE project_id=?",(project_id,))
            conn.execute("INSERT INTO project_lifecycle_events(project_id,actor_id,action,reason,before_state,after_state) VALUES(?,?,'RESTORE',?,?, 'ACTIVE')",(project_id,session["member_id"],body.reason.strip(),row[0]))
        return {"projectId":project_id,"state":"ACTIVE"}

    @app.get("/api/projects/{project_id}/members/me/exit-preview")
    def member_exit_preview(project_id: str, request: Request):
        session=auth_session(request); member_id=session["member_id"]
        if not read().projects.get(project_id): return JSONResponse(status_code=404,content={"detail":"unknown project"})
        store=read()
        owned=[item for item in store.contributions.values() if item.project_id==project_id and item.contributor_id==member_id]
        with sqlite3.connect(db_path) as conn:
            withdrawn_ids={row[0] for row in conn.execute("SELECT contribution_id FROM contribution_withdrawals")}
            owned=[item for item in owned if item.id not in withdrawn_ids]
            disputes=conn.execute("SELECT count(*) FROM disputes d JOIN contributions c ON c.id=d.contribution_id WHERE c.project_id=? AND d.resolution IS NULL",(project_id,)).fetchone()[0]
            pending=conn.execute("SELECT count(*) FROM membership_exit_requests WHERE project_id=? AND member_id=? AND state='PENDING'",(project_id,member_id)).fetchone()[0]
            admins=conn.execute("SELECT count(*) FROM auth_project_admins WHERE project_id=?",(project_id,)).fetchone()[0]
            is_admin=bool(conn.execute("SELECT 1 FROM auth_project_admins WHERE project_id=? AND member_id=?",(project_id,member_id)).fetchone())
            active_peers=conn.execute("SELECT count(*) FROM project_membership_state WHERE project_id=? AND member_id<>? AND state='ACTIVE'",(project_id,member_id)).fetchone()[0]
            member_state=conn.execute("SELECT state FROM project_membership_state WHERE project_id=? AND member_id=?",(project_id,member_id)).fetchone()
        if not member_state or member_state[0] not in ("ACTIVE","EXIT_REQUESTED"):
            return JSONResponse(status_code=403,content={"detail":"active project membership required"})
        blockers=[]
        if disputes: blockers.append(f"{disputes} 条未解决争议")
        if is_admin and admins <= 1: blockers.append("唯一项目管理员必须先移交管理员权限")
        if not active_peers: blockers.append("没有可独立审批的其他活跃成员")
        try:
            ledger=token_read(project_id)
            frozen=sum((ledger.ledger.events[seq-1].amount for seq in ledger.ledger._frozen_events
                        if seq <= len(ledger.ledger.events) and ledger.ledger.events[seq-1].destination_id == member_id),Decimal("0"))
            contracts=[item.id for item in ledger.ledger.contracts.values()
                       if member_id in (item.principal_id,item.contractor_id)
                       and item.status not in (ContractStatus.SETTLED,ContractStatus.RESOLVED)]
            debts=[debt for debt in ledger.debts_payload() if debt["debtorId"]==member_id and Decimal(debt["remainingExact"])>0]
        except (ValueError,sqlite3.Error):
            frozen=Decimal("0");contracts=[];debts=[]
        if frozen>0: blockers.append(f"冻结 Token {frozen}，必须先释放或解决")
        if contracts: blockers.append(f"{len(contracts)} 个未结算合约")
        balance=ledger.balance(member_id) if 'ledger' in locals() else Decimal("0")
        minted_ids={event.id for event in ledger.ledger.events if event.kind.name=="MINT"} if 'ledger' in locals() else set()
        recognized=sum((contribution_score(x,store.projects[project_id],store.members,store.tasks)
                        for x in owned if f"{x.id}:mint" in minted_ids or f"{x.id}:commission:mint" in minted_ids),Decimal("0"))
        return {"projectId":project_id,"memberId":member_id,"contributions":[{"id":x.id,"score":str(contribution_score(x,store.projects[project_id],store.members,store.tasks))} for x in owned],"pendingRequest":bool(pending),"balance":str(balance),"frozen":str(frozen),"contracts":contracts,"debts":debts,"recognizedToRecoverExact":str(recognized),"estimatedShortfallExact":str(max(Decimal("0"),recognized-max(Decimal("0"),balance))),"blockers":blockers}

    @app.post("/api/projects/{project_id}/members/me/exit-requests",status_code=201)
    def request_member_exit(project_id: str, body: LifecycleReasonInput, request: Request):
        member_id=auth_session(request)["member_id"]
        if not body.reason.strip(): return JSONResponse(status_code=400,content={"detail":"reason is required"})
        preview=member_exit_preview(project_id,request)
        if isinstance(preview,JSONResponse): return preview
        request_id=uuid4().hex
        with sqlite3.connect(db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur=conn.execute("UPDATE project_membership_state SET state='EXIT_REQUESTED' WHERE project_id=? AND member_id=? AND state='ACTIVE'",(project_id,member_id))
            if not cur.rowcount: return JSONResponse(status_code=409,content={"detail":"membership is not active"})
            snapshot=json.dumps([item["id"] for item in preview["contributions"]],ensure_ascii=False)
            conn.execute("INSERT INTO membership_exit_requests(id,project_id,member_id,reason,contribution_ids_snapshot) VALUES(?,?,?,?,?)",(request_id,project_id,member_id,body.reason.strip(),snapshot))
            conn.commit()
        return {"id":request_id,"state":"PENDING","preview":preview}

    @app.post("/api/projects/{project_id}/members/me/exit-requests/{request_id}/cancel")
    def cancel_member_exit(project_id: str, request_id: str, request: Request):
        member_id=auth_session(request)["member_id"]
        with sqlite3.connect(db_path) as conn:
            cur=conn.execute("UPDATE membership_exit_requests SET state='CANCELLED',decided_at=CURRENT_TIMESTAMP WHERE id=? AND project_id=? AND member_id=? AND state='PENDING'",(request_id,project_id,member_id))
            if not cur.rowcount: return JSONResponse(status_code=409,content={"detail":"exit request is no longer pending"})
            conn.execute("UPDATE project_membership_state SET state='ACTIVE' WHERE project_id=? AND member_id=? AND state='EXIT_REQUESTED'",(project_id,member_id))
        return {"id":request_id,"state":"CANCELLED"}

    @app.post("/api/projects/{project_id}/members/{member_id}/exit-requests/{request_id}/decision")
    def decide_member_exit(project_id: str, member_id: str, request_id: str, body: UnwindDecisionInput, request: Request):
        reviewer=auth_session(request)["member_id"]
        if body.decision not in ("APPROVE","REJECT"): return JSONResponse(status_code=400,content={"detail":"decision must be APPROVE or REJECT"})
        if reviewer == member_id: return JSONResponse(status_code=403,content={"detail":"an independent member must decide"})
        # Migrate the legacy ledger before taking the contribution DB write lock.
        project_ledger_state(project_id)
        with sqlite3.connect(db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            req=conn.execute("SELECT state FROM membership_exit_requests WHERE id=? AND project_id=? AND member_id=?",(request_id,project_id,member_id)).fetchone()
            peer=conn.execute("SELECT 1 FROM project_membership_state WHERE project_id=? AND member_id=? AND state='ACTIVE'",(project_id,reviewer)).fetchone()
            if not req or req[0] != 'PENDING': return JSONResponse(status_code=409,content={"detail":"request is no longer pending"})
            if not peer: return JSONResponse(status_code=403,content={"detail":"active project membership required"})
            if body.decision == 'APPROVE':
                disputes=conn.execute("SELECT count(*) FROM disputes d JOIN contributions c ON c.id=d.contribution_id WHERE c.project_id=? AND d.resolution IS NULL",(project_id,)).fetchone()[0]
                if disputes: return JSONResponse(status_code=409,content={"detail":"unresolved disputes block member exit","blockers":[f"{disputes} unresolved dispute(s)"]})
                admins=conn.execute("SELECT count(*) FROM auth_project_admins WHERE project_id=?",(project_id,)).fetchone()[0]
                exiting_admin=conn.execute("SELECT 1 FROM auth_project_admins WHERE project_id=? AND member_id=?",(project_id,member_id)).fetchone()
                if exiting_admin and admins<=1:
                    return JSONResponse(status_code=409,content={"detail":"sole project administrator must transfer role before exit","blockers":["唯一项目管理员必须先移交管理员权限"]})
                try:
                    ledger=token_read(project_id)
                    frozen=[sequence for sequence in ledger.ledger._frozen_events
                            if sequence<=len(ledger.ledger.events)
                            and ledger.ledger.events[sequence-1].destination_id==member_id]
                    unsettled=[item.id for item in ledger.ledger.contracts.values()
                               if member_id in (item.principal_id,item.contractor_id)
                               and item.status not in (ContractStatus.SETTLED,ContractStatus.RESOLVED)]
                    if frozen or unsettled:
                        return JSONResponse(status_code=409,content={"detail":"frozen Tokens or unsettled contracts block member exit","blockers":[*( [f"{len(frozen)} frozen Token event(s)"] if frozen else []),*([f"{len(unsettled)} unsettled contract(s)"] if unsettled else [])]})
                except ValueError:
                    pass
                snapshot=conn.execute("SELECT contribution_ids_snapshot FROM membership_exit_requests WHERE id=?",(request_id,)).fetchone()[0]
                ids=json.loads(snapshot or "[]")
                items=[(item_id,) for item_id in ids]
                for (contribution_id,) in items:
                    if conn.execute("SELECT 1 FROM contribution_withdrawals WHERE contribution_id=?",(contribution_id,)).fetchone(): continue
                    withdrawal_request_id=uuid4().hex
                    conn.execute("INSERT INTO contribution_unwind_requests(id,contribution_id,applicant_id,reason,state,reviewer_id,decision_note,decided_at) VALUES(?,?,?,?,'APPROVE',?, '批量成员退出撤回',CURRENT_TIMESTAMP)",(withdrawal_request_id,contribution_id,member_id,"成员退出申请 "+request_id,reviewer))
                    conn.execute("INSERT INTO contribution_withdrawals(contribution_id,request_id) VALUES(?,?)",(contribution_id,withdrawal_request_id))
                    conn.execute("INSERT OR IGNORE INTO unwind_outbox(id,project_id,contribution_id,member_id,amount) VALUES(?,?,?,?, '0')",(f"contribution:{contribution_id}:withdraw",project_id,contribution_id,member_id))
                conn.execute("UPDATE project_membership_state SET state='WITHDRAWN' WHERE project_id=? AND member_id=?",(project_id,member_id))
                conn.execute("DELETE FROM auth_project_admins WHERE project_id=? AND member_id=?",(project_id,member_id))
                conn.execute("UPDATE auth_invites SET used_at=COALESCE(used_at,?) WHERE project_id=? AND member_id=?",(int(time.time()),project_id,member_id))
                conn.execute("INSERT OR IGNORE INTO unwind_outbox(id,project_id,contribution_id,member_id,amount) VALUES(?,?,NULL,?,'0')",(f"member:{project_id}:{member_id}:exit-sweep",project_id,member_id))
            conn.execute("UPDATE membership_exit_requests SET state=?,reviewer_id=?,decided_at=CURRENT_TIMESTAMP WHERE id=?",(body.decision,reviewer,request_id))
            if body.decision == 'REJECT': conn.execute("UPDATE project_membership_state SET state='ACTIVE' WHERE project_id=? AND member_id=?",(project_id,member_id))
            conn.commit()
        accounting="NOT_REQUIRED"
        if body.decision=="APPROVE":
            try:
                states=reconcile_project_outbox(project_id)
                accounting="COMPLETE" if all(item["state"]=="DONE" for item in states) else "PENDING_RETRY"
            except (ValueError,sqlite3.Error,OSError): accounting="PENDING_RETRY"
        return {"id":request_id,"state":body.decision,"memberId":member_id,"accountRetained":True,"accountingState":accounting}

    @app.post("/api/projects/{project_id}/members", status_code=201)
    def add_member(project_id: str, body: MemberInput):
        result = write("add_member", project_id, body.id, body.name)
        with sqlite3.connect(db_path) as conn:
            conn.execute("INSERT OR IGNORE INTO project_membership_state(project_id,member_id,state) VALUES(?,?,'ACTIVE')",
                         (project_id, body.id))
        try:
            result["tokenSync"] = sync_token_entities(project_id)
        except Exception as error:
            result["tokenSync"] = {"skipped": str(error)}
        return result

    @app.delete("/api/projects/{project_id}/members/{member_id}")
    def remove_member(project_id: str, member_id: str):
        """Remove an unused project membership without deleting the global account."""
        with sqlite3.connect(db_path) as conn:
            if not conn.execute("SELECT 1 FROM project_members WHERE project_id=? AND member_id=?", (project_id, member_id)).fetchone():
                return JSONResponse(status_code=404, content={"detail": "member is not in this project"})
            if conn.execute("SELECT 1 FROM contributions WHERE project_id=? AND (contributor_id=? OR helped_member_id=?)", (project_id, member_id, member_id)).fetchone():
                return JSONResponse(status_code=409, content={"detail": "member has contribution history; use the exit workflow instead"})
            admin_count = conn.execute("SELECT count(*) FROM auth_project_admins WHERE project_id=?", (project_id,)).fetchone()[0]
            is_admin = conn.execute("SELECT 1 FROM auth_project_admins WHERE project_id=? AND member_id=?", (project_id, member_id)).fetchone()
            if is_admin and admin_count <= 1:
                return JSONResponse(status_code=409, content={"detail": "the last project administrator cannot be removed"})
            conn.execute("DELETE FROM auth_invites WHERE project_id=? AND member_id=?", (project_id, member_id))
            conn.execute("DELETE FROM auth_project_admins WHERE project_id=? AND member_id=?", (project_id, member_id))
            conn.execute("DELETE FROM project_membership_state WHERE project_id=? AND member_id=?", (project_id, member_id))
            conn.execute("DELETE FROM project_members WHERE project_id=? AND member_id=?", (project_id, member_id))
        return {"projectId": project_id, "memberId": member_id, "removed": True}

    @app.post("/api/projects/{project_id}/tasks", status_code=201)
    def add_task(project_id: str, body: TaskInput):
        result = write("add_task", project_id, body.id, body.name, body.task_value, body.description)
        try:
            result["tokenSync"] = sync_token_entities(project_id)
        except Exception as error:
            result["tokenSync"] = {"skipped": str(error)}
        return result

    @app.post("/api/projects/{project_id}/contributions", status_code=201)
    def submit_contribution(project_id: str, body: ContributionInput, request: Request):
        session = auth_session(request)
        if not session or body.contributor_id != session["member_id"]:
            return JSONResponse(status_code=403, content={"detail":"contributor must match the signed-in member"})
        return write("submit_contribution", project_id, body.id, body.contributor_id,
                     body.task_id, body.type, body.description, body.completion,
                     body.support_value, body.helped_member_id)

    @app.post("/api/contributions/{contribution_id}/evidence", status_code=201)
    def add_evidence(contribution_id: str, body: EvidenceInput, request: Request):
        session = auth_session(request)
        if not session or body.submitted_by != session["member_id"]:
            return JSONResponse(status_code=403, content={"detail":"evidence submitter must match the signed-in member"})
        item=read().contributions.get(contribution_id)
        if item is None: return JSONResponse(status_code=404,content={"detail":"unknown contribution"})
        if not active_project_member(item.project_id,body.submitted_by): return JSONResponse(status_code=403,content={"detail":"active project membership required"})
        return write("add_evidence", contribution_id, body.submitted_by, body.kind, body.reference)

    @app.post("/api/contributions/{contribution_id}/reviews")
    def review_contribution(contribution_id: str, body: ReviewInput, request: Request):
        session = auth_session(request)
        if not session or body.reviewer_id != session["member_id"]:
            return JSONResponse(status_code=403, content={"detail":"reviewer must match the signed-in member"})
        legacy = read()
        item = legacy.contributions[contribution_id]
        if not active_project_member(item.project_id,body.reviewer_id): return JSONResponse(status_code=403,content={"detail":"active project membership required"})
        if project_ledger_state(item.project_id) == "READY":
            try:
                token = token_read(item.project_id)
            except (ValueError, sqlite3.Error):
                token = None  # The committed legacy review reports a skipped token hook below.
            if token is not None and token.project.id == item.project_id and body.decision in (
                VerificationDecision.CONFIRM, VerificationDecision.ADJUST
            ):
                sync_token_entities(item.project_id)
                token = token_read(item.project_id)
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
        session = auth_session(request)
        if not session or body.resolved_by != session["member_id"]:
            return JSONResponse(status_code=403, content={"detail":"resolver must match the signed-in member"})
        item=read().contributions.get(contribution_id)
        if item is None: return JSONResponse(status_code=404,content={"detail":"unknown contribution"})
        if not active_project_member(item.project_id,body.resolved_by): return JSONResponse(status_code=403,content={"detail":"active project membership required"})
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
        item = read().contributions.get(contribution_id)
        if item is None:
            return None
        if _is_withdrawn(db_path,item.id):
            return {"skipped":"贡献已撤回，不会再铸币"}
        if project_ledger_state(item.project_id) != "READY":
            # Preserve the legacy review while making a damaged existing ledger
            # visible to the caller so it can be repaired and reconciled.
            if token_db_path.is_file() and token_db_path.stat().st_size:
                try:
                    TokenStore(token_db_path)
                except (ValueError, sqlite3.Error):
                    return {"code": "storage_failed", "skipped": "Token 账本无法读取；旧审核已保存"}
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
        item = read().contributions[contribution_id]
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
        item = read().contributions.get(contribution_id)
        if item is None or project_ledger_state(item.project_id) != "READY":
            return None
        try:
            sequences = _frozen_legacy_mints(contribution_id)
            if not sequences:
                return {"skipped": "没有需要冻结的铸币记录"}
            store = _open_token_store(item.project_id)
            events = store.freeze_events(sequences, reason.strip() or "争议冻结",
                                         tag=contribution_id)
            return {"kind": "FREEZE", "eventIds": [event.id for event in events],
                    "sequences": [event.sequence for event in events]}
        except Exception as error:
            return {"skipped": token_issue(error)}

    def _open_token_store(project_id=None):
        """Open the ledger, converting storage failures into skipped markers."""
        try:
            return token_read(project_id) if project_id else TokenStore(active_token_path())
        except sqlite3.Error as error:
            raise ValueError(f"token ledger storage error: {error}") from error

    def _token_release_for_contribution(contribution_id: str, note: str):
        """Release frozen tokens; returns None when nothing is frozen."""
        item = read().contributions.get(contribution_id)
        if item is None or project_ledger_state(item.project_id) != "READY":
            return None
        try:
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
        when the final score is higher, or transfers the difference back to
        the treasury when it is lower. When there is nothing frozen (the
        contribution was disputed before minting), falls back to a normal
        mint for the final score.
        """
        item = read().contributions.get(contribution_id)
        if item is None or project_ledger_state(item.project_id) != "READY":
            return None
        try:
            released = _token_release_for_contribution(contribution_id, note)
            if released and "skipped" in released:
                return {"code": "release_failed", "skipped": released["skipped"]}
            item, final_amount = _legacy_score(contribution_id)
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
                correction = {"kind": "TRANSFER", "eventId": event.id if event else None,
                              "destinationId": store.project.treasury_id,
                              "amount": float(-delta - remaining),
                              "debtExact": str(remaining)}
            return {"released": released, "correction": correction,
                    "finalAmount": float(final_amount)}
        except Exception as error:
            return {"skipped": token_issue(error)}

    @app.api_route("/api/projects/{project_id}/token/{token_path:path}", methods=["GET","POST"])
    async def project_token_api(project_id: str, token_path: str, request: Request):
        # All paths and payload project IDs are ignored for routing. The URL's
        # validated project ID selects the hashed, isolated ledger file.
        project_token_path(project_id)
        with sqlite3.connect(db_path) as conn:
            lifecycle=conn.execute("SELECT state FROM project_lifecycle WHERE project_id=?",(project_id,)).fetchone()
        if not lifecycle: return JSONResponse(status_code=404,content={"detail":"unknown project"})
        if lifecycle[0]!="ACTIVE": return JSONResponse(status_code=410,content={"detail":"project is archived"})
        marker=token_project_context.set(project_id)
        try:
            method=request.method
            route=token_path.strip("/")
            if method=="GET":
                if route=="status":
                    return {"projectId":project_id,"state":project_ledger_state(project_id)}
                if route in ("contracts","debts"):
                    session=auth_session(request)
                    allowed=session and (session["site_admin"] or active_project_member(project_id,session["member_id"]))
                    if not allowed: return JSONResponse(status_code=403,content={"detail":"active project membership required"})
                ledger=token_read(project_id)
                if route=="ledger": return ledger.ledger_payload()
                if route=="graph": return ledger.graph_payload()
                if route=="contracts": return ledger.contracts_payload()
                if route=="tasks": return [{"id":t.id,"name":t.name,"valueType":t.value_type.value,"mintCap":str(t.mint_cap),"acceptanceCriteria":t.acceptance_criteria} for t in ledger.ledger.tasks.values()]
                if route=="debts": return ledger.debts_payload()
                if route.startswith("tasks/") and route.endswith("/budget"):
                    task_id=route.split("/")[1]
                    return jsonable_encoder(ledger.task_budget(task_id),custom_encoder={Decimal:str})
                return JSONResponse(status_code=404,content={"detail":"unknown project token route"})
            if route=="setup/retry":
                ledger=ensure_project_ledger(project_id)
                with sqlite3.connect(db_path) as conn: conn.execute("UPDATE project_lifecycle SET token_setup_state='READY' WHERE project_id=?",(project_id,))
                sync=sync_token_entities(project_id)
                reconciliation=token_reconcile()
                return {"projectId":project_id,"state":"READY","sync":sync,"reconciliation":reconciliation,"ledger":token_read(project_id).ledger_payload()}
            if route=="sync": return sync_token_entities(project_id)
            if route=="reconcile": return token_reconcile()
            if route=="migrate":
                from migrate_token_ledger import migrate_project
                return migrate_project(db_path,project_token_path(project_id,create=True),project_id)
            try: data=await request.json()
            except ValueError: data={}
            parts=route.split("/")
            if route=="tasks" and method=="POST": return token_add_task(TokenTaskInput.model_validate(data))
            if len(parts)==3 and parts[0]=="tasks" and parts[2]=="cap":
                return token_set_task_cap(parts[1],TokenCapInput.model_validate(data))
            if route=="contracts": return token_create_contract(CommissionInput.model_validate(data))
            if len(parts)>=2 and parts[0]=="contracts":
                contract_id=parts[1]
                if len(parts)==2 and method=="GET":
                    return next((item for item in token_read(project_id).contracts_payload() if item["id"]==contract_id),JSONResponse(status_code=404,content={"detail":"unknown contract"}))
                if len(parts)==3 and parts[2]=="advance": return token_advance_contract(contract_id,ContractAdvanceInput.model_validate(data))
                if len(parts)==3 and parts[2]=="approve": return token_approve_contract(contract_id,ContractApprovalInput.model_validate(data),request)
                if len(parts)==3 and parts[2]=="dispute": return token_dispute_contract(contract_id,ContractDisputeInput.model_validate(data),request)
                if len(parts)==3 and parts[2]=="freeze": return token_freeze_contract(contract_id,ContractDisputeInput.model_validate(data))
                if len(parts)==3 and parts[2]=="resolve": return token_resolve_contract(contract_id,ContractResolutionInput.model_validate(data),request)
                if len(parts)==3 and parts[2]=="settle": return token_settle(contract_id,SettleInput.model_validate(data))
            if route=="mint": return token_mint(MintInput.model_validate(data))
            if route=="transfer": return token_transfer(TransferInput.model_validate(data))
            if route=="freeze": return token_freeze(FreezeInput.model_validate(data))
            if route=="release": return token_release(ReleaseInput.model_validate(data))
            if len(parts)==3 and parts[0]=="debts" and parts[2]=="collect": return token_collect_debt(parts[1])
            return JSONResponse(status_code=404,content={"detail":"unknown project token route"})
        except (ValueError,sqlite3.Error,OSError) as error:
            return JSONResponse(status_code=409 if "ledger" in str(error).lower() else 400,content={"detail":str(error)})
        finally:
            token_project_context.reset(marker)

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
    print("API writes: authenticated member sessions", flush=True)
    host = "0.0.0.0" if os.environ.get("POCKETBAY_DATA_DIR") else "127.0.0.1"
    uvicorn.run(create_app(args.db, args.token_db), host=host, port=args.port)
