CREATE TABLE IF NOT EXISTS auth_accounts (
  member_id TEXT PRIMARY KEY REFERENCES members(id),
  salt BLOB NOT NULL, password_hash BLOB NOT NULL,
  email TEXT,
  email_verified INTEGER NOT NULL DEFAULT 0 CHECK (email_verified IN (0,1)),
  display_name TEXT,
  bio TEXT NOT NULL DEFAULT '',
  avatar_url TEXT NOT NULL DEFAULT '',
  profile_updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  is_site_admin INTEGER NOT NULL DEFAULT 0 CHECK (is_site_admin IN (0,1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS auth_email_tokens (
  token_hash BLOB PRIMARY KEY,
  member_id TEXT NOT NULL REFERENCES auth_accounts(member_id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  used_at INTEGER
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
CREATE TABLE IF NOT EXISTS project_member_roles (
  project_id TEXT NOT NULL, member_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('OWNER','MEMBER','VERIFIER','VIEWER')),
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(project_id,member_id),
  FOREIGN KEY(project_id,member_id) REFERENCES project_members(project_id,member_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS project_member_roles_by_role ON project_member_roles(project_id,role);
CREATE TABLE IF NOT EXISTS project_role_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL, member_id TEXT NOT NULL, actor_id TEXT NOT NULL,
  old_role TEXT, new_role TEXT NOT NULL,
  changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
