# Contribution withdrawal, member exit, and project lifecycle manual

This implementation checklist was originally future work, not a claim of release. Complete authentication and settlement prerequisites first, preserve unrelated local edits, and verify actual state before deployment. Later account rules supersede the original administrator-only creation proposal.

## 0. Semantics

Contribution withdrawal retains contribution/evidence/review/dispute history. The contributor requests and another active project member approves; only approval sets effective score to zero. Rejecting changes no balance/score. Recover associated net recognized Tokens. Withdrawal is irreversible for that record; renewed work needs a new ID.

Member exit affects one project only. The member requests and another active member decides; approval covers all listed effective contributions. Historical signatures and other members' completed work remain. The exited member cannot submit/review/transfer/approve there, but retains global account and other projects.

Recover withdrawn contributions first, settle existing project debt, then sweep remaining available balance to the project treasury. Transferred-away shortfalls remain named debt. Exit can complete after debt is recorded, but the UI must show debt separately from recovered value. Never debit third parties, erase MINT history, or restore used task capacity.

Project creation initializes lifecycle/version and an independent ledger. A successful project with failed ledger initialization remains TOKEN_SETUP_PENDING with retry, not falsely READY. Current self-service/administrator creation paths are defined in the accounts manual.

Project deletion means reversible archival: no SQL deletion, ID reuse, or removal of accounts/history/ledger files. Archive hides public data and rejects writes; site administrators view and restore history. Unresolved disputes/pending withdrawals/unsettled contracts/frozen value can block exit approval. Named debt may remain on an archived project, but unfinished unwind_outbox blocks archive; include debts in previews/snapshots.

## 1. Baseline and consistent backup

Verify sessions, project permissions, real approvals, and REFUND/SPLIT. Record status/version/active IDs, ledger ownership, counts, balances, and debt. Stop writes; use SQLite Backup API for contribution/legacy/all-project files at one time. Integrity-check and actually restore copies. Run all tests/demo_workflow; demos target fresh temp directories. Backups retain identities; public JSON excludes secrets.

## 2. Independent project ledgers

Resolve only existing project IDs and use their full SHA-256 hex hash under token-ledgers/<hash>.sqlite3; never interpolate raw IDs into filesystem paths. Derive development root from the contribution database directory.

Read the legacy ledger's unique project ID, copy using SQLite Backup API, and persist original-project migration metadata. If target exists, compare project ID, event count, and last event ID; do not overwrite inconsistent data. Retain the old file for rollback; write only to new path. Startup is idempotent.

Project-scoped /api/projects/{project_id}/token/... includes reads, initialization, migration, sync, budgets, mint, transfer, commissions, freeze/release, debt, and finality. Path project selects permission/file; body IDs cannot redirect. Legacy /api/token/... remains bound to the original project, not browser selection. Dashboard recognition/review synchronization follow the contribution's project.

Snapshots add token_ledgers keyed by project; legacy token_ledger remains readable. Import refuses overwrite and excludes auth secrets. Acceptance compares old event order/balances/budgets, verifies isolated projects, management permissions, and legacy alias ownership.

## 3. Complete project creation

Create project/lifecycle/version and current-rule membership/admin/role records atomically in data.sqlite3. IDs remain globally unique, including archived project IDs and legacy task/contribution IDs. Current self-service creator joins as Owner; site administration alone does not imply membership.

Initialize an empty TokenProject after commit with <project_id>-treasury and the proper current member set. Record TOKEN_SETUP_PENDING/READY because files cannot share one transaction. Authorized idempotent retry must not duplicate project/member/mint. Select the new project and expose member/invitation/task/workspace steps. Empty pages cannot assume fintech always exists. Pending initialization must never route contribution minting to another project.

## 4. Additive lifecycle storage

Add contribution_unwind_requests, contribution_withdrawals (unique contribution), membership_exit_requests (snapshot/reason/decision), project_membership_state ACTIVE/EXIT_REQUESTED/WITHDRAWN, project_lifecycle ACTIVE/ARCHIVED, project_versions, and append-only lifecycle audit. Preserve business tables/project_members rows. Missing old state means ACTIVE; versioned migration is repeatable.

Audit actor/reason/time/request/prior/new state. At most one effective withdrawal per contribution and one pending exit per project member. Effective score becomes zero while original review status/evidence/disputes remain. Payloads expose withdrawalState and original status; retain graph history. Exclude withdrawals from projection, migration, reconcile, and pending mint checks. Export/import lifecycle and outbox; absent old snapshot tables mean active records.

## 5. Individual withdrawal

POST /api/contributions/{id}/unwind-requests requires the active contributor's nonempty reason. Already withdrawn/pending/archived conflicts return 409. A request alone does not change scores/Tokens.

POST .../unwind-requests/{request_id}/decision accepts APPROVE/REJECT and note from another active project member. Approval locks/rechecks/writes decision/withdrawal in one contribution transaction; concurrent/repeated decisions take effect once. Rejection closes only the request.

In that transaction, write unique outbox contribution:<id>:withdraw with project and current net recognition. Reconcile idempotently: handle related freeze, recover available Tokens from the actual holder to treasury, record named shortfall debt, or state no recovery for unminted records. Never delete MINT, duplicate REFUND, or debit transferred-away third-party value. Account for earlier downward-score recovery/debt to avoid double collection. Withdrawal event/debt IDs use withdraw:<contribution_id>.

Mark complete after successful recovery/debt recording; leave failure/reason for administrator retry. Display request/decision actors/reasons, original/effective score, actual recovered amount, outstanding amount, and sync state. Validate no self/cross-project approval, no request-time balance mutation, retained history, nonnegative balances, and restart/retry idempotency.

## 6. Member exit and bulk withdrawal

Provide exit-preview, POST members/me/exit-requests, and cancel for the member's pending request. EXIT_REQUESTED blocks new project contributions/reviews/approvals/commissions/transfers immediately, while other projects remain usable. Preview lists effective contributions/scores, available/frozen balance, unsettled contracts, existing debts, and estimated shortfall.

List blockers and return 409 at approval for unresolved disputes, pending withdrawals, unsettled contracts, frozen value, sole active administrator, or no independent active reviewer. Resolve contracts first. Cancellation/rejection restores ACTIVE with audit.

Another active member decides via members/{member_id}/exit-requests/{id}/decision. Approval atomically withdraws all effective contributions, writes per-record audit/outbox, sets WITHDRAWN, and revokes that project's administration, unused invitations, and approval eligibility. Retain global account/other memberships.

After contribution reconciliation, run unique member:<project_id>:<member_id>:exit-sweep: pay existing project debt from available balance and transfer the remainder to treasury. Unrecovered debt stays. Only show accounting complete after recovery/debt recording succeeds; otherwise show exited/accounting pending and retry. Retain marked member/cards/edges/approvals. Check fresh membership status on writes and /me. This version has no same-project rejoin workflow; design identity/history rules separately if needed.

## 7. Archive and restore

Site-admin archive-preview returns name, data version, member/contribution/event counts, balances/debts, pending requests, and contracts. Increment the shared project version on relevant writes; clearly state archival is reversible.

Archive requires exact project ID, preview version, and reason. Pending outbox blocks with 409; stale version requires a new preview. Transactionally compare/update/audit; repeated archive is idempotent. All legacy and scoped writes check lifecycle under the same project guard, preventing concurrent writes bypassing archive.

Active project lists hide archives; direct public access returns 410. Site administrators read /api/admin/projects?state=archived and details with full history/debt. Restore requires reason/audit and keeps original IDs, ledger files, withdrawals, and exited states. It does not revive members/contributions. Select another active project or display an empty/create guide when none remain. Keep archives in backup/export/restore. Acceptance compares event order/balances and verifies debt can be collected after restore.

## 8. UI and documentation

Dashboard exposes own withdrawal requests, independent decisions, exit preview/request/status, pending accounting/retry, archive preview/confirm/history/restore. Preserve withdrawn/exit history in details and graph. Token workspace follows selected project and distinguishes uninitialized, sync-pending, and archived states. Do not label archive as permanent deletion or debt as recovered. Current presentation is English; user data remains unchanged.

Update README/application guide/FAIRNESS/integration-guide/CHANGELOG with semantics, recovery/debt distinction, hashed paths, and alias ownership. Separate-member/site-admin browser flows must complete these operations with correct permissions.

## 9. Tests, migration, release, rollback

Tests cover request/approve/reject/self/cross-project/concurrent/repeated operations; disputed/unminted/transferred-away withdrawal; exit blockers/bulk/sweep/other projects; creator permissions/two-project isolation/legacy migration/archive/restore/aliases. Use fresh files.

Demonstrate pending withdrawal; minted/partially-transferred withdrawal with debt; and multi-contribution exit followed by archive/restore. Verify scores, available/frozen/treasury/debt values and event replay:

```text
Member balance + unresolved frozen value + recovered treasury value = cumulative mint
```

Run full unittest, demo_workflow, and token demos. Browser-test anonymous reads, separate accounts, project switches, archive links, and mobile widths. Inspect diffs for temporary databases/secrets/invitations/packages. Rehearse legacy-to-project-ledger migration, repeated startup, and rollback on copies. Production release verifies original data before enabling new operations. On failure, stop writes and restore the entire matching-time database group plus old code, never just one file.
