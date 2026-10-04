"""SQLite persistence and command-line entry point for group contribution ledger."""

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
from token_engine import (
    ContractStatus,
    LedgerEventType,
    TokenLedger,
    TokenProject,
    TokenTask,
    ValueType,
)


ZERO = Decimal("0")

# Legacy contribution types that describe produced value. SUPPORT is not a value
# type: in the token model it is commissioned production (see integration-guide.md).
TOKEN_VALUE_TYPES = {
    ContributionType.CORE: ValueType.CORE,
    ContributionType.REVIEW: ValueType.REVIEW,
    ContributionType.COORDINATION: ValueType.COORDINATION,
}


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
                project_id = None
                if method.__name__ != "create_project" and args:
                    if method.__name__ in {"add_member", "add_task", "submit_contribution"}:
                        project_id = args[0]
                    else:
                        row=conn.execute("SELECT project_id FROM contributions WHERE id=?",(args[0],)).fetchone()
                        project_id=row[0] if row else None
                if project_id and conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_lifecycle'").fetchone():
                    lifecycle=conn.execute("SELECT state FROM project_lifecycle WHERE project_id=?",(project_id,)).fetchone()
                    if lifecycle and lifecycle[0] != "ACTIVE":
                        raise ValueError("project is archived")
                result = method(self, *args, **kwargs)
                project_id = project_id or None
                if method.__name__ == "create_project":
                    project_id = args[0]
                elif method.__name__ in {"add_member", "add_task", "submit_contribution"}:
                    project_id = args[0]
                elif args:
                    contribution_id = args[0]
                    row = conn.execute("SELECT project_id FROM contributions WHERE id=?", (contribution_id,)).fetchone()
                    project_id = row[0] if row else None
                if project_id and conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_versions'").fetchone():
                    conn.execute("INSERT INTO project_versions(project_id,version) VALUES(?,2) ON CONFLICT(project_id) DO UPDATE SET version=project_versions.version+1", (project_id,))
                    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_lifecycle'").fetchone():
                        conn.execute("UPDATE project_lifecycle SET version=version+1 WHERE project_id=?", (project_id,))
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
    def __init__(self, path, read_only: bool = False):
        self.path = Path(path)
        self.read_only = read_only
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = None
        with self._connect() as conn:
            if read_only and not conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'projects'").fetchone():
                raise ValueError(f"no contribution data in {self.path}")
            if not read_only and not conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'projects'").fetchone():
                conn.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
            conn.execute("BEGIN")
            self._load(conn)

    @contextmanager
    def _connect(self):
        if self.read_only:
            conn = sqlite3.connect(f"file:{self.path.resolve()}?mode=ro", uri=True, timeout=10)
        else:
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

    def validate_integrity(self):
        """Check imported or merged rows against the same rules as API writes."""
        for task in self.tasks.values():
            if not task.task_value.is_finite() or not ZERO <= task.task_value <= Decimal("1000000000000"):
                raise ValueError("task_value must be a nonnegative finite number within the supported range")
        for item in self.contributions.values():
            validate_contribution(item, self.projects[item.project_id], self.members, self.tasks)
        for evidence in self.evidence.values():
            item = self.contributions[evidence.contribution_id]
            if evidence.submitted_by not in self.projects[item.project_id].member_ids:
                raise ValueError("evidence submitter is not a project member")
            if len(evidence.reference) > 4096:
                raise ValueError("evidence reference exceeds 4096 characters")
        for verification in self.verifications.values():
            item = self.contributions[verification.contribution_id]
            if verification.reviewer_id not in self.projects[item.project_id].member_ids:
                raise ValueError("reviewer is not a project member")
            if (verification.decision != VerificationDecision.DISPUTE
                    and verification.reviewer_id == item.contributor_id):
                raise ValueError("reviewer cannot verify their own contribution")

    @_write
    def create_project(self, project_id, name):
        if not project_id.strip() or not name.strip() or project_id in self.projects:
            raise ValueError("project id must be new and name must be nonempty")
        project = Project(project_id, name)
        self._conn.execute("INSERT INTO projects (id, name) VALUES (?, ?)", (project_id, name))
        if self._conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_lifecycle'").fetchone():
            self._conn.execute("INSERT OR IGNORE INTO project_lifecycle(project_id) VALUES(?)",(project_id,))
        return project

    @_write
    def add_member(self, project_id, member_id, name):
        project = self._project(project_id)
        if not member_id.strip() or not name.strip() or member_id in project.member_ids:
            raise ValueError("member id must be new and name must be nonempty")
        member = self.members.get(member_id)
        if member is None:
            member = Member(member_id, name)
            self._conn.execute("INSERT INTO members (id, name) VALUES (?, ?)", (member_id, name))
        elif member.name != name:
            joined = self._conn.execute("SELECT 1 FROM project_members WHERE member_id=? LIMIT 1", (member_id,)).fetchone()
            if joined:
                raise ValueError("existing member id has a different name")
            self._conn.execute("UPDATE members SET name=? WHERE id=?", (name, member_id))
            member = Member(member_id, name)
        self._conn.execute("INSERT INTO project_members (project_id, member_id) VALUES (?, ?)",
                           (project.id, member_id))
        if self._conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_membership_state'").fetchone():
            self._conn.execute("INSERT OR IGNORE INTO project_membership_state(project_id,member_id) VALUES(?,?)",(project.id,member_id))
        return member

    @_write
    def add_task(self, project_id, task_id, name, task_value, description=""):
        project = self._project(project_id)
        if not task_id.strip() or not name.strip() or task_id in self.tasks:
            raise ValueError("task id must be new and name must be nonempty")
        value = Decimal(str(task_value))
        if not value.is_finite() or not ZERO <= value <= Decimal("1000000000000"):
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
        if not contribution_id.strip() or contribution_id in self.contributions:
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
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='contribution_withdrawals'").fetchone():
                withdrawn={row[0] for row in conn.execute("SELECT contribution_id FROM contribution_withdrawals")}
                contributions=[item for item in contributions if item.id not in withdrawn]
        return score_members(project, self.members, self.tasks, contributions)

    @_write
    def add_evidence(self, contribution_id, submitted_by, kind, reference):
        contribution = self._contribution(contribution_id)
        self._member(contribution.project_id, submitted_by)
        if not reference.strip() or len(reference) > 4096:
            raise ValueError("evidence reference must be nonempty and at most 4096 characters")
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
        with self._connect() as conn:
            withdrawn = {row[0] for row in conn.execute(
                "SELECT contribution_id FROM contribution_withdrawals"
            )} if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='contribution_withdrawals'").fetchone() else set()
            requests = {row[0]: {"id": row[1], "applicantId": row[2], "reason": row[3], "state": row[4]}
                        for row in conn.execute("SELECT contribution_id,id,applicant_id,reason,state FROM contribution_unwind_requests WHERE state='PENDING'")} if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='contribution_unwind_requests'").fetchone() else {}
            request_history = {}
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='contribution_unwind_requests'").fetchone():
                for row in conn.execute("SELECT contribution_id,id,applicant_id,reason,state,reviewer_id,decision_note FROM contribution_unwind_requests ORDER BY rowid"):
                    request_history[row[0]] = {"id":row[1],"applicantId":row[2],"reason":row[3],"state":row[4],"reviewerId":row[5],"decisionNote":row[6]}
            member_states = {row[0]: row[1] for row in conn.execute("SELECT member_id,state FROM project_membership_state WHERE project_id=?",(project_id,))} if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_membership_state'").fetchone() else {}
            exit_requests = {row[1]: {"id":row[0],"reason":row[2],"state":row[3],"contributionIds":json.loads(row[4] or "[]")}
                             for row in conn.execute("SELECT id,member_id,reason,state,contribution_ids_snapshot FROM membership_exit_requests WHERE project_id=? AND state='PENDING'",(project_id,))} if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='membership_exit_requests'").fetchone() else {}
        scores = score_members(project, self.members, self.tasks,
                               [item for item in contributions if item.id not in withdrawn])
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
                "score": 0.0 if item.id in withdrawn else float(contribution_score(item, project, self.members, self.tasks)),
                "withdrawalState": "WITHDRAWN" if item.id in withdrawn else "ACTIVE",
                "unwindRequest": requests.get(item.id),
                "latestUnwindRequest": request_history.get(item.id),
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
                "withdrawalState": item["withdrawalState"],
            }
            for item in records if item["helpedMemberId"] is not None
        ]
        return {
            "project": {"id": project.id, "name": project.name},
            "members": [{
                "id": member_id,
                "name": self.members[member_id].name,
                "membershipState": member_states.get(member_id,"ACTIVE"),
                "exitRequest": exit_requests.get(member_id),
                "totalScore": float(scores[member_id].total_score),
                "totalScoreExact": str(scores[member_id].total_score),
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
            # Additive stage-1 token projection; legacy fields above are unchanged.
            "balances": self.token_view(project_id)["balances"],
        }

    def contribution_data(self, contribution_id):
        contribution = self._contribution(contribution_id)
        task = self.tasks[contribution.task_id]
        record = asdict(contribution)
        record.update(type=contribution.type.value, status=contribution.status.value,
                      completion=str(contribution.completion), quality=str(contribution.quality),
                      support_value=str(contribution.support_value))
        original_score=contribution_score(contribution,self._project(contribution.project_id),self.members,self.tasks)
        withdrawal=None
        if self._conn is not None:
            row=self._conn.execute("SELECT r.id,r.applicant_id,r.reason,r.state,r.reviewer_id,r.decision_note,w.effective_at FROM contribution_withdrawals w JOIN contribution_unwind_requests r ON r.id=w.request_id WHERE w.contribution_id=?",(contribution_id,)).fetchone() if self._conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='contribution_withdrawals'").fetchone() else None
        else:
            with self._connect() as conn:
                row=conn.execute("SELECT r.id,r.applicant_id,r.reason,r.state,r.reviewer_id,r.decision_note,w.effective_at FROM contribution_withdrawals w JOIN contribution_unwind_requests r ON r.id=w.request_id WHERE w.contribution_id=?",(contribution_id,)).fetchone() if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='contribution_withdrawals'").fetchone() else None
        if row: withdrawal={"requestId":row[0],"applicantId":row[1],"reason":row[2],"state":row[3],"reviewerId":row[4],"decisionNote":row[5],"effectiveAt":row[6]}
        return {
            "contribution": record,
            "task": {"id": task.id, "name": task.name, "taskValue": str(task.task_value)},
            "currentScore": 0.0 if withdrawal else float(original_score),
            "currentScoreExact": "0" if withdrawal else str(original_score),
            "originalScore": float(original_score),
            "originalScoreExact": str(original_score),
            "withdrawal": withdrawal,
            "tokenMintEventId": (
                f"{contribution.id}:commission:mint"
                if contribution.type == ContributionType.SUPPORT and contribution.helped_member_id
                and self._legacy_token_approver(contribution)
                else f"{contribution.id}:mint"
            ),
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

    # --- Stage 1: read-only projection of stored contributions into the token model ---
    # This never writes to SQLite. It exists so the legacy scores and the token
    # balances can be compared on the same data before any migration. See integration-guide.md.
    TOKEN_PROJECTION_ASSUMPTIONS = (
        "Project VERIFIED / RESOLVED contributions only; PENDING / DISPUTED records are unscored and listed in skipped.",
        "Direct: mint each previous CORE / REVIEW / COORDINATION score to its contributor.",
        "Commissioned: map SUPPORT with a real independent reviewer to a commission; otherwise mint the verified contribution directly without inventing approval.",
        "The legacy commission has no separate result valuation: verifiedMintValue = contractPrice; mint P to the principal, then transfer P to the contractor.",
        "Set task mintCap to max(task_value, projected task mint total) so legacy restatement is accepted; enforce actual caps in phase two.",
        "The projection synthesizes <project_id>-treasury; legacy data has no treasury.",
        "Use legacy:<contribution_id> as the evidence idempotency key; phase one does not deduplicate evidence references.",
    )

    def token_view(self, project_id):
        """Project stored contributions into the token model without changing any data."""
        project = self._project(project_id)
        items = [item for item in self.contributions.values() if item.project_id == project_id]
        with self._connect() as conn:
            withdrawn={row[0] for row in conn.execute("SELECT contribution_id FROM contribution_withdrawals")} if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='contribution_withdrawals'").fetchone() else set()
        scores = score_members(project, self.members, self.tasks, [item for item in items if item.id not in withdrawn])

        planned = []
        skipped = []
        mint_totals = {task_id: ZERO for task_id in project.task_ids}
        for item in items:
            if item.id in withdrawn:
                skipped.append(self._token_skip(item,"Contribution withdrawn; no further minting"))
                continue
            amount = contribution_score(item, project, self.members, self.tasks)
            if item.status not in (ContributionStatus.VERIFIED, ContributionStatus.RESOLVED):
                skipped.append(self._token_skip(item, f"Status {item.status.value} Not scored"))
                continue
            if amount <= ZERO:
                skipped.append(self._token_skip(item, "Effective score is 0; no Tokens can be minted."))
                continue
            if item.type == ContributionType.SUPPORT:
                commissioned = item.helped_member_id and self._legacy_token_approver(item)
                planned.append((item, "COMMISSION" if commissioned else "DIRECT", amount))
            else:
                planned.append((item, "DIRECT", amount))
            mint_totals[item.task_id] += amount

        ledger = TokenLedger(TokenProject(
            project.id, project.name, f"{project.id}-treasury", tuple(project.member_ids),
        ))
        for task_id in project.task_ids:
            task = self.tasks[task_id]
            ledger.add_task(TokenTask(
                task.id, project.id, task.name, self._token_value_type(items, task_id),
                max(task.task_value, mint_totals[task_id]),
                task.description.strip() or task.name,
            ))

        for item, kind, amount in planned:
            try:
                if kind == "DIRECT":
                    ledger.mint_direct(f"{item.id}:mint", item.task_id, item.contributor_id, amount,
                                       [f"legacy:{item.id}"])
                else:
                    self._project_commission(ledger, item, amount)
            except ValueError as error:
                ledger.contracts.pop(f"{item.id}:commission", None)
                skipped.append(self._token_skip(item, str(error)))

        return self._token_view_payload(project, ledger, scores, skipped)

    @staticmethod
    def _token_skip(contribution, reason):
        return {
            "contributionId": contribution.id,
            "contributorId": contribution.contributor_id,
            "type": contribution.type.value,
            "status": contribution.status.value,
            "reason": reason,
        }

    @staticmethod
    def _token_value_type(items, task_id):
        for item in items:
            if item.task_id == task_id and item.type in TOKEN_VALUE_TYPES:
                return TOKEN_VALUE_TYPES[item.type]
        return ValueType.CORE

    def _legacy_token_approver(self, contribution):
        excluded = {contribution.contributor_id, contribution.helped_member_id}
        project = self.projects[contribution.project_id]
        actors = [entry.resolved_by for entry in reversed(list(self.disputes.values()))
                  if entry.contribution_id == contribution.id and entry.resolved_by]
        actors += [entry.reviewer_id for entry in reversed(list(self.verifications.values()))
                   if entry.contribution_id == contribution.id
                   and entry.decision in (VerificationDecision.CONFIRM, VerificationDecision.ADJUST)]
        return next((actor for actor in actors
                     if actor in project.member_ids and actor not in excluded), None)

    def _project_commission(self, ledger, contribution, amount):
        """Replay one legacy SUPPORT contribution as a settled commission contract."""
        contract_id = f"{contribution.id}:commission"
        principal, contractor = contribution.helped_member_id, contribution.contributor_id
        key = [f"legacy:{contribution.id}"]
        ledger.create_commission(contract_id, contribution.task_id, principal, contractor, amount, amount)
        for status in (ContractStatus.OFFERED, ContractStatus.ACCEPTED, ContractStatus.CREDIT_RESERVED,
                       ContractStatus.DELIVERED, ContractStatus.VERIFIED):
            ledger.advance_contract(contract_id, status)
        ledger.settle_commission(contract_id, amount, key,
                                 [self._legacy_token_approver(contribution)])

    def _token_view_payload(self, project, ledger, scores, skipped):
        minted = {member_id: ZERO for member_id in project.member_ids}
        paid = {member_id: ZERO for member_id in project.member_ids}
        received = {member_id: ZERO for member_id in project.member_ids}
        for event in ledger.events:
            if event.kind == LedgerEventType.MINT:
                minted[event.destination_id] += event.amount
            elif event.kind == LedgerEventType.TRANSFER:
                paid[event.source_id] += event.amount
                received[event.destination_id] += event.amount
        graph = ledger.graph()
        return {
            "project": {"id": project.id, "name": project.name,
                        "treasuryId": ledger.project.treasury_id},
            "assumptions": list(self.TOKEN_PROJECTION_ASSUMPTIONS),
            "oldScores": [{
                "memberId": member_id,
                "totalScore": float(scores[member_id].total_score),
                "totalScoreExact": str(scores[member_id].total_score),
                "contributionShare": float(scores[member_id].contribution_share),
                "breakdown": {kind.value: float(value) for kind, value in scores[member_id].breakdown.items()},
            } for member_id in project.member_ids],
            "balances": [{
                "memberId": member_id,
                "name": self.members[member_id].name,
                "minted": float(minted[member_id]),
                "mintedExact": str(minted[member_id]),
                "paid": float(paid[member_id]),
                "paidExact": str(paid[member_id]),
                "received": float(received[member_id]),
                "receivedExact": str(received[member_id]),
                "balance": float(ledger.balance(member_id)),
                "balanceExact": str(ledger.balance(member_id)),
            } for member_id in project.member_ids],
            "totalSupply": float(ledger.total_supply()),
            "totalSupplyExact": str(ledger.total_supply()),
            "oldTeamTotal": float(sum((scores[member_id].total_score for member_id in project.member_ids), ZERO)),
            "oldTeamTotalExact": str(sum((scores[member_id].total_score for member_id in project.member_ids), ZERO)),
            "tasks": [{
                "id": task_id,
                "name": self.tasks[task_id].name,
                "valueType": ledger.tasks[task_id].value_type.value,
                "mintCap": float(ledger.tasks[task_id].mint_cap),
                "mintCapExact": str(ledger.tasks[task_id].mint_cap),
                "budget": {key: float(value) for key, value in ledger.task_budget(task_id).items()},
                "budgetExact": {key: str(value) for key, value in ledger.task_budget(task_id).items()},
            } for task_id in project.task_ids],
            "contracts": [{
                "id": item.id,
                "taskId": item.task_id,
                "principalId": item.principal_id,
                "contractorId": item.contractor_id,
                "contractPrice": float(item.contract_price),
                "contractPriceExact": str(item.contract_price),
                "maximumMintValue": float(item.maximum_mint_value),
                "maximumMintValueExact": str(item.maximum_mint_value),
                "status": item.status.value,
                "approverIds": list(item.approver_ids),
                "verifiedMintValue": (float(item.verified_mint_value)
                                      if item.verified_mint_value is not None else None),
                "verifiedMintValueExact": (str(item.verified_mint_value)
                                           if item.verified_mint_value is not None else None),
            } for item in ledger.contracts.values()],
            "events": [{
                "sequence": item.sequence,
                "id": item.id,
                "kind": item.kind.value,
                "amount": float(item.amount),
                "amountExact": str(item.amount),
                "sourceId": item.source_id,
                "destinationId": item.destination_id,
                "taskId": item.task_id,
                "contractId": item.contract_id,
                "note": item.note,
            } for item in ledger.events],
            "graph": {
                "nodes": [{"address": list(node.address), "kind": node.kind, "label": node.label}
                          for node in graph.nodes],
                "edges": [{"address": list(edge.address), "kind": edge.kind,
                           "source": list(edge.source), "destination": list(edge.destination),
                           "amount": float(edge.amount) if edge.amount is not None else None,
                           "amountExact": str(edge.amount) if edge.amount is not None else None}
                          for edge in graph.edges],
            },
            "skipped": skipped,
        }

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
    token = commands.add_parser("token-view")
    token.add_argument("project_id")
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
        elif args.command == "token-view":
            result = store.token_view(args.project_id)
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
