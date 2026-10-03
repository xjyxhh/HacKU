-- Token ledger persistence for the fusion stage (PR1).
-- Additive only: these tables are created next to the legacy schema.sql tables
-- in the same database file. The eight legacy tables are never altered.

CREATE TABLE IF NOT EXISTS token_projects (
    id TEXT PRIMARY KEY CHECK (length(trim(id)) > 0),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    treasury_id TEXT NOT NULL CHECK (length(trim(treasury_id)) > 0),
    member_ids TEXT NOT NULL CHECK (json_valid(member_ids) AND json_type(member_ids) = 'array')
);

CREATE TABLE IF NOT EXISTS token_tasks (
    id TEXT NOT NULL CHECK (length(trim(id)) > 0),
    project_id TEXT NOT NULL REFERENCES token_projects(id),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    value_type TEXT NOT NULL CHECK (value_type IN ('CORE', 'REVIEW', 'COORDINATION')),
    mint_cap TEXT NOT NULL CHECK (json_valid(mint_cap) AND json_type(mint_cap) IN ('integer', 'real')
                                  AND CAST(mint_cap AS REAL) BETWEEN 0 AND 1000000000000),
    acceptance_criteria TEXT NOT NULL CHECK (length(trim(acceptance_criteria)) > 0),
    PRIMARY KEY (project_id, id)
);

CREATE TABLE IF NOT EXISTS commission_contracts (
    id TEXT PRIMARY KEY CHECK (length(trim(id)) > 0),
    project_id TEXT NOT NULL REFERENCES token_projects(id),
    task_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    contractor_id TEXT NOT NULL,
    value_type TEXT NOT NULL CHECK (value_type IN ('CORE', 'REVIEW', 'COORDINATION')),
    contract_price TEXT NOT NULL CHECK (json_valid(contract_price) AND json_type(contract_price) IN ('integer', 'real')
                                        AND CAST(contract_price AS REAL) BETWEEN 0 AND 1000000000000),
    maximum_mint_value TEXT NOT NULL CHECK (json_valid(maximum_mint_value) AND json_type(maximum_mint_value) IN ('integer', 'real')
                                             AND CAST(maximum_mint_value AS REAL) > 0
                                             AND CAST(maximum_mint_value AS REAL) <= 1000000000000),
    acceptance_criteria_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('DRAFT', 'OFFERED', 'ACCEPTED', 'CREDIT_RESERVED',
                                         'DELIVERED', 'VERIFIED', 'DISPUTED', 'FROZEN', 'SETTLED')),
    evidence_hashes TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(evidence_hashes) AND json_type(evidence_hashes) = 'array'),
    approver_ids TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(approver_ids) AND json_type(approver_ids) = 'array'),
    verified_mint_value TEXT CHECK (verified_mint_value IS NULL OR
                                    (json_valid(verified_mint_value) AND json_type(verified_mint_value) IN ('integer', 'real')
                                     AND CAST(verified_mint_value AS REAL) > 0
                                     AND CAST(verified_mint_value AS REAL) <= 1000000000000)),
    row_sequence INTEGER NOT NULL,
    FOREIGN KEY (project_id, task_id) REFERENCES token_tasks(project_id, id)
);

CREATE TABLE IF NOT EXISTS ledger_events (
    sequence INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE CHECK (length(trim(id)) > 0),
    project_id TEXT NOT NULL REFERENCES token_projects(id),
    kind TEXT NOT NULL CHECK (kind IN ('MINT', 'TRANSFER', 'FREEZE', 'RELEASE', 'REFUND', 'SPLIT')),
    amount TEXT NOT NULL CHECK (json_valid(amount) AND json_type(amount) IN ('integer', 'real')
                                AND CAST(amount AS REAL) > 0 AND CAST(amount AS REAL) <= 1000000000000),
    source_id TEXT,
    destination_id TEXT,
    task_id TEXT NOT NULL,
    contract_id TEXT,
    evidence_key TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (project_id, task_id) REFERENCES token_tasks(project_id, id),
    FOREIGN KEY (contract_id) REFERENCES commission_contracts(id)
);

CREATE TABLE IF NOT EXISTS reconciliation_debts (
    id TEXT PRIMARY KEY CHECK (length(trim(id)) > 0),
    project_id TEXT NOT NULL REFERENCES token_projects(id),
    debtor_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    amount TEXT NOT NULL,
    remaining TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS token_tasks_by_project ON token_tasks(project_id);
CREATE INDEX IF NOT EXISTS commission_contracts_by_project ON commission_contracts(project_id);
CREATE INDEX IF NOT EXISTS ledger_events_by_project ON ledger_events(project_id);
CREATE INDEX IF NOT EXISTS ledger_events_by_task ON ledger_events(task_id);

CREATE TRIGGER IF NOT EXISTS token_contract_members BEFORE INSERT ON commission_contracts
WHEN NOT EXISTS (
    SELECT 1 FROM token_projects AS p, json_each(p.member_ids) AS m
    WHERE p.id = NEW.project_id AND m.value = NEW.principal_id
) OR NOT EXISTS (
    SELECT 1 FROM token_projects AS p, json_each(p.member_ids) AS m
    WHERE p.id = NEW.project_id AND m.value = NEW.contractor_id
)
BEGIN SELECT RAISE(ABORT, 'contract member is not in token project'); END;

CREATE TRIGGER IF NOT EXISTS token_event_members BEFORE INSERT ON ledger_events
WHEN (NEW.kind = 'MINT' AND (
    NEW.source_id <> (SELECT treasury_id FROM token_projects WHERE id = NEW.project_id)
    OR NOT EXISTS (SELECT 1 FROM token_projects AS p, json_each(p.member_ids) AS m
                   WHERE p.id = NEW.project_id AND m.value = NEW.destination_id)
)) OR (NEW.kind = 'TRANSFER' AND (
    NOT EXISTS (SELECT 1 FROM token_projects AS p, json_each(p.member_ids) AS m
                WHERE p.id = NEW.project_id AND m.value = NEW.source_id)
    OR (NEW.destination_id <> (SELECT treasury_id FROM token_projects WHERE id = NEW.project_id)
        AND NOT EXISTS (SELECT 1 FROM token_projects AS p, json_each(p.member_ids) AS m
                        WHERE p.id = NEW.project_id AND m.value = NEW.destination_id))
)) OR (NEW.kind IN ('FREEZE', 'RELEASE') AND NOT EXISTS (
    SELECT 1 FROM token_projects AS p, json_each(p.member_ids) AS m
    WHERE p.id = NEW.project_id AND m.value = NEW.source_id
))
BEGIN SELECT RAISE(ABORT, 'ledger event member is not in token project'); END;

CREATE TRIGGER IF NOT EXISTS token_split_refund_members BEFORE INSERT ON ledger_events
WHEN (NEW.kind = 'SPLIT' AND (
    NOT EXISTS (SELECT 1 FROM token_projects AS p, json_each(p.member_ids) AS m
                WHERE p.id = NEW.project_id AND m.value = NEW.source_id)
    OR NOT EXISTS (SELECT 1 FROM token_projects AS p, json_each(p.member_ids) AS m
                   WHERE p.id = NEW.project_id AND m.value = NEW.destination_id)
)) OR (NEW.kind = 'REFUND' AND (
    NEW.destination_id IS NOT (SELECT treasury_id FROM token_projects WHERE id = NEW.project_id)
    OR NOT EXISTS (SELECT 1 FROM token_projects AS p, json_each(p.member_ids) AS m
                   WHERE p.id = NEW.project_id AND m.value = NEW.source_id)
))
BEGIN SELECT RAISE(ABORT, 'split or refund member is not in token project'); END;
