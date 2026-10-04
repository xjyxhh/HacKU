# Accounts, workspace, roles, and graph integration manual

This is the historical implementation specification based on the local workspace and more-functions branch 3e445b4. It was originally marked pending, not deployed. Recheck actual code/data before operations. The current remote implementation incorporates these capabilities; this English edition preserves requirements without claiming every acceptance item is production-verified.

Scope: registration, profile, workspace/self-created projects, four roles, existing-account invitation/role changes, fixed demo, four graph views, delivery evidence, and session-specific contract advancement. Preserve independent per-project SQLite ledgers and 12-hour sessions; do not introduce one multi-project ledger or TOKEN_ADMIN_KEY. English-only presentation supersedes the original bilingual requirement.

## 0. Product rules and completion

An account is a global immutable member_id usable across projects. Normalize/uniquely store email; verification proves ownership for email invitations. The original specification required verification before email login; current registered-email login follows the existing server behavior, so member-ID login remains the reliable fallback when SMTP is absent. Editable display name never changes member_id. Registration creates account/member only, never joins existing projects or takes another member's invitation identity.

Self-service creation atomically creates project/lifecycle/version/membership/Owner/admin compatibility records, then initializes a separate ledger. Site-admin creation remains distinct from automatically joining a project. Failed initialization retains TOKEN_SETUP_PENDING and retry without claiming usable Tokens.

Keep existing public Dashboard/review-detail/Token read routes. Personal workspace/profile/membership/todos require login and return only authorized data. Roles authorize actions, not hidden project privacy. Owner manages; Member contributes/commissions; Verifier reviews; Viewer reads. Never let role or site administration bypass self/party independence.

Owners invite registered accounts by member ID/verified email with chosen role. Existing account passwords never reset. Old accountless-member invitations remain one-use 48-hour links and cannot be stolen by new registration. Audit role actor/old/new/time and protect the last active Owner; honor exit/archive states.

Profile supports display name, HTTPS avatar, and short bio; email change activates only after verification. Wallet address has no current identity/issuance role and is not required. Demo is fixed read-only data, anonymous, separate from production, with no submit/settle controls. Preserve hashed project-ledger paths, migration, backup, unwind, reconciliation, refunds/splits, and actual contract_approvals.

Completion: a new user registers, enters empty workspace, creates an Owner project, invites another account, submits and independently reviews; a third account approves commissions. Workspace, views, and demo work; old invitations/lifecycle/settlement/independent ledger regressions pass.

## 1. Recoverable baseline

Record git status/HEAD/reference branch/uncommitted files and preserve existing work. Use verified per-file integration rather than blindly replacing local implementation with an entire branch. Run unittest/demo_workflow/seed_token_demo in new temp directories and inspect existing browser flows. Back up contribution/legacy/all-project files at one maintenance point with Backup API, check integrity, restore copies, record counts/balances, and retain old deployment package. Repeat before production.

## 2. Incremental account and role migration

Extend auth schema with normalized email/display name/bio/avatar/pending verification/profile time; store hashed short-lived one-use verification tokens and invalidate prior tokens when replacing a request. Old accounts without email still log in by ID; never require retroactive email or silently change historical name semantics. Public exports exclude private profile/email/auth data.

Register member+account in one transaction with stable opaque unique ID, no email plaintext in ID. Normalize casing/whitespace consistently; handle collision without orphan member rows or revealing unrelated accounts. Map old project administrators to Owner and active members to Member; site administrators without membership get no project role. Keep admin compatibility queries synchronized or unify authorization to avoid contradictory roles.

Preserve lifecycle/membership/version/ledger files. Add foreign keys/unique/indexes, idempotent migrations, rollback on failure. Missing avatar uses initials; archived/exited role history does not authorize writes. Acceptance compares project/member/contribution/event counts and balances, old logins, different roles across projects, and repeated startups.

## 3. Registration and profile

POST /api/auth/register accepts email/display name/password with existing valid_password/scrypt, Origin checks, trusted-source limits, and body limits. Reuse existing HttpOnly/Secure/SameSite session/CSRF and 12-hour policy, not branch seven-day sessions. Roll back failed account creation entirely.

Send a one-use verification link with only a server-side hash; clear URL token after exchange. Check expiry/replay/email consistency. Missing SMTP still permits member-ID account/project use and must be explained; unverified email cannot authorize invitations. Credentials belong in deployment environment, never repository/logs. Recovery must not reset passwords from unverified email; use administrator recovery when no trusted channel exists.

GET/PATCH /api/profile reads/writes only self. Bound/validate name/bio/HTTPS avatar and escape output. Email change follows submit → verify → activate; without sending capability, explain unavailability rather than an immediate-update fiction. Reuse change-password, invalidating old sessions. Profile/registration cannot directly join projects or modify ledgers.

Add registration/profile pages with auth.js as shared identity/CSRF helper. Link registration in login UI and route success to empty workspace. Any next target must be safe and same-origin. Test duplicate email/weak password/cross-origin/rate limit/invitation collision and no access to old projects.

## 4. Workspace and creation

GET /api/workspace reads only session-member projects, roles/status/counts/todos/available-frozen balance/ledger state. Query only joined projects and their own ledgers. Failed read is unavailable, never invented zero.

Todos identify project/object and link to existing detail/anchors. Only actionable evidence/review/commission/Owner exit/accounting work appears. Destinations validate object ownership/permissions and give return-to-workspace states on failure.

Self-service creation atomically creates membership/Owner/admin compatibility, checks unique IDs/current account/rate limits, then initializes ledger after commit. An existing project must never enroll or upgrade a would-be creator. Retry pending ledger only. Reuse project form constraints and saved selection; empty workspace offers create/wait-for-invite, not unrelated sample projects. Anonymous create guides login/register while preserving safe return context. Test both self-service and site-admin paths and setup failure.

## 5. Roles and invitation

| Action | Owner | Member | Verifier | Viewer |
|---|---|---|---|---|
| Public/project-personal reads | Yes | Yes | Yes | Yes |
| Membership/tasks/budgets/roles/invitations/settings | Yes | No | No | No |
| Own contribution/evidence | Yes | Yes | Yes | No |
| Own dispute/withdrawal | Yes | Yes | Yes | No |
| Independent contribution review/commission approval | Independent only | No | Independent only | No |
| Own commission/delivery | Yes | Yes | Party-dependent | No |
| Manual mint/cap/reconcile/accounting | Yes | No | No | No |
| Settlement/exit/withdrawal decisions | Non-party under current rules | No | Explicitly authorized reviews | No |

Site administrators retain recovery/archival authority without independent self-approval. Configure actual reviewers as Verifier/Owner during migration so old projects retain qualified reviewers. Do not weaken third-party approval for two-member projects.

Centralize authorization around session member, project, membership state, lifecycle, role, and object parties. Apply to every POST/PATCH/DELETE, scoped and legacy aliases; body member/role/project is never actor authority. Add members GET, invite-existing POST, and member-role PATCH under proper Owner checks. Existing-account lookup uses member ID or verified email, avoids unrelated profile exposure, and returns 409 if already joined. Add membership/role/audit transactionally; ledger member sync failure is retryable without undoing successful join or claiming full completion.

Keep old add-member → invitation → password path. Explain both pathways. Role changes audit and protect last active Owner; exit-pending/exited/archived roles cannot reopen writes. Refresh frontend capabilities, but reauthorize each backend request. Contract principal/contractor/approver/resolver are actual session identities. Test all roles/statuses/cross-project/impersonation/self-review/last-owner/exit-state and both invitation paths.

## 6. Delivery and independent verification

Compare CREDIT_RESERVED → DELIVERED → VERIFIED interactions against current engine/store/approvals/finality without overwriting freeze/shortfall/refund/split logic. Cards display parties/task/price/reserve/state/evidence/real approvers/next actor/blockers. Contractor supplies own evidence; independent Owner/Verifier approves; settled disputes use current finality controls.

Delivery evidence and state change share one project-ledger transaction. Require nonempty, bounded evidence/count; duplicates cannot advance twice. Settlement still verifies recorded contract_approvals. Explain evidence/third-party/budget/archive/exit/debt blockers. Workspace points to exact contract and refreshes on success. Test three-account success and rejected two-member/self/no-evidence/duplicate/illegal-dispute advancement; replay exact amounts.

## 7. Four graph views

Filter existing graph data, never rebuild the ledger or introduce unnecessary four separate APIs. Views: value (CONTRIBUTES_TO/CREATED_VALUE/MINTED); flow (MINTED/PAID/SPLIT/REFUNDED); collaboration (COMMISSIONED/EXECUTED/CONTRIBUTES_TO/PAID/SPLIT); trust (APPROVED/DISPUTED/FROZEN/RELEASED). Verify actual emitted edge kinds and classify lifecycle/recovery additions explicitly.

Use one filter for SVG/list/count; preserve every raw relationship in at least one view. Provide purpose/empty states and keyboard/focus/contrast/narrow-scroll behavior. Reset invalid cross-project focus, keep suitable view preference. Link event/contribution/contract detail; display exact refund/split amounts and do not rely on color alone.

## 8. Demo and navigation

Fixed /demo.html and GET /api/demo show submit → independent review → Token recording → commission → dispute; no production-file selector, write, or real balance claim. Offer register/Dashboard/fairness exits.

Reuse page-nav/topbar/style.css colors/layout/cards/forms/theme/focus/skip-link/status. Main entries are Dashboard/review/Token; workspace appears for signed-in users, member/role/invite/task/lifecycle controls are secondary project management, profile/security are settings, and demo remains available. Avoid replacing the existing homepage with branch landing/hacku.html. Shared identity/project/login status controls actions from capabilities, while backend validates independently.

Cross-page links carry project/object IDs; validate query context before saved project then first visible project. Clear invalid focus on switching, forbid external next redirects, and preserve reasonable refresh/back behavior. Current requested interface is English; titles/aria-labels/empty/error/help must match. Test anonymous demo → registration → empty workspace → creation → invitation → review → ledger plus desktop/mobile/keyboard/themes.

## 9. Verification and release

Add temporary-file tests for account compatibility/email normalization/uniqueness/password/rate-limit/Origin/CSRF/self-profile/workspace isolation/creation atomicity/setup failure/role migration/last Owner/invites/exit-archive-role interaction/backend role matrix/delivery/approval/graph classification/demo isolation. Retain existing lifecycle/finality/migration/backup tests.

Manually run three accounts, Viewer, cross-project Owner, forged body IDs, self-approval, missing third-party, archived writes, unavailable ledger, and anonymous demo. Check statuses/messages and project context after refresh/back/switch. Run unittest/demo_workflow/isolated seed_token_demo, update README/app guide/FAIRNESS/CHANGELOG, and record limitations.

Rehearse migrations/rollback on backups. Before production, back up all files at one time; after release validate old logins/projects first, then new registration/workspace/invitation/review, and finally per-project events/balances. Failure requires stopping writes and restoring whole database group plus package. Record versions/counts/tests/screenshots/demo URL/backup/recovery results and unresolved limits.

Sequence: baseline/migration → registration/profile → workspace/creation → roles/invitation → delivery → graph → demo/navigation → full acceptance. Open UI only after backend capabilities exist. Deliver code/additive schema/rollback guide/tests/docs/reviewable screenshots; reference branch code must be absorbed selectively.
