CREATE TABLE IF NOT EXISTS auth_accounts (
  member_id TEXT PRIMARY KEY REFERENCES members(id),
  salt BLOB NOT NULL, password_hash BLOB NOT NULL,
  is_site_admin INTEGER NOT NULL DEFAULT 0 CHECK (is_site_admin IN (0,1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS auth_project_admins (
  project_id TEXT NOT NULL, member_id TEXT NOT NULL,
  PRIMARY KEY (project_id, member_id),
  FOREIGN KEY (project_id, member_id) REFERENCES project_members(project_id, member_id)
);
CREATE TABLE IF NOT EXISTS auth_sessions (
  token_hash BLOB PRIMARY KEY, member_id TEXT NOT NULL REFERENCES auth_accounts(member_id),
  csrf_hash BLOB NOT NULL, expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_invites (
  token_hash BLOB PRIMARY KEY, project_id TEXT NOT NULL, member_id TEXT NOT NULL,
  expires_at INTEGER NOT NULL, used_at INTEGER,
  FOREIGN KEY (project_id, member_id) REFERENCES project_members(project_id, member_id)
);
CREATE TABLE IF NOT EXISTS auth_login_attempts (
  attempt_key TEXT PRIMARY KEY, failures INTEGER NOT NULL, window_start INTEGER NOT NULL
);
