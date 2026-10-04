# group contribution ledger application guide

Run commands in this directory. FastAPI serves the dashboard and CLI data from `data.sqlite3` at `http://127.0.0.1:8000`; `/docs` lists complete request schemas and enums. SQLite runtime files are ignored, while `data.json` is the portable snapshot. No browser build is required.

## Start and isolated demos

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python import_json.py data.json data.sqlite3
.venv/bin/python dashboard_server.py
```

Use import only if data.sqlite3 is absent; it refuses overwrite. On Windows use `.venv\Scripts\python.exe`, although the current server's Unix locking dependency requires a Unix environment such as WSL. The default server does not silently initialize an empty contribution database. On macOS, `start-local.command` starts isolated `.local-demo/` data after dependency installation; stop with Control+C.

```sh
python3 demo_workflow.py
python3 demo_workflow.py --db workflow.sqlite3
python3 contribution_store.py --db workflow.sqlite3 dashboard fintech
python3 contribution_store.py --db workflow.sqlite3 record c4
python3 seed_dashboard.py output/b-demo.sqlite3
python3 dashboard_server.py --db output/b-demo.sqlite3
```

The workflow uses temporary data unless given a new filename. Seed commands reject existing files. Both review and dashboard must share the same service/database.

| Workflow stage | Alice | Bob | Charlie | David |
|---|---:|---:|---:|---:|
| All PENDING | 0 | 0 | 0 | 0 |
| Confirmed and adjusted | 40 | 20 | 3 | 12 |
| David's SUPPORT disputed | 40 | 20 | 3 | 4 |
| SUPPORT resolved at 7 | 40 | 20 | 3 | 11 |

## Accounts, roles, and workspace

Register at `/register.html`. Registration creates a global member/account without joining existing projects. Member-ID login remains supported. Email verification and invitations require SMTP; email ownership is not established by merely entering an address. The current implementation also supports its existing registered-email login path. Configure HACKU_SMTP_HOST, HACKU_SMTP_FROM and optional PORT/USER/PASSWORD settings in the environment. `/profile.html` edits display name, HTTPS avatar link, and introduction; changing email requires verification.

`/workspace.html` lists your projects, roles, member/task counts, available/frozen Tokens, ledger setup status, and actionable review/commission/exit tasks. A failed ledger read is unavailable, not a zero balance. A self-service creator becomes Owner in the contribution database transaction, then initializes the independent ledger. If that step fails, keep the project as TOKEN_SETUP_PENDING and retry in the Token workspace. Site administrator is a separate operational identity and does not automatically join projects.

| Role | Main capabilities |
|---|---|
| OWNER | Membership, roles, project configuration, ledger administration, lifecycle handling |
| MEMBER | Own contributions, commissions, own Token transfers |
| VERIFIER | Independent review and approval according to object/party restrictions |
| VIEWER | Public project content and authorized personal workspace data |

Owners invite registered accounts by member ID or verified email and choose a role. Members without accounts retain the one-use 48-hour password invitation. Invitations to existing accounts never reset passwords. Role changes audit actor, old/new role, and time; the last active Owner cannot be downgraded. Existing public read routes remain public.

Use `manage_auth.py bootstrap-seed --db data.sqlite3 --member MEMBER_ID --out private/hacku-auth-seed.json` to initialize an administrator privately. The command reads a hidden password and writes only scrypt parameters/salt/hash. Existing accounts are not overwritten. Password requirements, 12-hour sessions, same-origin checks, and CSRF remain in force. TOKEN_ADMIN_KEY and X-Token-Admin-Key are obsolete authentication mechanisms.

## Dashboard and review

The dashboard selects or creates projects, adds members/tasks, and submits CORE/SUPPORT/REVIEW/COORDINATION contributions. Project, task, and contribution IDs are globally unique. One global member ID may join multiple projects with a consistent name. The English interface preserves user-entered text.

The graph displays member → contribution → task, with dashed helped-member edges. Click a contribution for evidence and scoring inputs. Filters and selected contributions persist across refreshes. The merged snapshot has six contributions; Alice's colliding c1 was renamed merged-c1, retaining both original records.

For the historical sample, `python3 contribution_store.py review c3 alice CONFIRM` verifies Charlie's review contribution: his score becomes 3 and team score moves from 67 to 70. Current HTTP actors always come from the session.

Review at `/review.html`: PENDING allows independent confirm/adjust or dispute; VERIFIED allows dispute; DISPUTED needs an authorized non-contributor's conclusion and final preview; RESOLVED displays final history. Evidence kinds NOTE/URL/IMAGE/GITHUB_PR are stored as text/link references, with no upload facility. Preview accepts completion/support_value/quality, computes without saving, and must change the score for ADJUST. The server returns currentScore and proposedScore separately.

After writes, reload details and Dashboard. A same-origin localStorage signal prompts open dashboard tabs to refresh; manual refresh remains available. See [B implementation](../B-implementation.md).

## API overview

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/projects` | Active project list |
| GET | `/api/dashboard` | Default active Dashboard |
| GET | `/api/projects/{project_id}/dashboard` | Selected project data |
| GET | `/api/projects/{project_id}/token-view` | Read-only legacy Token projection |
| GET | `/api/contributions/{id}` | Contribution/evidence/history |
| POST | `/api/projects` | Create project under current account rules |
| POST | `/api/projects/{id}/members`, `/tasks`, `/contributions` | Add records |
| POST | `/api/contributions/{id}/evidence`, `/reviews`, `/resolve`, `/preview` | Review workflow |

POST bodies use JSON; engine fields use snake_case, rendered payloads generally use camelCase. Consult `/docs` for complete definitions. Writes require the current member session, Origin and CSRF; project/Token administration checks the selected project's permissions.

## Token workspace

Open `/token.html`. Select a project, migrate verified legacy contributions or initialize an empty ledger, and inspect the migration preview. Pending/disputed/withdrawn records are excluded. SUPPORT with a real independent reviewer maps to a commission; without one, retain verified legacy value by direct minting without invented approval. Other unmappable verified records fail migration, avoiding a partial ledger. Existing target files are not overwritten.

Each project uses `token-ledgers/<full SHA-256 of project ID>.sqlite3`. The old token.sqlite3 remains a migration backup; old `/api/token/...` aliases stay bound to its original project. New pages and automatic review synchronization choose the contribution/project's own ledger.

Manage members/tasks, task minted/reserved/available capacity, cap adjustments, direct minting, transfers, commissions, delivery evidence, verification, real independent approvals, and settlement. Disputed unsettled work may freeze and return to delivery/verification. Settled disputes freeze the original payment and resolve through RELEASE, REFUND, or SPLIT by an authorized non-party. Two-member projects cannot independently approve commissions.

`freeze`/`release` accept sequences arrays, reason/note, and optional tag. Reviewed legacy contributions usually mint automatically. If a ledger write fails after review, tokenRecognition.pendingContributions reports it and reconcile retries. Manual minting with contribution_id requires matching project/task, reviewed status, recipient, exact amount, and evidence; no ID means independent Token work. Response *Exact strings are for precise accounting.

Downward dispute adjustment recovers available balance and records a shortfall in `/token/debts`. Collect through `/token/debts/{contribution_id}/collect` when balance returns. Until recovery, circulating Tokens may exceed resolved legacy scores. Legacy reconcile_refund produces TRANSFER/debt records; genuine contract REFUND/SPLIT consume frozen payment without new mint or restored capacity.

The four graph views filter current-project relationships: value creation, Token flow, collaboration, verification/trust. Graph, text list, and counts share the filter. `/demo.html` and `/api/demo` use fixed read-only data without opening production databases; the sample is not a real balance statement.

## Withdrawal, exit, and archival

A contributor requests withdrawal and another active member decides. Approval makes effective score zero without deleting original review status/history. Ledger reconciliation recovers available Tokens and records `withdraw:<contribution_id>` debt for shortfalls. Exit withdraws the member's remaining effective contributions, collects existing debt, and sweeps remaining available balance to that project's treasury. Global account and other projects remain intact.

Archival is recoverable and retains data/ledgers. Pending outbox accounting blocks archival; previews and archive records retain balances and debt. Restore does not revive withdrawn members or contributions. The dashboard lifecycle panel provides previews, pending accounting/retry, archived history, and restore. See [lifecycle manual](../withdrawal-and-lifecycle-manual.md).

## Snapshot and backup

`import_json.py` refuses overwrite. `export_json.py` reads runtime data and includes all project ledgers; legacy token_ledger snapshots remain readable. Specify `--token-db PATH` for a custom legacy ledger. Public snapshots exclude authentication secrets; SQLite Backup API is the complete account-preserving backup method.

Stop writes and run `backup_restore.py data.sqlite3 /tmp/gcl-backup-YYYYMMDD` with a fresh destination. It backs up contribution, legacy, and project ledger files, checks integrity, and rehearses restoration on independent copies. Review manifest.json and compare projects/events/balances/debts. Historical pre-merge databases, if present, are ignored files named data.before-merge-* and demo.before-merge-*.

## Manual legacy CLI walkthrough

```sh
python3 contribution_store.py --db walkthrough.sqlite3 create-project fintech 'FinTech group contribution ledger'
python3 contribution_store.py --db walkthrough.sqlite3 add-member fintech alice Alice
python3 contribution_store.py --db walkthrough.sqlite3 add-member fintech bob Bob
python3 contribution_store.py --db walkthrough.sqlite3 add-member fintech david David
python3 contribution_store.py --db walkthrough.sqlite3 add-task fintech recommendation 'Recommendation Engine' 40
python3 contribution_store.py --db walkthrough.sqlite3 add-task fintech deployment Deployment 20
python3 contribution_store.py --db walkthrough.sqlite3 submit fintech c1 alice recommendation CORE 'Implemented recommendation logic'
python3 contribution_store.py --db walkthrough.sqlite3 submit fintech c2 david deployment SUPPORT 'Helped Alice debug deployment' --support-value 8 --helped-member alice
python3 contribution_store.py --db walkthrough.sqlite3 add-evidence c1 alice NOTE 'Implementation record'
python3 contribution_store.py --db walkthrough.sqlite3 add-evidence c2 david NOTE 'Joint deployment debugging record'
python3 contribution_store.py --db walkthrough.sqlite3 review c1 bob ADJUST --completion 0.8 --note 'Confirmed 80 percent completion'
python3 contribution_store.py --db walkthrough.sqlite3 review c2 alice CONFIRM
python3 contribution_store.py --db walkthrough.sqlite3 review c2 alice DISPUTE --note 'Recheck support value'
python3 contribution_store.py --db walkthrough.sqlite3 resolve c2 alice 'Agreed final value of 7' --support-value 7
python3 contribution_store.py --db walkthrough.sqlite3 record c2
python3 contribution_store.py --db walkthrough.sqlite3 scores fintech
python3 contribution_store.py --db walkthrough.sqlite3 dashboard fintech
python3 contribution_store.py --db walkthrough.sqlite3 token-view fintech
python3 token_projection_demo.py --db walkthrough.sqlite3
```

Use a new database if IDs already exist. CORE supports completion; non-CORE types use support_value. Quality remains available. CONFIRM/ADJUST require independent actors, ADJUST must change the score, DISPUTE requires note, and resolve retains final parameters/conclusion. Reads recompute according to status.

Dashboard JSON contains project, members, tasks, contributions, relationships, and additive balances. Members include totalScore, contributionShare, and breakdown; help relationships include current score and status. `ContributionStore(...).dashboard_data(...)` returns the same structure. Projection returns balances/contracts/events/graph/skipped/assumptions without writes; see [integration guide](../integration-guide.md).

## PostgreSQL migration considerations

Retain relational projects/members/project-members/tasks/contributions/evidence/reviews/disputes, constraints, and application validation. SQLite decimal TEXT must migrate through exact Decimal validation into NUMERIC, never float. Replace connections/placeholders/transactions in the store while preserving engine/API contracts. Copy in dependency order, compare counts/states/scores, and keep status/history changes transactional. Preserve historical rowid order using explicit PostgreSQL ordering columns.

## Development checks

```sh
python3 -m unittest discover -s . -p 'test_*.py'
python3 demo_workflow.py
python3 token_projection_demo.py
python3 seed_token_demo.py /tmp/gcl-token-demo
```

Keep scoring in contribution_engine.py, persistence/state changes in stores, HTTP in dashboard_server.py, and rendering in dashboard/. New database-write tests use temporary files. Preserve compatible legacy fields, actual approval records, deterministic ledger replay, and same-project permission checks. Production migration/backup/browser acceptance must be rehearsed separately.
