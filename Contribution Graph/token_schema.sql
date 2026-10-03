-- Token ledger persistence for the fusion stage (PR1).
-- Additive only: these tables are created next to the legacy schema.sql tables
-- in the same database file. The eight legacy tables are never altered.

CREATE TABLE IF NOT EXISTS token_projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    treasury_id TEXT NOT NULL CHECK (length(trim(treasury_id)) > 0),
    member_ids TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS token_tasks (
    id TEXT NOT NULL,
    project_id TEXT NOT NULL REFERENCES token_projects(id),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    value_type TEXT NOT NULL CHECK (value_type IN ('CORE', 'REVIEW', 'COORDINATION')),
    mint_cap TEXT NOT NULL,
    acceptance_criteria TEXT NOT NULL CHECK (length(trim(acceptance_criteria)) > 0),
    PRIMARY KEY (project_id, id)
);

CREATE TABLE IF NOT EXISTS commission_contracts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES token_projects(id),
    task_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    contractor_id TEXT NOT NULL,
    value_type TEXT NOT NULL CHECK (value_type IN ('CORE', 'REVIEW', 'COORDINATION')),
    contract_price TEXT NOT NULL,
    maximum_mint_value TEXT NOT NULL,
    acceptance_criteria_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('DRAFT', 'OFFERED', 'ACCEPTED', 'CREDIT_RESERVED',
                                         'DELIVERED', 'VERIFIED', 'DISPUTED', 'FROZEN', 'SETTLED')),
    evidence_hashes TEXT NOT NULL DEFAULT '[]',
    approver_ids TEXT NOT NULL DEFAULT '[]',
    verified_mint_value TEXT,
    row_sequence INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ledger_events (
    sequence INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    project_id TEXT NOT NULL REFERENCES token_projects(id),
    kind TEXT NOT NULL CHECK (kind IN ('MINT', 'TRANSFER', 'FREEZE', 'RELEASE', 'REFUND', 'SPLIT')),
    amount TEXT NOT NULL,
    source_id TEXT,
    destination_id TEXT,
    task_id TEXT NOT NULL,
    contract_id TEXT,
    evidence_key TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS token_tasks_by_project ON token_tasks(project_id);
CREATE INDEX IF NOT EXISTS commission_contracts_by_project ON commission_contracts(project_id);
CREATE INDEX IF NOT EXISTS ledger_events_by_project ON ledger_events(project_id);
CREATE INDEX IF NOT EXISTS ledger_events_by_task ON ledger_events(task_id);
