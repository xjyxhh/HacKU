"""SQLite persistence and command-line entry point for Contribution Graph."""

import argparse
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, replace
from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path
from uuid import uuid4

from contribution_engine import (
    Contribution,
    ContributionStatus,
    ContributionType,
    Dispute,
    Evidence,
    EvidenceType,
    Member,
    Project,
    Task,
    Verification,
    VerificationDecision,
    contribution_score,
    score_members,
    validate_contribution,
)


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"cannot serialize {type(value).__name__} to JSON")


def _write(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._load(conn)
                self._conn = conn
                result = method(self, *args, **kwargs)
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise
            finally:
                self._conn = None
                self._load(conn)
    return wrapped


class ContributionStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = None
        with self._connect() as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'projects'").fetchone():
                conn.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
            self._load(conn)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    def _load(self, conn):
        # ponytail: Load the small local dataset as objects; query per project if it grows.
        self.projects = {id: Project(id, name) for id, name in conn.execute("SELECT id, name FROM projects ORDER BY rowid")}
        self.members = {id: Member(id, name) for id, name in conn.execute("SELECT id, name FROM members ORDER BY rowid")}
        for project_id, member_id in conn.execute("SELECT project_id, member_id FROM project_members ORDER BY rowid"):
            self.projects[project_id].member_ids.append(member_id)
        self.tasks = {}
        for id, project_id, name, value, description in conn.execute(
            "SELECT id, project_id, name, task_value, description FROM tasks ORDER BY rowid"
        ):
            self.tasks[id] = Task(id, project_id, name, Decimal(value), description)
            self.projects[project_id].task_ids.append(id)
        self.contributions = {}
        for row in conn.execute("SELECT id, project_id, contributor_id, task_id, type, description, "
                                "completion, quality, support_value, status, helped_member_id, resolution_note "
                                "FROM contributions ORDER BY rowid"):
            id, project_id, contributor_id, task_id, kind, description, completion, quality, support_value, status, helped_member_id, resolution_note = row
            self.contributions[id] = Contribution(
                id, project_id, contributor_id, task_id, ContributionType(kind), description,
                Decimal(completion), Decimal(quality), Decimal(support_value),
                ContributionStatus(status), helped_member_id, resolution_note=resolution_note,
            )
        self.evidence = {}
        for id, contribution_id, submitted_by, kind, reference in conn.execute(
            "SELECT id, contribution_id, submitted_by, kind, reference FROM evidence ORDER BY rowid"
        ):
            self.evidence[id] = Evidence(id, contribution_id, submitted_by, EvidenceType(kind), reference)
            self.contributions[contribution_id].evidence_ids.append(id)
        self.verifications = {
            id: Verification(id, contribution_id, reviewer_id, VerificationDecision(decision), note)
            for id, contribution_id, reviewer_id, decision, note in conn.execute(
                "SELECT id, contribution_id, reviewer_id, decision, note FROM verifications ORDER BY rowid"
            )
        }
        self.disputes = {
            id: Dispute(id, contribution_id, raised_by, reason, resolution, resolved_by)
            for id, contribution_id, raised_by, reason, resolution, resolved_by in conn.execute(
                "SELECT id, contribution_id, raised_by, reason, resolution, resolved_by FROM disputes ORDER BY rowid"
            )
        }

    @_write
    def create_project(self, project_id, name):
        if not project_id or not name.strip() or project_id in self.projects:
            raise ValueError("project id must be new and name must be nonempty")
        project = Project(project_id, name)
        self._conn.execute("INSERT INTO projects (id, name) VALUES (?, ?)", (project_id, name))
        return project

    @_write
    def add_member(self, project_id, member_id, name):
        project = self._project(project_id)
        if not member_id or not name.strip() or member_id in self.members:
            raise ValueError("member id must be new and name must be nonempty")
        member = Member(member_id, name)
        self._conn.execute("INSERT INTO members (id, name) VALUES (?, ?)", (member_id, name))
        self._conn.execute("INSERT INTO project_members (project_id, member_id) VALUES (?, ?)",
                           (project.id, member_id))
        return member

    @_write
    def add_task(self, project_id, task_id, name, task_value, description=""):
        project = self._project(project_id)
        if not task_id or not name.strip() or task_id in self.tasks:
            raise ValueError("task id must be new and name must be nonempty")
        value = Decimal(str(task_value))
        if not value.is_finite() or value < 0:
            raise ValueError("task_value must be a nonnegative finite number")
        task = Task(task_id, project_id, name, value, description)
        self._conn.execute("INSERT INTO tasks (id, project_id, name, task_value, description) VALUES (?, ?, ?, ?, ?)",
                           (task_id, project.id, name, str(value), description))
        return task

    @_write
    def submit_contribution(
        self, project_id, contribution_id, contributor_id, task_id, kind, description,
        completion="1", support_value="0", helped_member_id=None,
    ):
        project = self._project(project_id)
        if not contribution_id or contribution_id in self.contributions:
            raise ValueError("contribution id must be new")
        if not description.strip():
            raise ValueError("description must be nonempty")
        contribution = Contribution(
            contribution_id, project_id, contributor_id, task_id, ContributionType(kind), description,
            completion=Decimal(str(completion)), support_value=Decimal(str(support_value)),
            helped_member_id=helped_member_id,
        )
        validate_contribution(contribution, project, self.members, self.tasks)
        self._conn.execute(
            "INSERT INTO contributions (id, project_id, contributor_id, task_id, type, description, "
            "completion, quality, support_value, status, helped_member_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (contribution.id, project_id, contributor_id, task_id, contribution.type.value, description,
             str(contribution.completion), str(contribution.quality), str(contribution.support_value),
             contribution.status.value, helped_member_id),
        )
        return contribution

    def project_scores(self, project_id):
        project = self._project(project_id)
        contributions = [item for item in self.contributions.values() if item.project_id == project_id]
        return score_members(project, self.members, self.tasks, contributions)

    @_write
    def add_evidence(self, contribution_id, submitted_by, kind, reference):
        contribution = self._contribution(contribution_id)
        self._member(contribution.project_id, submitted_by)
        if not reference.strip():
            raise ValueError("evidence reference must be nonempty")
        evidence = Evidence(uuid4().hex, contribution_id, submitted_by, EvidenceType(kind), reference)
        self._conn.execute("INSERT INTO evidence (id, contribution_id, submitted_by, kind, reference) "
                           "VALUES (?, ?, ?, ?, ?)",
                           (evidence.id, contribution_id, submitted_by, evidence.kind.value, reference))
        return evidence

    @_write
    def review_contribution(
        self, contribution_id, reviewer_id, decision, note="", completion=None,
        support_value=None, quality=None,
    ):
        contribution = self._contribution(contribution_id)
        project = self._project(contribution.project_id)
        self._member(project.id, reviewer_id)
        decision = VerificationDecision(decision)
        if decision != VerificationDecision.DISPUTE and reviewer_id == contribution.contributor_id:
            raise ValueError("reviewer cannot verify their own contribution")
        changes = self._score_changes(completion, support_value, quality)
        if decision == VerificationDecision.DISPUTE:
            if contribution.status not in (ContributionStatus.PENDING, ContributionStatus.VERIFIED):
                raise ValueError("only pending or verified contributions can be disputed")
            if not note.strip() or changes:
                raise ValueError("dispute requires a reason and no score changes")
            updated = replace(contribution, status=ContributionStatus.DISPUTED)
        else:
            if contribution.status != ContributionStatus.PENDING:
                raise ValueError("only pending contributions can be verified")
            if (decision == VerificationDecision.CONFIRM and changes) or (decision == VerificationDecision.ADJUST and not changes):
                raise ValueError("CONFIRM takes no changes; ADJUST requires a score change")
            updated = replace(contribution, status=ContributionStatus.VERIFIED, **changes)
            validate_contribution(updated, project, self.members, self.tasks)
            if decision == VerificationDecision.ADJUST:
                proposed = replace(contribution, status=ContributionStatus.VERIFIED)
                if contribution_score(updated, project, self.members, self.tasks) == contribution_score(
                    proposed, project, self.members, self.tasks
                ):
                    raise ValueError("ADJUST requires a score change")
        verification = Verification(uuid4().hex, contribution_id, reviewer_id, decision, note)
        self._conn.execute("UPDATE contributions SET status = ?, completion = ?, quality = ?, support_value = ? "
                           "WHERE id = ?",
                           (updated.status.value, str(updated.completion), str(updated.quality),
                            str(updated.support_value), contribution_id))
        self._conn.execute("INSERT INTO verifications (id, contribution_id, reviewer_id, decision, note) "
                           "VALUES (?, ?, ?, ?, ?)",
                           (verification.id, contribution_id, reviewer_id, decision.value, note))
        if decision == VerificationDecision.DISPUTE:
            dispute = Dispute(uuid4().hex, contribution_id, reviewer_id, note)
            self._conn.execute("INSERT INTO disputes (id, contribution_id, raised_by, reason) VALUES (?, ?, ?, ?)",
                               (dispute.id, contribution_id, reviewer_id, note))
        return updated

    @_write
    def resolve_dispute(
        self, contribution_id, resolved_by, resolution, completion=None,
        support_value=None, quality=None,
    ):
        contribution = self._contribution(contribution_id)
        project = self._project(contribution.project_id)
        self._member(project.id, resolved_by)
        if resolved_by == contribution.contributor_id:
            raise ValueError("member cannot resolve their own contribution")
        if contribution.status != ContributionStatus.DISPUTED:
            raise ValueError("only disputed contributions can be resolved")
        if not resolution.strip():
            raise ValueError("resolution must be nonempty")
        dispute = next((item for item in reversed(list(self.disputes.values()))
                        if item.contribution_id == contribution_id and item.resolution is None), None)
        if dispute is None:
            raise ValueError("no open dispute for contribution")
        changes = self._score_changes(completion, support_value, quality)
        updated = replace(contribution, status=ContributionStatus.RESOLVED,
                          resolution_note=resolution, **changes)
        validate_contribution(updated, project, self.members, self.tasks)
        self._conn.execute("UPDATE contributions SET status = ?, completion = ?, quality = ?, "
                           "support_value = ?, resolution_note = ? WHERE id = ?",
                           (updated.status.value, str(updated.completion), str(updated.quality),
                            str(updated.support_value), resolution, contribution_id))
        self._conn.execute("UPDATE disputes SET resolution = ?, resolved_by = ? WHERE id = ?",
                           (resolution, resolved_by, dispute.id))
        return updated

    def dashboard_data(self, project_id):
        project = self._project(project_id)
        contributions = [item for item in self.contributions.values() if item.project_id == project_id]
        scores = score_members(project, self.members, self.tasks, contributions)
        records = []
        for item in contributions:
            records.append({
                "id": item.id,
                "contributorId": item.contributor_id,
                "taskId": item.task_id,
                "type": item.type.value,
                "description": item.description,
                "helpedMemberId": item.helped_member_id,
                "status": item.status.value,
                "score": float(contribution_score(item, project, self.members, self.tasks)),
            })
        relationships = [
            {
                "contributionId": item["id"],
                "fromMemberId": item["contributorId"],
                "toMemberId": item["helpedMemberId"],
                "taskId": item["taskId"],
                "type": item["type"],
                "status": item["status"],
                "score": item["score"],
            }
            for item in records if item["helpedMemberId"] is not None
        ]
        return {
            "project": {"id": project.id, "name": project.name},
            "members": [{
                "id": member_id,
                "name": self.members[member_id].name,
                "totalScore": float(scores[member_id].total_score),
                "contributionShare": float(scores[member_id].contribution_share),
                "breakdown": {kind.value: float(value) for kind, value in scores[member_id].breakdown.items()},
            } for member_id in project.member_ids],
            "tasks": [
                {"id": task_id, "name": self.tasks[task_id].name,
                 "taskValue": float(self.tasks[task_id].task_value),
                 "description": self.tasks[task_id].description}
                for task_id in project.task_ids
            ],
            "contributions": records,
            "relationships": relationships,
        }

    def contribution_data(self, contribution_id):
        contribution = self._contribution(contribution_id)
        task = self.tasks[contribution.task_id]
        record = asdict(contribution)
        record.update(type=contribution.type.value, status=contribution.status.value,
                      completion=str(contribution.completion), quality=str(contribution.quality),
                      support_value=str(contribution.support_value))
        return {
            "contribution": record,
            "task": {"id": task.id, "name": task.name, "taskValue": str(task.task_value)},
            "currentScore": float(contribution_score(
                contribution, self._project(contribution.project_id), self.members, self.tasks)),
            "proposedScore": self.preview_score(contribution_id)["proposedScore"],
            "evidence": [asdict(item) for item in self.evidence.values()
                         if item.contribution_id == contribution_id],
            "verifications": [asdict(item) for item in self.verifications.values()
                              if item.contribution_id == contribution_id],
            "disputes": [asdict(item) for item in self.disputes.values()
                         if item.contribution_id == contribution_id],
        }

    def preview_score(self, contribution_id, completion=None, support_value=None, quality=None):
        """Calculate proposed scores on copies, without changing status or saving data."""
        contribution = self._contribution(contribution_id)
        project = self._project(contribution.project_id)
        proposed = replace(contribution, status=ContributionStatus.VERIFIED)
        updated = replace(proposed, **self._score_changes(completion, support_value, quality))
        before = contribution_score(proposed, project, self.members, self.tasks)
        after = contribution_score(updated, project, self.members, self.tasks)
        return {
            "currentScore": float(contribution_score(contribution, project, self.members, self.tasks)),
            "proposedScore": float(before),
            "updatedScore": float(after),
            "scoreChanged": before != after,
        }

    @staticmethod
    def _score_changes(completion, support_value, quality):
        values = {"completion": completion, "support_value": support_value, "quality": quality}
        changes = {key: Decimal(str(value)) for key, value in values.items() if value is not None}
        if any(not value.is_finite() for value in changes.values()):
            raise ValueError("numeric values must be finite")
        return changes

    def _contribution(self, contribution_id):
        try:
            return self.contributions[contribution_id]
        except KeyError:
            raise ValueError(f"unknown contribution: {contribution_id}") from None

    def _member(self, project_id, member_id):
        if member_id not in self._project(project_id).member_ids or member_id not in self.members:
            raise ValueError("member is not part of the project")

    def _project(self, project_id):
        try:
            return self.projects[project_id]
        except KeyError:
            raise ValueError(f"unknown project: {project_id}") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(Path(__file__).with_name("data.sqlite3")), help="SQLite database file")
    commands = parser.add_subparsers(dest="command", required=True)
    project = commands.add_parser("create-project")
    project.add_argument("id")
    project.add_argument("name")
    member = commands.add_parser("add-member")
    member.add_argument("project_id")
    member.add_argument("id")
    member.add_argument("name")
    task = commands.add_parser("add-task")
    task.add_argument("project_id")
    task.add_argument("id")
    task.add_argument("name")
    task.add_argument("task_value")
    task.add_argument("--description", default="")
    contribution = commands.add_parser("submit")
    contribution.add_argument("project_id")
    contribution.add_argument("id")
    contribution.add_argument("contributor_id")
    contribution.add_argument("task_id")
    contribution.add_argument("type", choices=[kind.value for kind in ContributionType])
    contribution.add_argument("description")
    contribution.add_argument("--completion", default="1")
    contribution.add_argument("--support-value", default="0")
    contribution.add_argument("--helped-member")
    evidence = commands.add_parser("add-evidence")
    evidence.add_argument("contribution_id")
    evidence.add_argument("submitted_by")
    evidence.add_argument("kind", choices=[kind.value for kind in EvidenceType])
    evidence.add_argument("reference")
    review = commands.add_parser("review")
    review.add_argument("contribution_id")
    review.add_argument("reviewer_id")
    review.add_argument("decision", choices=[decision.value for decision in VerificationDecision])
    review.add_argument("--note", default="")
    resolve = commands.add_parser("resolve")
    resolve.add_argument("contribution_id")
    resolve.add_argument("resolved_by")
    resolve.add_argument("resolution")
    for command in (review, resolve):
        command.add_argument("--completion")
        command.add_argument("--support-value")
        command.add_argument("--quality")
    scores = commands.add_parser("scores")
    scores.add_argument("project_id")
    dashboard = commands.add_parser("dashboard")
    dashboard.add_argument("project_id")
    record = commands.add_parser("record")
    record.add_argument("contribution_id")
    args = parser.parse_args()
    store = ContributionStore(args.db)
    try:
        if args.command == "create-project":
            result = store.create_project(args.id, args.name)
        elif args.command == "add-member":
            result = store.add_member(args.project_id, args.id, args.name)
        elif args.command == "add-task":
            result = store.add_task(args.project_id, args.id, args.name, args.task_value, args.description)
        elif args.command == "submit":
            result = store.submit_contribution(
                args.project_id, args.id, args.contributor_id, args.task_id, args.type,
                args.description, args.completion, args.support_value, args.helped_member,
            )
        elif args.command == "add-evidence":
            result = store.add_evidence(args.contribution_id, args.submitted_by, args.kind, args.reference)
        elif args.command == "review":
            result = store.review_contribution(args.contribution_id, args.reviewer_id, args.decision,
                                               args.note, args.completion, args.support_value, args.quality)
        elif args.command == "resolve":
            result = store.resolve_dispute(args.contribution_id, args.resolved_by, args.resolution,
                                           args.completion, args.support_value, args.quality)
        elif args.command == "dashboard":
            result = store.dashboard_data(args.project_id)
        elif args.command == "record":
            result = store.contribution_data(args.contribution_id)
        else:
            result = {key: asdict(value) for key, value in store.project_scores(args.project_id).items()}
        print(json.dumps(result if isinstance(result, dict) else asdict(result),
                         ensure_ascii=False, indent=2, default=_json_default))
    except (ValueError, InvalidOperation) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
