# B and C handoff for group contribution ledger

This historical handoff describes the legacy contribution workflow and shared SQLite data interface. Later authentication and Token manuals extend its scope. The goal is for B's verification to update real data and C's Dashboard/Graph to display that same current data.

## Shared foundation

A supplies projects, members, tasks, contributions, SQLite persistence, and CORE/SUPPORT/REVIEW/COORDINATION scoring. `submit_contribution()` creates PENDING records. PENDING and DISPUTED score zero; VERIFIED and RESOLVED use the final valuation.

`contribution_data(id)` returns a contribution with evidence, review, and dispute history. `dashboard_data(project_id)` supplies project/member/task/contribution/help relationships. FastAPI serves both B's write workflow and C's data from `data.sqlite3`; do not duplicate scoring formulas in JavaScript. The example snapshot has four members, four tasks, and six contributions; use port 8000.

## B work and acceptance

1. Show contribution queue and details: contributor, task, type, description, helped member, proposed value, status, evidence, and history. Filter the shared contribution data rather than introducing separate business state.
2. Call `add_evidence(id, submitted_by, kind, reference)` for NOTE, URL, IMAGE, and GITHUB_PR. References are text/links; file uploads would need separate storage.
3. CONFIRM or ADJUST PENDING contributions through `review_contribution()`. Reviewers must differ from contributors. Adjustment provides completion/support_value/quality and must actually change the score. Show before/after values.
4. DISPUTE requires a reason and pauses scoring. Resolve through `resolve_dispute()` with a conclusion and final parameters; the resolver cannot be the contributor. RESOLVED restores final scoring.
5. After each write, reload detail and project data. Show server validation errors and never report success for unsaved data.

Acceptance: evidence plus independent review produces VERIFIED; dispute/resolution preserves reasons/history; self-confirmation and invalid transitions/values fail without modifying data; C reads the resulting current state and score.

## C work and acceptance

1. Render project, members, tasks, preset task values, totalScore, contributionShare, and four-type breakdown directly from server data.
2. Show contributor/task/type/description/helped member/status/current score. Label PENDING/DISPUTED as not scored, rather than implying no work was submitted.
3. Render contributor → helped-member relationships with task, type, status, and score. Keep pending/disputed relationships visible with zero score. Contributions without helpedMemberId remain in details even though absent from this relationship array.
4. Refresh member totals, shares, breakdowns, statuses, and graph after B confirmation/adjustment/dispute/resolution.
5. Handle zero team score and empty records/relationships. Use server percentages and avoid calculating scores again.

Acceptance: all four members/tasks/types appear; David's help for Alice on Deployment is understandable; B writes produce consistent details and graph; empty and unscored states have clear labels and valid percentages.

## Integration sequence

1. Share `data.sqlite3`, project `fintech`, and port 8000.
2. B connects details → evidence → confirm/adjust → dispute → resolve.
3. C connects `dashboard_data("fintech")` to overview/details/help graph.
4. Compare `demo_workflow.py`: all PENDING = 0; after review Alice/Bob/Charlie/David = 40/20/3/12; disputing David's SUPPORT leaves him at 4; resolving SUPPORT at 7 leaves him at 11.
5. Run the full unittest suite and a real browser demonstration.

References: `contribution_engine.py` for rules, `contribution_store.py` for writes/reads, `demo_workflow.py` for expected values, and [application documentation](group%20contribution%20ledger/README.md).
