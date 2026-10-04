# Frontend adversarial review and change requirements

Review date: 2026-10-04. Scope: Dashboard, contribution review, Token workspace, shared authentication, invitation redemption, and fairness pages in group contribution ledger/dashboard/. Related APIs/manuals were inspected only to assess UI behavior.

This historical report lists findings and acceptance requirements; it does not assert that every issue was fixed or browser/production acceptance completed. Line references identify the reviewed revision and may have shifted. The current English-only requirement supersedes its original bilingual requirement.

## 1. Basis and priorities

References: B-C-handoff.md, member-auth-and-settlement-manual.md, withdrawal-and-lifecycle-manual.md, README, FAIRNESS. Required chains: own-account contribution/evidence → independent review; project-specific mint and third-party commission settlement; frozen settled-payment RELEASE/REFUND/SPLIT; own withdrawal/exit with independent approval, zero effective score/retained history/recovery/debt/sync; administrator create/archive/view/restore; session-specific permissions across pages.

P0 blocks a complete workflow. P1 contradicts established product rules or key data semantics. P2 affects reliability, clarity, or accessibility. Findings below were confirmed from source; browser behavior requires separate acceptance.

## 2. Findings and acceptance

| ID | Priority | Finding and source evidence | Required result |
|---|---|---|---|
| F-01 | P0 | token.js:125,130,133,258–271 generates a settle-form, hides all forms, and waits for a data-settle button never rendered. | Expose settlement for VERIFIED contracts with actual independent approval; authorized administrator submits and sees mint/payment/approver/events. Three identities complete commission/delivery/approval/settlement; settled disputes reach RELEASE/REFUND/SPLIT. |
| F-02 | P0 | review.html:42 lacks withdrawal filter; review.js:31,59–62,83–100 uses original review status and claims withdrawn VERIFIED value still counts. | Show withdrawalState and original status, zero effective score, request/decision/accounting/history. Withdrawn records remain findable and are never described as counted. |
| F-03 | P1 | auth.js:49–63 only adds site administrators, while dashboard_server.py:552 and the manual require project-admin appointment/list. | Distinguish site/project administration; site admin appoints an existing accounted project member. Ordinary/cross-project users fail; independent admin can resolve a party administrator's dispute. |
| F-04 | P1 | Password-change API exists at dashboard_server.py:601 without a page entry. | Old/new/confirmation password UI; clear weak/incorrect feedback; successful change invalidates old sessions and guides login. |
| F-05 | P1 | app.js:324–331 shows invitation once with a fixed 48-hour label but omits expiresAt/copy result. | Show exact expiry, one-use meaning, copy confirmation/manual fallback; no token logging/storage/repeated disclosure. |
| F-06 | P1 | app.js:101–113,516–525 says delete member; backend:1495–1511 only removes no-history project membership. | Say remove from this project; explain retained account/history and guide contributed members to exit. |
| F-07 | P1 | review.js:164–170 throws No projects yet for an empty deployment. | Normal empty state, administrator creation guidance, Dashboard link, usable login/navigation. |
| F-08 | P1 | app.js:397–412,421–445 collapses stale-preview/accounting conflicts into generic messages. | Explain exit blockers, outbox reconciliation/retry, stale-version refresh, and exited/accounting-pending versus complete. Only pending outbox necessarily blocks archive; other preview counts are not blanket blockers. |
| F-09 | P1 | Fixed English review/token text, fixed non-English lifecycle text, and auxiliary pages cause inconsistent presentation. | Use consistent English interface, errors, states, titles, help, and empty states; preserve names/IDs/evidence/user input. The original report requested bilingual completeness; the current user request replaces it. |
| F-10 | P1 | token.js:150–154 retains focusedEventId in every event-type filter. | Deep-link initial focus/highlight must not defeat subsequent filters; selecting REFUND after a MINT link shows REFUND only, with a way to find the original event again. |
| F-11 | P2 | review.js:9–23 and token.js:12–21 mostly echo raw errors without consistent next action. | Explain 401/login, 403/permission, uninitialized ledger/retry, and insufficient balance/debt recovery while retaining specific server reason. |
| F-12 | P2 | app.js lifecycle/reconcile, auth.js:57–84, and accept-invite lack complete pending-submit locking. | Disable related controls while waiting, show progress, restore after failure, keep input, retain backend idempotency/conflicts. Slow repeated clicks must not create duplicate intent. |
| F-13 | P2 | review.html:29/review.js:41 disable actor, but review.js:127 re-enables with busy state. This was not proven impersonation because only self is listed and server checks identity. | Read-only actor text or permanently disabled control; login/switch/refresh/submit never makes it an actor selector. |

## 3. Coverage and remaining work

Project/member/task/contribution entry requires F-06/F-07 plus empty/new/cross-project browser checks. Independent review requires F-02/F-09/F-11/F-13 and coexistence of withdrawal/original review history. Authentication requires F-03–F-05/F-09/F-11/F-12. Token settlement requires F-01/F-09–F-11, especially reachable settlement and all final outcomes. Lifecycle requires F-02/F-06/F-08/F-09/F-12 with actual recovery/debt states. Fairness explanation must let reviewers identify beneficiaries, review costs, independence, and limits.

Python API tests cannot prove DOM reachability. Add browser request-layer checks for no obsolete key/header, 401/403, CSRF, read-only controls, and current identity. Use separate members plus site admin for submit/evidence/review/mint/invitation/appointment/commission/settlement/finality/withdrawal/exit/archive/restore; commissions need a third independent project identity. Cover anonymous reads, cross-project access, persisted login, mobile width, keyboard, and themes.

Use isolated scripts for pending withdrawal, partially transferred minted withdrawal/debt, and multi-contribution exit/archive/restore. Compare scores, balances, frozen/treasury/debt values and event replay. Never write demo data into production or repository snapshot. Back up contribution/legacy/all-project ledgers together, rehearse migration/restoration/rollback, then perform PocketBay test and production acceptance. This report did not perform those operations.

Two-member approval, transferred-away payment shortfall, and Token units not being wages/market prices are established boundaries requiring clear failure explanations. External email, two-person self-certification, and periodic statements were not defects within this review's original scope.

## 4. Implementation sequence

First F-01/F-02/F-03 to restore settlement, withdrawal semantics, and independent administration. Then F-04–F-08 for passwords/invitations/lifecycle/empty states. Finally F-09–F-13 for presentation/filtering/errors/repeated submits/actor reliability, with browser automation and narrow-width/keyboard checks.

Run full unittest and demo_workflow.py from the application directory; Token/lifecycle changes also require manual-script accounting and backup-copy checks. Attach screenshots for visible UI review and exclude experimental SQLite, secrets, invitations, caches, and deployment archives.

## 5. Historical validation and limits

The previous review recorded 158 passing tests using the project virtual environment. System python3 lacked fastapi/uvicorn and failed nine module imports. Passing Python assertions did not prove reachable browser workflows. The report itself changed no business data and did not operate production. The original workspace had many uncommitted changes that implementation was required to preserve; current local checkpoint handling is separate from this historical report.
