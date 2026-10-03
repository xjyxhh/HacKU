"""Minimal data model and deterministic score engine for Contribution Graph."""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class ContributionType(str, Enum):
    CORE = "CORE"
    SUPPORT = "SUPPORT"
    REVIEW = "REVIEW"
    COORDINATION = "COORDINATION"


class ContributionStatus(str, Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    DISPUTED = "DISPUTED"
    RESOLVED = "RESOLVED"


class VerificationDecision(str, Enum):
    CONFIRM = "CONFIRM"
    ADJUST = "ADJUST"
    DISPUTE = "DISPUTE"


class EvidenceType(str, Enum):
    NOTE = "NOTE"
    URL = "URL"
    IMAGE = "IMAGE"
    GITHUB_PR = "GITHUB_PR"


@dataclass
class Project:
    id: str
    name: str
    member_ids: list[str] = field(default_factory=list)
    task_ids: list[str] = field(default_factory=list)


@dataclass
class Member:
    id: str
    name: str


@dataclass
class Task:
    id: str
    project_id: str
    name: str
    task_value: Decimal
    description: str = ""


@dataclass
class Evidence:
    id: str
    contribution_id: str
    submitted_by: str
    kind: EvidenceType
    reference: str


@dataclass
class Verification:
    id: str
    contribution_id: str
    reviewer_id: str
    decision: VerificationDecision
    note: str = ""


@dataclass
class Dispute:
    id: str
    contribution_id: str
    raised_by: str
    reason: str
    resolution: str | None = None
    resolved_by: str | None = None


@dataclass
class Contribution:
    id: str
    project_id: str
    contributor_id: str
    task_id: str
    type: ContributionType
    description: str
    completion: Decimal = Decimal("1")
    quality: Decimal = Decimal("1")
    # Proposed while PENDING; final only after verification or resolution.
    support_value: Decimal = Decimal("0")
    status: ContributionStatus = ContributionStatus.PENDING
    helped_member_id: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    # Verification/dispute fields are optional; RESOLVED scores use the finalized values above.
    resolution_note: str | None = None


@dataclass
class MemberScore:
    member_id: str
    total_score: Decimal
    contribution_share: Decimal
    breakdown: dict[ContributionType, Decimal]


def validate_contribution(
    contribution: Contribution, project: Project, members: dict[str, Member], tasks: dict[str, Task]
) -> None:
    """Check references and scoring inputs before a contribution is scored."""
    if not isinstance(contribution.type, ContributionType):
        raise ValueError("invalid contribution type")
    if not isinstance(contribution.status, ContributionStatus):
        raise ValueError("invalid contribution status")
    if contribution.project_id != project.id:
        raise ValueError("contribution belongs to another project")
    if contribution.contributor_id not in project.member_ids or contribution.contributor_id not in members:
        raise ValueError("contributor is not a project member")
    if contribution.helped_member_id is not None:
        if contribution.helped_member_id not in project.member_ids or contribution.helped_member_id not in members:
            raise ValueError("helped member is not a project member")
        if contribution.helped_member_id == contribution.contributor_id:
            raise ValueError("contributor cannot help themselves")
    task = tasks.get(contribution.task_id)
    if task is None or task.id not in project.task_ids or task.project_id != project.id:
        raise ValueError("task is not part of the project")
    if not task.task_value.is_finite() or task.task_value < 0:
        raise ValueError("task_value must be a nonnegative finite number")
    if not contribution.completion.is_finite() or not Decimal("0") <= contribution.completion <= Decimal("1"):
        raise ValueError("completion must be between 0 and 1")
    if not contribution.quality.is_finite() or not Decimal("0.9") <= contribution.quality <= Decimal("1.1"):
        raise ValueError("quality must be between 0.9 and 1.1")
    if not contribution.support_value.is_finite() or contribution.support_value < 0:
        raise ValueError("support_value must be a nonnegative finite number")
    if contribution.type == ContributionType.CORE and contribution.support_value:
        raise ValueError("CORE contribution cannot include support_value")


def contribution_score(
    contribution: Contribution, project: Project, members: dict[str, Member], tasks: dict[str, Task]
) -> Decimal:
    """Score verified work using the formula for its contribution type."""
    validate_contribution(contribution, project, members, tasks)
    if contribution.status not in (ContributionStatus.VERIFIED, ContributionStatus.RESOLVED):
        return Decimal("0")
    if contribution.type == ContributionType.CORE:
        return tasks[contribution.task_id].task_value * contribution.completion * contribution.quality
    return contribution.support_value * contribution.quality


def score_members(
    project: Project, members: dict[str, Member], tasks: dict[str, Task], contributions: list[Contribution]
) -> dict[str, MemberScore]:
    """Compute totals, category breakdowns, and shares from current contribution states."""
    if any(member_id not in members for member_id in project.member_ids):
        raise ValueError("project contains an unknown member")
    totals = {member_id: Decimal("0") for member_id in project.member_ids}
    breakdowns = {member_id: {kind: Decimal("0") for kind in ContributionType} for member_id in project.member_ids}
    for contribution in contributions:
        score = contribution_score(contribution, project, members, tasks)
        totals[contribution.contributor_id] += score
        breakdowns[contribution.contributor_id][contribution.type] += score
    team_total = sum(totals.values(), Decimal("0"))
    return {
        member_id: MemberScore(
            member_id,
            totals[member_id],
            (totals[member_id] / team_total * 100).quantize(Decimal("0.01")) if team_total else Decimal("0.00"),
            breakdowns[member_id],
        )
        for member_id in project.member_ids
    }


def demo_data():
    members = {mid: Member(mid, name) for mid, name in (("alice", "Alice"), ("bob", "Bob"), ("charlie", "Charlie"), ("david", "David"))}
    tasks = {
        task.id: task for task in (
            Task("recommendation", "fintech", "Recommendation Engine", Decimal("40")),
            Task("dashboard", "fintech", "Frontend Dashboard", Decimal("25")),
            Task("deployment", "fintech", "Deployment", Decimal("20")),
            Task("demo", "fintech", "Demo Preparation", Decimal("15")),
        )
    }
    project = Project("fintech", "FinTech Contribution Graph", list(members), list(tasks))
    contributions = [
        Contribution("c1", "fintech", "alice", "recommendation", ContributionType.CORE, "Built recommendation logic", status=ContributionStatus.VERIFIED),
        Contribution("c2", "fintech", "bob", "dashboard", ContributionType.CORE, "Built dashboard", completion=Decimal("0.8"), status=ContributionStatus.VERIFIED),
        Contribution("c3", "fintech", "charlie", "recommendation", ContributionType.REVIEW, "Reviewed ranking behavior", support_value=Decimal("3"), status=ContributionStatus.PENDING),
        Contribution("c4", "fintech", "david", "deployment", ContributionType.SUPPORT, "Helped debug deployment", support_value=Decimal("8"), helped_member_id="alice", status=ContributionStatus.RESOLVED, resolution_note="Confirmed by helped member"),
        Contribution("c5", "fintech", "david", "demo", ContributionType.COORDINATION, "Coordinated demo", status=ContributionStatus.DISPUTED),
    ]
    return project, members, tasks, contributions


if __name__ == "__main__":
    demo_project, demo_members, demo_tasks, demo_contributions = demo_data()
    scores = score_members(demo_project, demo_members, demo_tasks, demo_contributions)
    assert contribution_score(demo_contributions[0], demo_project, demo_members, demo_tasks) == Decimal("40")
    assert contribution_score(demo_contributions[2], demo_project, demo_members, demo_tasks) == Decimal("0")
    assert contribution_score(demo_contributions[3], demo_project, demo_members, demo_tasks) == Decimal("8")
    assert abs(sum((s.contribution_share for s in scores.values()), Decimal("0")) - Decimal("100")) <= Decimal("0.01")
    assert demo_contributions[3].helped_member_id == "alice"
    for member, score in scores.items():
        print(member, score.total_score, score.contribution_share)
