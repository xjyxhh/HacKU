CREATE TABLE IF NOT EXISTS project_lifecycle (
    project_id TEXT PRIMARY KEY REFERENCES projects(id),
    state TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (state IN ('ACTIVE','ARCHIVED')),
    version INTEGER NOT NULL DEFAULT 1,
    token_setup_state TEXT NOT NULL DEFAULT 'TOKEN_SETUP_PENDING' CHECK (token_setup_state IN ('TOKEN_SETUP_PENDING','READY')),
    changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS project_membership_state (
    project_id TEXT NOT NULL,
    member_id TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (state IN ('ACTIVE','EXIT_REQUESTED','WITHDRAWN')),
    PRIMARY KEY(project_id,member_id),
    FOREIGN KEY(project_id,member_id) REFERENCES project_members(project_id,member_id)
);
CREATE TABLE IF NOT EXISTS contribution_unwind_requests (
    id TEXT PRIMARY KEY,
    contribution_id TEXT NOT NULL REFERENCES contributions(id),
    applicant_id TEXT NOT NULL REFERENCES members(id),
    reason TEXT NOT NULL CHECK (length(trim(reason))>0),
    state TEXT NOT NULL DEFAULT 'PENDING' CHECK (state IN ('PENDING','APPROVE','REJECT','CANCELLED')),
    reviewer_id TEXT,
    decision_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    decided_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS one_pending_unwind_per_contribution
ON contribution_unwind_requests(contribution_id) WHERE state='PENDING';
CREATE TABLE IF NOT EXISTS contribution_withdrawals (
    contribution_id TEXT PRIMARY KEY REFERENCES contributions(id),
    request_id TEXT NOT NULL UNIQUE REFERENCES contribution_unwind_requests(id),
    effective_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS membership_exit_requests (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    member_id TEXT NOT NULL REFERENCES members(id),
    reason TEXT NOT NULL,
    contribution_ids_snapshot TEXT NOT NULL DEFAULT '[]',
    state TEXT NOT NULL DEFAULT 'PENDING' CHECK (state IN ('PENDING','APPROVE','REJECT','CANCELLED')),
    reviewer_id TEXT,
    decision_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    decided_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS one_pending_exit
ON membership_exit_requests(project_id,member_id) WHERE state='PENDING';
CREATE TABLE IF NOT EXISTS project_lifecycle_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT NOT NULL,
    before_state TEXT NOT NULL,
    after_state TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS unwind_outbox (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    contribution_id TEXT,
    member_id TEXT NOT NULL,
    amount TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'PENDING' CHECK (state IN ('PENDING','DONE')),
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS token_ledger_migrations (
    project_id TEXT PRIMARY KEY REFERENCES projects(id),
    source_path TEXT NOT NULL,
    target_path TEXT NOT NULL,
    source_event_count INTEGER NOT NULL,
    last_event_id TEXT,
    migrated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS project_versions (
    project_id TEXT PRIMARY KEY REFERENCES projects(id),
    version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS project_archive_snapshots (
    project_id TEXT NOT NULL REFERENCES projects(id),
    version INTEGER NOT NULL,
    payload TEXT NOT NULL CHECK(json_valid(payload)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(project_id,version)
);
INSERT OR IGNORE INTO project_lifecycle(project_id) SELECT id FROM projects;
INSERT OR IGNORE INTO project_membership_state(project_id,member_id) SELECT project_id,member_id FROM project_members;
INSERT OR IGNORE INTO project_versions(project_id) SELECT id FROM projects;
