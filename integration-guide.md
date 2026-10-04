# Integration guide for legacy scoring and Token ledgers

Read this guide, [A model](A-responsibilities.md), then the [application guide](group%20contribution%20ledger/README.md). The Token engine is the rules core; SQLite, FastAPI, and existing pages provide the application shell. This document preserves historical integration decisions; current account/lifecycle manuals supersede older scope statements. The interface is now English only.

## 1. Integration constraints

Preserve legacy scoring unless explicitly authorized to change it. Keep the legacy contribution schema compatible; add Token/authentication/approval/resolution tables and explicit contract constraint migrations. Mint each value once. Calculate with Decimal internally and serialize only at boundaries. Scoring/state/persistence changes require all tests plus demo_workflow.py.

| Aspect | Legacy | Token |
|---|---|---|
| Code | contribution_engine.py, contribution_store.py | token_engine.py, token_store.py |
| Calculation | CORE = taskValue × completion × quality; others = supportValue × quality | balance = minted + received - paid |
| Categories | CORE/SUPPORT/REVIEW/COORDINATION | valueType CORE/REVIEW/COORDINATION × DIRECT/COMMISSIONED |
| State | PENDING/VERIFIED/DISPUTED/RESOLVED | Contract state machine and append-only events |
| Storage | SQLite business tables/transactions | Independent project SQLite ledgers and replay |
| UI | Dashboard/review/FastAPI | Token workspace, contract/identity APIs |

Both are in use. Reviews synchronize verified value into persistent ledgers. Commission approval and dispute freezing/resolution use Token APIs; read-only projection remains a comparison tool.

## 2. Phase one read-only projection

Phase one compares legacy scores and projected balances on existing data without writing tables/files. Additions were TOKEN_PROJECTION_ASSUMPTIONS, token_view(project_id), helper mapping methods, additive dashboard balances, read-only `/api/projects/{project_id}/token-view`, CLI token-view, comparison script, and eight focused tests.

Mapping contract:

1. Project VERIFIED/RESOLVED contributions; other statuses and withdrawals are skipped.
2. CORE/REVIEW/COORDINATION legacy score becomes a direct mint to the contributor.
3. SUPPORT maps principal = helped_member_id, contractor = contributor_id, contractPrice = legacy score when real independent review is available. Otherwise retain verified value by direct minting; do not fabricate approval.
4. verifiedMintValue = contractPrice is an explicit legacy assumption.
5. mintCap = max(task_value, projected mint total for the task).
6. Synthesize treasuryId = `<project_id>-treasury`.
7. Evidence idempotency key = legacy:<contribution_id>; phase one has no reference-level deduplication.
8. Individual failures produce skipped.reason, not an entire endpoint failure.

When all counted records project successfully, sum(balances) == totalSupply == oldTeamTotal. If exceptional records are skipped, supply can be lower. The earlier two-member scenario originally exposed missing independent approval; current fallback behavior is defined by the implementation/tests.

Persistent totalSupply is current member circulation: MINT + RELEASE - FREEZE - treasury-return TRANSFER. Task minted capacity remains cumulative and never resets on freeze/recovery. Compare historical mint, current circulation, and legacy scores only under the relevant conditions.

```sh
cd 'group contribution ledger'
.venv/bin/python token_projection_demo.py
.venv/bin/python token_projection_demo.py --db data.sqlite3
.venv/bin/python contribution_store.py token-view fintech
curl http://127.0.0.1:8000/api/projects/fintech/token-view
```

Historical sample: Alice previous score/balance 40, gross mint 47, paid 7; David receives 7; oldTeamTotal = totalSupply = 67.

## 3. Stable contracts and mappings

Preserve eight legacy schema tables/keys/indexes, _write transaction decorator, _load ordering, existing HTTP paths/fields, and established interactions unless migration is expressly requested. Add methods/fields/routes/tables rather than breaking clients. English-only presentation is an explicitly requested change.

| Legacy concept | Token concept | Caveat |
|---|---|---|
| task_value | mint_cap | Per-item baseline differs from cumulative task issuance capacity |
| CORE/REVIEW/COORDINATION valuation | mint_direct | Keep the formula as valuation |
| SUPPORT/helped_member/support_value | create_commission/settle_commission | Helped member is principal; contributor is contractor |
| Independent legacy reviewer | Independent contract approver | Neither principal nor contractor may approve |
| Evidence table | Sorted-hash evidence key | Legacy references have no unique constraint |
| Member total_score | ledger.balance | Different display/accounting semantics |
| Help relationships | Typed graph edges | Add value-flow explanations |
| Contribution share | Proposed replacement by balances | Product decision, not silent removal |

## 4. Current boundaries

Exit writes bulk withdrawal audit/outbox and named shortfall debt. ProductionMode remains a defined but otherwise unused enum; the invoked method implicitly selects mode. Two-person commissions require a third independent member. If payment has been transferred away, freezing may return 409/shortfall without debiting others. Token units depend on team practice, never inherently wages or market value.

Genuine REFUND/SPLIT append events consume frozen contract payment. Legacy downward-score recovery uses TRANSFER plus debt; do not conflate them.

## 5. Integration pitfalls

1. Do not mint CORE and SUPPORT independently for the same result. SUPPORT payment is allocation of one mint.
2. task_value is not a cumulative cap. A task worth 40 can already contain Alice's CORE 40 and Charlie's REVIEW; choose explicit cap semantics rather than rejecting existing history.
3. Legacy V = P is an assumption. Replacing V with task_value creates unsupported value; require a product decision and updated conservation tests.
4. David helping Alice means Alice commissions David, never the reverse.
5. Settlement trusts real account-produced contract_approvals, never client approver IDs; two-party self-approval is invalid.
6. Settled disputes follow SETTLED → DISPUTED → FROZEN → RESOLVED. Unsettled cancellation releases reserve without inventing refund.
7. token_view must remain read-only; the file-byte assertion protects this.
8. Use Decimal throughout migration/engine; do not feed serialized floats back.
9. Preserve rowid/_load ordering because event sequence depends on it.
10. Dashboard currently performs projection; optimize by sharing a result, not copying rules.
11. Preserve old fields/routes; compatible actor fields never override session identity.
12. Transform snake_case engine fields into camelCase at the boundary.
13. .box-agent/ is tool output, not project source. Review git status and avoid committing registry/cache/experimental files.

## 6. Decisions, roadmap, and verification

The [settlement manual](member-auth-and-settlement-manual.md) governs RELEASE/REFUND/SPLIT and insufficient freezes. The [lifecycle manual](withdrawal-and-lifecycle-manual.md) governs project-specific exit, retained history, and named debt. The [accounts manual](accounts-workspace-integration-manual.md) defines later roles/profile/workspace extensions.

Historical phase one delivered projection/comparison/tests without schema changes. Later work added sessions, permissions, approvals, persistent ledgers, dispute finality, isolated seed_token_demo data, withdrawals/exits/archival, and optional SMTP. Periodic statements remain outside the documented implementation scope. Earlier roadmap entries listing already implemented lifecycle features as future work are historical.

```sh
cd 'group contribution ledger'
.venv/bin/python -m unittest discover -s . -p 'test_*.py'
.venv/bin/python demo_workflow.py
.venv/bin/python token_projection_demo.py
```

Check sum(balances) == totalSupply; successful legacy projection equals oldTeamTotal; projection leaves database bytes unchanged; Dashboard retains every old field. Read TokenLedger public methods and token_view before edits. Rules belong in token_engine.py, mapping/persistence in stores, HTTP in dashboard_server.py, rendering in dashboard/. Add focused temporary-file tests for changed behavior. Do not alter V/cap semantics, old schema/routes, or approval independence without authorization; ask when a material product decision cannot be verified.
