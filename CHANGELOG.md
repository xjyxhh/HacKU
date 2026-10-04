# Change log

## 2026-10-04 · Project rename and English interface

- Based on remote main 0855fbe, rename the application to group contribution ledger and update directory references and deployment packaging.
- Convert repository documents, source messages, sample data, and code/Markdown filenames to English. Replace bilingual presentation with a fixed English interface.
- Preserve remote account, workspace, role, Token, and lifecycle functionality. Local outcome/value-ledger changes remain in a separate checkpoint branch.

## 2026-10-04 · Accounts, workspace, project roles, and Token graph integration

- Add public registration, optional SMTP verification, profile/email-change verification, member-ID login, and existing 12-hour sessions.
- Add personal workspace, self-created Owner projects, existing-account invitations, role audit, and last-Owner protection; retain independent project ledgers.
- Add transactional delivery evidence, party-specific advancement, independent verification, and real approval-based settlement; retain freezes/refunds/splits.
- Add fixed read-only public demo, four graph views, and account/role/demo/ledger documentation.
- Update online entry links and PocketBay persistence guidance. SMTP needs deployment configuration; browser/responsive/keyboard/theme acceptance and production backup/recovery require later deployment checks.

## 2026-10-03 · Withdrawal and project lifecycle

- Add idempotent lifecycle, membership, withdrawal/exit request, audit, and outbox tables.
- Add withdrawal decisions, exit preview/request/decision, and archive preview/archive/restore. Archival hides projects and stops writes without deleting data.
- Show zero effective score for withdrawn records and retain history; remove fixed fintech assumptions.
- Use independent SHA-256 named project ledgers; copy the legacy ledger using SQLite Backup API and retain it.
- Recover available Tokens, record named debt, allow idempotent retry, and expose previews/pending accounting/restoration in Dashboard.

## 2026-10-03 · Usage documentation

- Expand README with positioning, Dashboard/review/Token workflows, initial startup/admin key, backups, and tests.
- Correct the former administrator-header example and document separate databases/reconciliation.

## 2026-10-03 · Adversarial fixes

- Protect Token and ledger-enabled contribution writes with the then-current administrator key; bound task/evidence input.
- Fix initialization races, read-only locking, partial settlement, SUPPORT freeze targeting/repeated freezing, and record shortfall recovery debt.
- Atomically export ledger snapshots, validate numeric/member references, fail unmappable verified migration, and check Decimal conservation.
- Add concurrency, damaged-ledger, rollback, commission-freeze, debt, and snapshot-roundtrip regressions.

## 2026-10-03 · Persistent Token workspace

- Add token.sqlite3, budgets, direct mints, transfers, commissions, freeze/release APIs, legacy migration, and review-driven synchronization.
- Add workspace balance/event/graph controls and Dashboard persistent-balance/previous-score comparison tests.

## 2026-10-03 · Phase one read-only projection

- Add token_view() producing balances/contracts/events/graph without writes/schema changes. Map direct types to mints and SUPPORT to commissions; skip unverified/unsettleable records.
- Add Dashboard balances, read-only HTTP/CLI access, comparison script, and eight projection tests. Historical full suite: 57 passing tests.
- Add integration-guide.md with mappings, pitfalls, gaps, and roadmap.

## 2026-10-03 · Dashboard entry, review, and branch merge

- Add project/member/task/contribution forms and pending zero-score records; redesign layered member → contribution → task graph with dashed helped-member edges and synchronized filters.
- Add the historical bilingual switch, persisted project/filter/focus, review/evidence/adjustment/dispute/resolution page, preview API, currentScore/proposedScore, project listing, and same-origin refresh signal.
- Merge feature/contribution-review (482dbf6), resolve conflicts, and adapt JSON examples to SQLite. Historical full suite: 38 passing tests.

## 2026-10-03 · Unified data and Dashboard

- Migrate to relational SQLite with constraints, transactions, JSON tools, and tests.
- Merge two databases while retaining six contributions/reviews/disputes; rename Alice's colliding c1 to merged-c1, refresh data.json, and remove demo.json.
- Share default database/port 8000, add API read/write, filters/sorting/detail-graph synchronization, and parallel help relationships.

## 2026-10-03 · FastAPI service (f863ff9)

- Replace the earlier web service with FastAPI contribution/evidence/review/dispute APIs; add tests and requirements while retaining static Dashboard.

## 2026-10-03 · Initial application (bf4c6f5)

- Add scoring models, local store, CLI, workflow demo, tests, Dashboard/help graph, documentation, and B/C handoff.

## 2026-10-02 · Repository initialization (237c9b1)

- Create repository and initial README.

## Previously recorded unreleased authentication and dispute work

- Add account tables, scrypt seed command, session/CSRF, one-use invitations, and project-admin appointment.
- Enable Secure cookies for PocketBay, trusted-source login/invitation rate limits, and correct /api/ handling.
- Replace browser TOKEN_ADMIN_KEY prompts with member sessions; add invitation/password/fairness pages.
- Add real contract_approvals, RESOLVED migration, contract freezes, append-only REFUND/SPLIT, and resolution records without extra minting.
- Add isolated multi-case seed data and HTTP/persistence tests; update rules/integration docs.
