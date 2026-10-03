PRAGMA foreign_keys = ON;
BEGIN;

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0)
);

CREATE TABLE IF NOT EXISTS members (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0)
);

CREATE TABLE IF NOT EXISTS project_members (
    project_id TEXT NOT NULL REFERENCES projects(id),
    member_id TEXT NOT NULL REFERENCES members(id),
    PRIMARY KEY (project_id, member_id)
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    task_value TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    UNIQUE (project_id, id)
);

CREATE TABLE IF NOT EXISTS contributions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    contributor_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('CORE', 'SUPPORT', 'REVIEW', 'COORDINATION')),
    description TEXT NOT NULL CHECK (length(trim(description)) > 0),
    completion TEXT NOT NULL,
    quality TEXT NOT NULL,
    support_value TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'VERIFIED', 'DISPUTED', 'RESOLVED')),
    helped_member_id TEXT,
    resolution_note TEXT,
    FOREIGN KEY (project_id, contributor_id) REFERENCES project_members(project_id, member_id),
    FOREIGN KEY (project_id, helped_member_id) REFERENCES project_members(project_id, member_id),
    FOREIGN KEY (project_id, task_id) REFERENCES tasks(project_id, id),
    CHECK (helped_member_id IS NULL OR helped_member_id <> contributor_id)
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    contribution_id TEXT NOT NULL REFERENCES contributions(id),
    submitted_by TEXT NOT NULL REFERENCES members(id),
    kind TEXT NOT NULL CHECK (kind IN ('NOTE', 'URL', 'IMAGE', 'GITHUB_PR')),
    reference TEXT NOT NULL CHECK (length(trim(reference)) > 0)
);

CREATE TABLE IF NOT EXISTS verifications (
    id TEXT PRIMARY KEY,
    contribution_id TEXT NOT NULL REFERENCES contributions(id),
    reviewer_id TEXT NOT NULL REFERENCES members(id),
    decision TEXT NOT NULL CHECK (decision IN ('CONFIRM', 'ADJUST', 'DISPUTE')),
    note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS disputes (
    id TEXT PRIMARY KEY,
    contribution_id TEXT NOT NULL REFERENCES contributions(id),
    raised_by TEXT NOT NULL REFERENCES members(id),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    resolution TEXT,
    resolved_by TEXT REFERENCES members(id)
);

CREATE INDEX IF NOT EXISTS contributions_by_project ON contributions(project_id);
CREATE INDEX IF NOT EXISTS evidence_by_contribution ON evidence(contribution_id);
CREATE INDEX IF NOT EXISTS verifications_by_contribution ON verifications(contribution_id);
CREATE INDEX IF NOT EXISTS disputes_by_contribution ON disputes(contribution_id);
COMMIT;
