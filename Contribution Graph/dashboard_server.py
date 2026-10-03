"""FastAPI service for the dashboard and contribution workflow."""

import argparse
import json
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from threading import Lock

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from contribution_engine import ContributionType, EvidenceType, VerificationDecision
from contribution_store import ContributionStore


ROOT = Path(__file__).with_name("dashboard")
DEFAULT_DB = Path(__file__).with_name("demo.json")


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


def create_app(db_path=DEFAULT_DB):
    app = FastAPI(title="Contribution Graph API")
    db_path = Path(db_path)
    write_lock = Lock()

    @app.exception_handler(ValueError)
    @app.exception_handler(InvalidOperation)
    async def bad_input(_request: Request, error: Exception):
        status = 404 if str(error).startswith("unknown ") else 400
        return JSONResponse(status_code=status, content={"detail": str(error), "error": str(error)})

    @app.exception_handler(json.JSONDecodeError)
    @app.exception_handler(OSError)
    async def storage_error(_request: Request, error: Exception):
        return JSONResponse(status_code=500, content={"detail": str(error), "error": str(error)})

    def read():
        return ContributionStore(db_path)

    def write(method, *args):
        # ponytail: One process lock fits the local demo; use DB transactions for multiple workers.
        with write_lock:
            result = getattr(read(), method)(*args)
        return jsonable_encoder(asdict(result), custom_encoder={Decimal: str})

    @app.get("/api/dashboard")
    def dashboard(response: Response):
        response.headers["Cache-Control"] = "no-store"
        return read().dashboard_data("fintech")

    @app.get("/api/projects/{project_id}/dashboard")
    def project_dashboard(project_id: str):
        return read().dashboard_data(project_id)

    @app.get("/api/contributions/{contribution_id}")
    def contribution(contribution_id: str):
        return read().contribution_data(contribution_id)

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
        return write("review_contribution", contribution_id, body.reviewer_id, body.decision,
                     body.note, body.completion, body.support_value, body.quality)

    @app.post("/api/contributions/{contribution_id}/resolve")
    def resolve_dispute(contribution_id: str, body: ResolutionInput):
        return write("resolve_dispute", contribution_id, body.resolved_by, body.resolution,
                     body.completion, body.support_value, body.quality)

    app.mount("/", StaticFiles(directory=ROOT, html=True), name="dashboard")
    return app


app = create_app()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(create_app(args.db), host="127.0.0.1", port=args.port)
