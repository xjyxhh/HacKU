# B implementation for contribution review

This is the historical review-page implementation report. Its original 38-test/browser results describe that earlier revision, not current production verification. Later account/role manuals replace its former demonstration identity selector.

Start `dashboard_server.py` from `group contribution ledger/`; open `/review.html` and `/docs` at `http://127.0.0.1:8000`. To keep the default database unchanged, create a new file with `seed_dashboard.py output/b-demo.sqlite3` and start with `--db output/b-demo.sqlite3`. Seeding refuses overwrite.

## Data flow

```text
review.html / review.js → fetch → dashboard_server.py
→ ContributionStore (members, states, history, SQLite transactions)
→ contribution_engine.py (single scoring formula)
→ reload details and Dashboard → update review page and notify Dashboard
```

| Operation | API |
|---|---|
| Members/tasks/contributions/scores | GET `/api/projects/fintech/dashboard` |
| Detail/evidence/review/dispute history | GET `/api/contributions/{id}` |
| Evidence | POST `/api/contributions/{id}/evidence` |
| Confirm/adjust/dispute | POST `/api/contributions/{id}/reviews` |
| Resolve | POST `/api/contributions/{id}/resolve` |
| Preview | POST `/api/contributions/{id}/preview` |

The queue uses Dashboard contributions and loads detail by ID. No separate queue API is necessary.

## Preview

`preview_score()` uses `dataclasses.replace()` to create a verified copy and calls the existing contribution_score() for original and proposed parameters. It leaves stored state, fields, and file unchanged. Return currentScore (actually counted), proposedScore (existing fields after verification), updatedScore (adjusted result), and scoreChanged.

A PENDING CORE task worth 40 with completion 1 has currentScore 0 and proposedScore 40. Previewing completion 0.8 returns 32 without saving. Detail includes currentScore/proposedScore so pending zero is not mistaken for proposed value. Changing inputs, selected contribution, or actor invalidates the preview; adjustment requires a fresh score-changing preview.

## Restrictions

PENDING allows confirm/adjust/dispute; VERIFIED allows dispute; DISPUTED allows resolution; RESOLVED presents final history. Evidence references were allowed in all legacy review states. Confirm/adjust/resolve require a different member from the contributor; contributors may raise disputes. Reasons/conclusions are required for dispute/resolution. Quality is 0.9–1.1, CORE completion 0–1, and support value nonnegative.

Buttons reflect identity/state but the server independently validates every action. Lock relevant controls while waiting. Errors appear at the top; if saving succeeded but refresh failed, state that clearly and stop showing stale actionable details. Escape evidence, notes, and history; only HTTP/HTTPS references become links.

## Dashboard synchronization

Reload detail and project Dashboard after writes. A localStorage change signal triggers same-origin open Dashboards to fetch again; returning to a Dashboard also refreshes. The signal is notification, not business storage. Other browsers/devices can refresh manually.

## Historical verification

`test_review_api.py` covers CORE/non-CORE previews, unchanged file bytes, four evidence kinds, score/relationship updates, restart persistence, and rejected self-review/invalid input/state changes. At that earlier merge, 38 automated tests passed. Browser checks covered evidence, actor restrictions, required reasons/conclusions, team score 67 → 70 → 67 → 69, Dashboard updates, CORE adjustment 25 → 20, invalidated previews, empty queue, and desktop/mobile widths without horizontal overflow or reported console errors. Isolated copies left data.json unchanged.

Reproduce with c3: self-confirmation as Charlie is disabled; Alice attaches evidence and confirms (Charlie 3, team 70), disputes (team 67), then resolves at support value 2 after preview (team 69). Details retain evidence and all decisions. C and a restarted service must show the same result. A fresh PENDING record verifies that preview does not save and unchanged scores cannot be adjusted.

The original scope used a demonstration actor selector, local single-process SQLite, and text/link evidence without uploads. Current sessions/roles supersede that selector. Run `python3 -m unittest discover -s . -p 'test_*.py'` from the application directory before submitting.
