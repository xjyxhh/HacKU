"""Tests for the data model and score engine.

Run from the repository root:
    python3 -m unittest discover -s 'Contribution Graph' -p 'test_*.py' -v
"""

import unittest
from dataclasses import replace
from decimal import Decimal

from contribution_engine import (
    Contribution,
    ContributionStatus,
    ContributionType,
    Dispute,
    Evidence,
    EvidenceType,
    Project,
    Verification,
    VerificationDecision,
    contribution_score,
    demo_data,
    score_members,
    validate_contribution,
)


class EngineTestCase(unittest.TestCase):
    def setUp(self):
        self.project, self.members, self.tasks, self.contributions = demo_data()
        self.by_id = {contribution.id: contribution for contribution in self.contributions}

    def score(self, contribution):
        return contribution_score(contribution, self.project, self.members, self.tasks)


class DataModelTests(EngineTestCase):
    def test_enums(self):
        self.assertEqual({x.value for x in ContributionType}, {"CORE", "SUPPORT", "REVIEW", "COORDINATION"})
        self.assertEqual({x.value for x in ContributionStatus}, {"PENDING", "VERIFIED", "DISPUTED", "RESOLVED"})
        self.assertEqual({x.value for x in VerificationDecision}, {"CONFIRM", "ADJUST", "DISPUTE"})
        self.assertEqual({x.value for x in EvidenceType}, {"NOTE", "URL", "IMAGE", "GITHUB_PR"})

    def test_mutable_defaults_are_independent(self):
        first, second = Project("p1", "First"), Project("p2", "Second")
        first.member_ids.append("alice")
        first.task_ids.append("task")
        self.assertEqual((second.member_ids, second.task_ids), ([], []))

        first = Contribution("c1", "p1", "alice", "task", ContributionType.CORE, "Work")
        second = Contribution("c2", "p1", "alice", "task", ContributionType.CORE, "Other work")
        first.evidence_ids.append("e1")
        self.assertEqual(second.evidence_ids, [])
        self.assertEqual(second.status, ContributionStatus.PENDING)
        self.assertEqual((second.completion, second.quality, second.support_value), (Decimal("1"), Decimal("1"), Decimal("0")))

    def test_review_models_store_their_fields(self):
        evidence = Evidence("e1", "c1", "alice", EvidenceType.GITHUB_PR, "https://example.com/pr/1")
        verification = Verification("v1", "c1", "bob", VerificationDecision.ADJUST, "Reduce value")
        dispute = Dispute("d1", "c1", "bob", "Incorrect attribution", "Split work", "charlie")
        self.assertEqual((evidence.contribution_id, evidence.kind), ("c1", EvidenceType.GITHUB_PR))
        self.assertEqual((verification.reviewer_id, verification.decision), ("bob", VerificationDecision.ADJUST))
        self.assertEqual((dispute.resolution, dispute.resolved_by), ("Split work", "charlie"))
        self.assertIsNone(Dispute("d2", "c1", "bob", "Needs review").resolution)


class ValidationTests(EngineTestCase):
    def test_demo_contributions_are_valid(self):
        for contribution in self.contributions:
            with self.subTest(contribution=contribution.id):
                self.assertIsNone(validate_contribution(contribution, self.project, self.members, self.tasks))

    def test_rejects_invalid_type_and_status(self):
        for changes, message in (
            ({"type": "CORE"}, "invalid contribution type"),
            ({"status": "VERIFIED"}, "invalid contribution status"),
        ):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, message):
                self.score(replace(self.by_id["c1"], **changes))

    def test_rejects_project_member_and_task_mismatches(self):
        core = self.by_id["c1"]
        cases = (
            (replace(core, project_id="other"), self.project, self.members, self.tasks, "another project"),
            (replace(core, contributor_id="unknown"), self.project, self.members, self.tasks, "not a project member"),
            (core, replace(self.project, member_ids=["bob"]), self.members, self.tasks, "not a project member"),
            (core, self.project, {"bob": self.members["bob"]}, self.tasks, "not a project member"),
            (replace(core, task_id="unknown"), self.project, self.members, self.tasks, "not part of the project"),
            (core, replace(self.project, task_ids=["dashboard"]), self.members, self.tasks, "not part of the project"),
            (core, self.project, self.members,
             {**self.tasks, "recommendation": replace(self.tasks["recommendation"], project_id="other")},
             "not part of the project"),
        )
        for contribution, project, members, tasks, message in cases:
            with self.subTest(message=message, contribution=contribution), self.assertRaisesRegex(ValueError, message):
                validate_contribution(contribution, project, members, tasks)

    def test_rejects_invalid_helped_member(self):
        support = self.by_id["c4"]
        for member_id in ("unknown", "david"):
            with self.subTest(member_id=member_id), self.assertRaises(ValueError):
                self.score(replace(support, helped_member_id=member_id))
        with self.assertRaisesRegex(ValueError, "helped member is not a project member"):
            validate_contribution(support, self.project, {"david": self.members["david"]}, self.tasks)

    def test_rejects_invalid_numbers_even_for_pending_work(self):
        core = replace(self.by_id["c1"], status=ContributionStatus.PENDING)
        support = self.by_id["c4"]
        cases = (
            (replace(core, completion=Decimal("-0.01")), "completion"),
            (replace(core, completion=Decimal("1.01")), "completion"),
            (replace(core, quality=Decimal("0.89")), "quality"),
            (replace(core, quality=Decimal("1.11")), "quality"),
            (replace(support, support_value=Decimal("-0.01")), "support_value"),
            (replace(core, support_value=Decimal("1")), "CORE contribution"),
        )
        for contribution, message in cases:
            with self.subTest(contribution=contribution), self.assertRaisesRegex(ValueError, message):
                self.score(contribution)
        tasks = {**self.tasks, "recommendation": replace(self.tasks["recommendation"], task_value=Decimal("-1"))}
        with self.assertRaisesRegex(ValueError, "task_value"):
            validate_contribution(core, self.project, self.members, tasks)

    def test_accepts_numeric_boundaries(self):
        core = self.by_id["c1"]
        for completion in (Decimal("0"), Decimal("1")):
            for quality in (Decimal("0.9"), Decimal("1.1")):
                with self.subTest(completion=completion, quality=quality):
                    candidate = replace(core, completion=completion, quality=quality)
                    self.assertIsNone(validate_contribution(candidate, self.project, self.members, self.tasks))

    def test_rejects_nonfinite_numbers(self):
        core = self.by_id["c1"]
        for field in ("completion", "quality", "support_value"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                validate_contribution(replace(core, **{field: Decimal("NaN")}),
                                      self.project, self.members, self.tasks)
        tasks = {**self.tasks, "recommendation": replace(self.tasks["recommendation"],
                                                           task_value=Decimal("Infinity"))}
        with self.assertRaisesRegex(ValueError, "task_value"):
            validate_contribution(core, self.project, self.members, tasks)


class ContributionScoreTests(EngineTestCase):
    def test_core_uses_task_value_completion_and_quality(self):
        core = self.by_id["c1"]
        self.assertEqual(self.score(core), Decimal("40"))
        self.assertEqual(self.score(replace(core, completion=Decimal("0.5"), quality=Decimal("0.9"))), Decimal("18"))
        self.assertEqual(self.score(replace(core, completion=Decimal("0"))), Decimal("0"))

    def test_other_types_use_support_value_and_quality_only(self):
        cases = (
            (self.by_id["c4"], Decimal("8")),
            (replace(self.by_id["c3"], status=ContributionStatus.VERIFIED), Decimal("3")),
            (replace(self.by_id["c5"], status=ContributionStatus.RESOLVED, support_value=Decimal("4")), Decimal("4")),
        )
        for contribution, expected in cases:
            with self.subTest(type=contribution.type):
                self.assertEqual(self.score(contribution), expected)
                self.assertEqual(self.score(replace(contribution, quality=Decimal("1.1"))), expected * Decimal("1.1"))
                self.assertEqual(self.score(replace(contribution, completion=Decimal("0"))), expected)

    def test_status_controls_scoring(self):
        support = self.by_id["c4"]
        for status, expected in (
            (ContributionStatus.PENDING, Decimal("0")),
            (ContributionStatus.DISPUTED, Decimal("0")),
            (ContributionStatus.VERIFIED, Decimal("8")),
            (ContributionStatus.RESOLVED, Decimal("8")),
        ):
            with self.subTest(status=status):
                self.assertEqual(self.score(replace(support, status=status)), expected)


class MemberScoreTests(EngineTestCase):
    def test_demo_totals_breakdowns_and_rounded_shares(self):
        scores = score_members(self.project, self.members, self.tasks, self.contributions)
        self.assertEqual(list(scores), self.project.member_ids)
        expected = {
            "alice": (Decimal("40"), Decimal("58.82")),
            "bob": (Decimal("20"), Decimal("29.41")),
            "charlie": (Decimal("0"), Decimal("0.00")),
            "david": (Decimal("8"), Decimal("11.76")),
        }
        for member_id, (total, share) in expected.items():
            with self.subTest(member=member_id):
                self.assertEqual(scores[member_id].member_id, member_id)
                self.assertEqual(scores[member_id].total_score, total)
                self.assertEqual(scores[member_id].contribution_share, share)
                self.assertEqual(set(scores[member_id].breakdown), set(ContributionType))
                self.assertEqual(sum(scores[member_id].breakdown.values(), Decimal("0")), total)
        self.assertEqual(scores["alice"].breakdown[ContributionType.CORE], Decimal("40"))
        self.assertEqual(scores["david"].breakdown[ContributionType.SUPPORT], Decimal("8"))
        self.assertEqual(sum((s.contribution_share for s in scores.values()), Decimal("0")), Decimal("99.99"))

    def test_empty_and_unverified_work_has_zero_shares(self):
        for contributions in ([], [replace(self.by_id["c1"], status=ContributionStatus.PENDING)]):
            with self.subTest(contributions=contributions):
                for score in score_members(self.project, self.members, self.tasks, contributions).values():
                    self.assertEqual(score.total_score, Decimal("0"))
                    self.assertEqual(score.contribution_share, Decimal("0.00"))
                    self.assertTrue(all(value == 0 for value in score.breakdown.values()))

    def test_verification_and_final_value_changes_recalculate(self):
        updated = [replace(c, status=ContributionStatus.VERIFIED, support_value=Decimal("5"))
                   if c.id == "c3" else c for c in self.contributions]
        scores = score_members(self.project, self.members, self.tasks, updated)
        self.assertEqual(scores["charlie"].total_score, Decimal("5"))
        self.assertEqual(scores["charlie"].breakdown[ContributionType.REVIEW], Decimal("5"))
        self.assertEqual(scores["charlie"].contribution_share, Decimal("6.85"))

    def test_multiple_contributions_accumulate(self):
        extra = replace(self.by_id["c4"], id="c6", support_value=Decimal("2"))
        scores = score_members(self.project, self.members, self.tasks, self.contributions + [extra])
        self.assertEqual(scores["david"].total_score, Decimal("10"))
        self.assertEqual(scores["david"].breakdown[ContributionType.SUPPORT], Decimal("10"))

    def test_rejects_unknown_project_member_and_invalid_contribution(self):
        project = replace(self.project, member_ids=self.project.member_ids + ["unknown"])
        with self.assertRaisesRegex(ValueError, "unknown member"):
            score_members(project, self.members, self.tasks, [])
        with self.assertRaisesRegex(ValueError, "not part of the project"):
            score_members(self.project, self.members, self.tasks, [replace(self.by_id["c1"], task_id="unknown")])


class DemoDataTests(EngineTestCase):
    def test_demo_references_and_workflow_coverage(self):
        self.assertEqual(self.project.id, "fintech")
        self.assertEqual(set(self.project.member_ids), set(self.members))
        self.assertEqual(set(self.project.task_ids), set(self.tasks))
        self.assertEqual({member.name for member in self.members.values()}, {"Alice", "Bob", "Charlie", "David"})
        self.assertEqual({task.name for task in self.tasks.values()},
                         {"Recommendation Engine", "Frontend Dashboard", "Deployment", "Demo Preparation"})
        self.assertEqual({c.type for c in self.contributions}, set(ContributionType))
        self.assertEqual({c.status for c in self.contributions}, set(ContributionStatus))
        self.assertEqual(self.by_id["c4"].helped_member_id, "alice")
        for task in self.tasks.values():
            self.assertEqual(task.project_id, self.project.id)
        for contribution in self.contributions:
            self.assertIsNone(validate_contribution(contribution, self.project, self.members, self.tasks))


if __name__ == "__main__":
    unittest.main()
