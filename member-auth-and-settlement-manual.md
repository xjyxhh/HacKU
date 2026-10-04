# Member login, fairness, and final dispute settlement manual

This manual records the authentication and settlement implementation/operational checklist. Local identity, real approval, final settlement, and multi-case demos were implemented; production backup, PocketBay release, and browser acceptance were not verified by the original report. Later account and lifecycle manuals supersede the earlier invitation-only registration and lifecycle exclusions.

Historical acceptance: authentication/invitations/session/permissions in auth_schema.sql, manage_auth.py, auth.js and API tests; real contract_approvals; RESOLVED migration and REFUND/SPLIT replay; FAIRNESS.md and seed_token_demo.py. The recorded revision passed 153 unittest cases and demo_workflow.py. That count is historical, not a current verification claim. Browser automation, multi-account manual operations, backups, restoration, and production deployment remained pending.

## 0. Rules and boundaries

The original account path was administrator invitation: add a member, generate a one-use link if no account exists, and let the member set a password. Reuse global accounts across projects. Later public registration is defined in accounts-workspace-integration-manual.md.

Keep public Dashboard/detail/Token GETs read-only; unauthenticated writes return 401, unauthorized authenticated writes 403. Session identity determines contributor/submitted_by/reviewer/resolved_by. Compatible actor fields must match the session or return 403. A browser selector cannot impersonate another member. Maintain independent review and non-party resolution rules.

Project administrators manage their own members/tasks/invitations/Token writes. Site administration is distinct; later rules keep it separate from automatic membership. An independent administrator can resolve when another administrator is a party. Review-triggered mint/freeze/compensation records the true actor. No administrator can verify their own contribution.

Never make the first public visitor administrator. Generate a private hash-only seed interactively for verified existing data. Import once only when accounts are empty; never overwrite /data/data.sqlite3 or existing accounts. Remove the seed from subsequent packages after durable recovery is established.

Password minimum: 8 characters with uppercase, lowercase, and number. Use per-account salt and scrypt n=2^14, r=8, p=1, dklen=32. Generate session/invitation secrets with 32-byte secure randomness and store hashes. Production cookies: Secure, HttpOnly, SameSite=Lax, Path=/; session lifetime 12 hours, revoked on logout/change-password. Cookie writes require same Origin and CSRF. Login/invitation redemption require Origin and trusted-source rate limits. Invitations expire in 48 hours and are single-use. Do not log tokens/passwords or store them in analytics/localStorage.

Mint verified value once, enforce task caps, require independent review and third-party commission approval. Explain benefits, review costs, two-member limits, inability to freeze transferred-away payments, and drifting value units.

CREDIT_RESERVED reserves issuance capacity without charging the principal. Cancelling unsettled work releases reserve and records cancellation, without monetary REFUND. True REFUND/SPLIT require a settled, successfully frozen original payment. They do not mint again or restore used task capacity. If the contractor lacks sufficient balance, return 409 with shortfall, leave ledger/contract unchanged, and show recovery is required; do not debit third parties.

Original exclusions were exit/historical unwind, two-person self-certification, external email, and periodic statements. Later manuals implement selected extensions; independent approval remains mandatory.

## 1. Baseline, backup, and recovery

Run all tests and demo_workflow.py; record git status, deployed version, failures, and the old package. Stop writes and use SQLite Backup API for contribution/legacy/all-project ledger files at one maintenance point, not raw copies of active databases. Check PRAGMA integrity_check = ok and actually restore copies to a test directory. Compare old Dashboard/review, event counts, balances, budgets, and debt. Never test against production. Acceptance requires recoverable complete backups, baseline results, and rollback package.

## 2. Identity schema and private bootstrap

Add auth_accounts, auth_project_admins, auth_sessions, auth_invites, auth_login_attempts without rewriting eight business tables. Accounts reference members.id; project administration references project_members. Incremental migration is idempotent and versioned through PRAGMA user_version.

```sh
python3 manage_auth.py bootstrap-seed --db /absolute/path/data.sqlite3 --project fintech --member alice --out /tmp/hacku-auth-seed.json
python3 scripts/package_pocketbay.py /tmp/gcl-pocketbay.zip --bootstrap-seed /tmp/hacku-auth-seed.json
```

Replace sample IDs with backup-verified production values. Hidden input supplies the password; output contains member/project, salt, hash, and scrypt parameters, with mode 0600. Explicit --bootstrap-seed packages it under non-static group_contribution_ledger/private/; default packaging excludes it. Import in one transaction only for an empty account table. Ignore private/seed/experimental files in Git. Public export excludes passwords, sessions, and invitations. Bad member/absent seed leaves writes closed; repeated startup must not alter accounts.

## 3. Session and invitation APIs

Provide login/logout/change-password/me. /me returns current member, projects/admin capabilities, and CSRF information, never password hashes or raw session secrets. Password changes revoke old sessions.

Project invitation creation is restricted to administrators and an existing project member without an account. Store hash/member/project/expiry/use time; revoke earlier unused invitations. Show the raw link once; put the token in a fragment, immediately remove it from the address bar, and send it by POST. Site administrators can appoint another already-accounted project member and inspect the administrator list.

accept-invite verifies expiry, replay, membership, and account absence, then atomically creates the account and marks used. Existing accounts cannot be reset by invitations. Use uniform login failure messages and rate-limit member/trusted-source attempts without trusting arbitrary forwarding headers. Reject expired/replayed/cross-project invitations, invalid passwords, and expired sessions; account reuse across projects must work.

## 4. Bind every write to identity

Replace TOKEN_ADMIN_KEY/X-Token-Admin-Key and the old unavailable-key response with session/route authorization, preserving body-size/numeric validation. Authorize project/member/task management and each ledger initialization/migration/budget/mint/transfer/contract/freeze/release/reconcile/debt operation against its actual project. Body project IDs cannot redirect authorization.

Force contribution/evidence/review/resolution actors to the session member; keep store-level independence/membership checks. Preview is pure computation and may remain public. Keep compatible fields without trusting them. Use 401/403/409 for authentication/permission/business conflict.

Add contract approve and append-only contract_approvals. Only a logged-in project member outside both parties approves VERIFIED work; each member approves a contract once with actual identity/time/note. Settlement reads valid recorded approvals and ignores fabricated IDs; compatible approver fields must agree with recorded facts. Cross-project and self-approval attempts fail. Review synchronization across separate databases reports reconciliation needs, never a fictitious cross-file transaction.

## 5. Browser authentication

One auth.js loads /api/auth/me, renders identity/login/logout, and supplies Cookie/CSRF headers to Dashboard, review, and Token workspace. 401 guides login; 403 explains permissions. Actors are read-only session displays. Anonymous pages remain readable; controls follow permissions and server validation remains authoritative.

Provide password change, project-admin appointment/list, and invitation link/copy/expiry UI. Remove browser tokenAdminKey and old header references. No password/token localStorage. Refresh retains sessions until expiry; logout immediately returns read-only. DOM modification cannot change submitted identity. Presentation is now English under the requested localization change.

## 6. Contract finality and migration

Add final outcome/note and RESOLVED state, plus resolution rows for contract, original/freeze event sequence, actor, result, refund/retained amounts, note, and time. Explicitly rebuild the old SQLite CHECK constraint after backup while preserving rows/order/keys/indexes/events.

```text
Unsettled: DISPUTED → FROZEN → DELIVERED (retry)
Unsettled: FROZEN → RESOLVED(CANCELLED) (release reserve only)
Settled: SETTLED → DISPUTED → FROZEN → RESOLVED(RELEASE|REFUND|SPLIT)
```

A party or project administrator disputes settled work with required reason and true identity; independent administration freezes the contract :payment transfer only. Require full available contractor balance. Failure returns 409/shortfall without mutations. Do not confuse manually frozen or legacy contribution events with contract escrow. Settled work can never mint/settle twice.

RELEASE sends all P to contractor; REFUND all P to principal; SPLIT requires Decimal refund R with 0 < R < P and contractor P-R. The exact sum is P and reason is mandatory. Replay, balances, and task budgets must match before/after migration. Cancellation creates no fictitious refund.

## 7. Append-only refunds and splits

Bind frozen payment to escrow:<contract_id>. REFUND transfers escrow to principal; SPLIT records two events in one resolution batch; RELEASE restores full contractor payment. IDs derive from contract/outcome for idempotency. Consume each freeze once. Commit events, contract state, and resolution atomically in the same project ledger transaction; roll back on any failure.

resolve accepts outcome/note and SPLIT refund_amount. Its session actor must be an authorized non-party project administrator. Preserve legacy reconcile_refund's TRANSFER/debt behavior, rather than renaming historical events. Replays/restarts reproduce balances; refunds/splits do not increase cumulative mint or restore budgets; resolved frozen amount becomes zero. Duplicate/concurrent/invalid/self-party requests cannot issue value twice.

```text
Current member balances + unresolved frozen value + recovered treasury value = cumulative mint
```

## 8. Rules and demonstrations

Expose FAIRNESS.md and visible cards explaining objects, beneficiaries, independent review, unique minting, costs, and failure boundaries. Generate a fresh isolated seed_token_demo directory with direct contribution; mint 60/pay 50/principal retains 10; full refund after dispute; and partial split. Reject overwrite and do not read/write live data. Display payments, frozen amounts, final outcomes, refunded/retained exact strings, REFUND/SPLIT events, and graph paths.

## 9. Test and release acceptance

Add focused tests for one-time bootstrap, invite expiry/replay, passwords/session invalidation, CSRF, anonymous reads, impersonation/cross-project/self-review, appointment/non-party resolution, two-member rejection, cancellation/release/refund/split/shortfall, replay/concurrency, and migration.

Run all unittest, demo_workflow.py, and seed_token_demo.py to a fresh temp directory. Browser checks cover no old key/header, 401/403/CSRF, read-only controls, identity, and separate-member submit/review. Deploy only after copy-based migration/rollback rehearsal. Validate old counts/balances first, then invitations and independent review; remove obsolete deployment TOKEN_ADMIN_KEY after session acceptance and redeploy without an unnecessary seed.

For rollback, stop writes and restore the entire matching-time database set plus old package and any old-version settings. Code-only rollback against migrated files is insufficient. Record versions/backups and update README, application guide, integration guide, FAIRNESS, and CHANGELOG. Production acceptance requires real independent submit → review → ledger plus REFUND/SPLIT, public reads, permission isolation, conservation, and durable data.
