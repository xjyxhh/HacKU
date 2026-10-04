# group contribution ledger

A local web application for recording team contributions, independent peer review, and collaboration. It was developed for the HacKU 2026 prototype demonstration. The legacy workflow scores CORE, SUPPORT, REVIEW, and COORDINATION contributions. Pending and disputed records do not count toward scores. Verified value can enter an independent project Token ledger.

## Access

[Live application](https://hacku.pocketbay.app) · [Register](https://hacku.pocketbay.app/register.html) · [My workspace](https://hacku.pocketbay.app/workspace.html) · [Public demo](https://hacku.pocketbay.app/demo.html) · [Review](https://hacku.pocketbay.app/review.html) · [Token workspace](https://hacku.pocketbay.app/token.html)

These are the existing deployment URLs. Source changes pushed to GitHub do not by themselves verify that the deployment has been updated.

## Features

- Record projects, members, tasks, and four contribution types. New contributions are PENDING with score zero.
- Attach NOTE, URL, IMAGE, or GITHUB_PR evidence references; independently confirm or adjust contributions, raise disputes, and retain resolution history. Preview adjustments before saving.
- View member scores, shares, task values, contribution details, and a member → contribution → task graph. Dashed edges identify helped members. Filter and sort the list and graph together.
- Use an English interface. User-entered project names, evidence, and descriptions retain their original text.
- View persistent project Token balances alongside previous contribution scores. Reconcile reviewed records whose minting failed.
- Manage mint budgets, direct mints, transfers, commissions, freezes, releases, ledger events, and recovery debt.
- Register an account, edit a display name, HTTPS avatar URL, and introduction, and access a personal workspace. Self-service project creators become Owners. SMTP configuration is required to send verification emails.
- Assign project-scoped OWNER, MEMBER, VERIFIER, and VIEWER roles. Invite existing accounts by member ID or verified email; members without accounts can redeem a one-use 48-hour invitation.
- View a fixed public demo without accessing real project databases. Explore value creation, Token flow, collaboration, and verification/trust graph views.

Site administrator is a separate operational identity and does not automatically confer project membership. Owners manage project membership and roles; Members contribute and accept commissions; Verifiers review independently; Viewers read. See [fairness rules](FAIRNESS.md).

## Start locally

Run from the application directory with Python 3:

```sh
cd 'group contribution ledger'
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python import_json.py data.json data.sqlite3
.venv/bin/python dashboard_server.py
```

On Windows, use `.venv\Scripts\python.exe` in place of `.venv/bin/python`. Import only when the database is absent; the importer refuses to overwrite an existing database. The server and CLI share `data.sqlite3`. SQLite runtime files are ignored by Git; `data.json` is the portable snapshot.

Open [Dashboard](http://127.0.0.1:8000), [Review](http://127.0.0.1:8000/review.html), [Token workspace](http://127.0.0.1:8000/token.html), or [API documentation](http://127.0.0.1:8000/docs). The server binds to `127.0.0.1:8000` by default. Override `--port`, `--db`, or `--token-db` when needed. Browser assets have no build step.

On macOS, double-click `group contribution ledger/start-local.command` after installing dependencies. It uses isolated `.local-demo/` data and opens the browser after startup. Press Control+C in its terminal to stop.

For the initial global administrator, generate a private scrypt seed for an existing member:

```sh
python3 'group contribution ledger/manage_auth.py' bootstrap-seed --db /absolute/path/data.sqlite3 --member MEMBER_ID --out /tmp/hacku-auth-seed.json
```

Supply the seed privately during deployment; remove it afterward. Existing accounts are not overwritten. Passwords require at least eight characters, uppercase, lowercase, and a number. Sessions use HttpOnly cookies and same-origin/CSRF checks. SMTP settings are `HACKU_SMTP_HOST`, `HACKU_SMTP_FROM`, and optional `HACKU_SMTP_PORT`, `HACKU_SMTP_USER`, and `HACKU_SMTP_PASSWORD`. Existing email-login behavior follows the server; use the member ID if email verification is unavailable. Email invitations require verified ownership.

## Workflow

1. Select a project or create one, then add members and tasks with preset values.
2. Submit a contribution and evidence. Its initial score is zero.
3. Another qualified member confirms, adjusts, or disputes it. Preview score changes before saving. Resolution retains the full history.
4. Initialize the selected project's ledger by migrating verified history or creating an empty ledger. Check the project ID first. Migration skips pending/disputed records and fails if verified records cannot be mapped. SUPPORT with real independent review maps to a commission; otherwise verified legacy value is retained through direct minting without invented approval.
5. Inspect balances, budgets, events, and missing mints. Reconcile if a contribution review succeeded but the ledger write failed. After a downward adjustment, collect recorded debt when the debtor has available balance.

Withdrawal requires a contributor request and an independent active-member decision. Approval sets effective score to zero and retains the original contribution, evidence, and review history. Recovery and outstanding debt are different amounts. Exit affects only one project and retains the global account. Archival hides a project and stops writes while retaining all history and ledgers; it can be restored. See the [lifecycle manual](withdrawal-and-lifecycle-manual.md).

Commissions require actual third-party approval records. For a settled dispute, freeze the original payment before RELEASE, REFUND, or SPLIT by a qualified non-party administrator. Two-member projects cannot independently approve commissions. Debt does not authorize debiting third-party balances.

## Structure

| Path | Purpose |
|---|---|
| `group contribution ledger/contribution_engine.py` | Models, validation, legacy scoring |
| `group contribution ledger/contribution_store.py` | SQLite operations, workflows, CLI, read-only projection |
| `group contribution ledger/dashboard_server.py` | FastAPI and static assets |
| `group contribution ledger/dashboard/` | Dashboard, review, Token workspace, accounts, demo |
| `group contribution ledger/token_engine.py`, `token_store.py` | Token rules, persistence, commission settlement |
| `group contribution ledger/migrate_token_ledger.py` | Verified legacy contribution migration |
| `group contribution ledger/token_projection_demo.py` | Previous-score and projected-balance comparison |
| `group contribution ledger/schema.sql` | Relational constraints and indexes |
| `group contribution ledger/data.json` | Portable example snapshot |
| `group contribution ledger/import_json.py`, `export_json.py`, `merge_sqlite.py` | Import, export, historical database merging |
| `integration-guide.md` | Model mapping, integration pitfalls, roadmap |

The snapshot contains one project, four members, four tasks, six contributions, and review/dispute records. Runtime data may differ. Refresh `data.json` with `python3 export_json.py` only after deciding which data should be published. See the [application guide](group%20contribution%20ledger/README.md) and [review implementation](B-implementation.md).

## Ledgers, backups, and deployment

Each project's ledger uses `token-ledgers/<full SHA-256 of project ID>.sqlite3`. The legacy `token.sqlite3` remains a migration backup; `/api/token/...` aliases refer only to its original project. Review records and Token events span separate SQLite files, so reconciliation is necessary after partial failures. Exact monetary response strings use `*Exact` fields.

Stop writes and back up `data.sqlite3`, legacy `token.sqlite3`, and all project ledgers at the same maintenance point. Use `backup_restore.py` with a fresh output directory to run SQLite Backup API, integrity checks, and restoration rehearsal. Public JSON snapshots exclude authentication credentials, sessions, and invitations; they are not complete account backups. Imported ledger snapshots restore the corresponding ledger files. Protect private backups and seed files.

PocketBay currently has no managed database. Before redeployment, verify `/data` persistence and back up live files. Package source, assets, and snapshot using:

```sh
python3 scripts/package_pocketbay.py /tmp/group-contribution-ledger-pocketbay.zip
python3 scripts/package_pocketbay.py /tmp/group-contribution-ledger-pocketbay.zip --bootstrap-seed 'group contribution ledger/private/hacku-auth-seed.json'
```

The archive uses `group_contribution_ledger` to avoid deployment build paths containing spaces. Supply the ignored private recovery seed only while required for administrator recovery. Stop bundling it once durable database migration and recovery are verified. Never publish the seed.

## Verification

```sh
cd 'group contribution ledger'
.venv/bin/python -m unittest discover -s . -p 'test_*.py'
.venv/bin/python demo_workflow.py
.venv/bin/python token_projection_demo.py
.venv/bin/python contribution_store.py token-view fintech
.venv/bin/python seed_token_demo.py /tmp/group-contribution-ledger-token-demo
```

Tests cover scoring, persistence, API, authentication, Token synchronization, and lifecycle behavior. Demos use temporary or new files and refuse overwrite. Read-only projection is available at `GET /api/projects/{project_id}/token-view`; Dashboard retains legacy fields and adds `balances`. Browser acceptance and production backup/restoration require separate deployment verification. See [repository guidelines](AGENTS.md), [integration guide](integration-guide.md), and [change log](CHANGELOG.md).
