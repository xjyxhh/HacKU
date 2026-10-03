"""Test-only authenticated client for legacy HTTP integration tests."""
import hashlib
import json
import secrets
import sqlite3
import time

from fastapi.testclient import TestClient


class AuthenticatedClient(TestClient):
    password = "test-password-long-enough"

    def __init__(self, app, db_path=None, **kwargs):
        self.db_path = str(db_path or app.state.db_path)
        super().__init__(app, **kwargs)
        self._ensure_accounts()
        self._login("_test_admin")

    def _ensure_accounts(self):
        salt = b"test-auth-fixture"
        digest = hashlib.scrypt(self.password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR IGNORE INTO members(id,name) VALUES(?,?)", ("_test_admin", "Test admin"))
            conn.execute("INSERT OR IGNORE INTO auth_accounts(member_id,salt,password_hash,is_site_admin) VALUES(?,?,?,1)",
                         ("_test_admin", salt, digest))
            rows = conn.execute("SELECT project_id,member_id FROM project_members").fetchall()
            for project_id, member_id in rows:
                conn.execute("INSERT OR IGNORE INTO auth_accounts(member_id,salt,password_hash,is_site_admin) VALUES(?,?,?,1)",
                             (member_id, salt, digest))
                conn.execute("INSERT OR IGNORE INTO auth_project_admins(project_id,member_id) VALUES(?,?)",
                             (project_id, member_id))

    def _login(self, member_id):
        self._ensure_accounts()
        self.post("/api/auth/login", json={"member_id": member_id, "password": self.password},
                  headers={"Origin": "http://testserver"})
        csrf = self.cookies.get("hacku_csrf", "")
        self.headers.update({"Origin": "http://testserver", "X-CSRF-Token": csrf})

    def post(self, url, *args, **kwargs):
        body = kwargs.get("json")
        if isinstance(body, dict):
            actor = next((body[key] for key in ("contributor_id", "submitted_by", "reviewer_id", "resolved_by")
                          if isinstance(body.get(key), str)), None)
            if actor:
                with sqlite3.connect(self.db_path) as conn:
                    exists = conn.execute("SELECT 1 FROM auth_accounts WHERE member_id=?", (actor,)).fetchone()
                if exists:
                    self._login(actor)
        result = super().post(url, *args, **kwargs)
        if result.status_code in (200, 201) and url.startswith("/api/projects/") and url.endswith("/members"):
            project_id = url.split("/")[3]
            member_id = body.get("id") if isinstance(body, dict) else None
            if member_id:
                salt = b"test-auth-fixture"
                digest = hashlib.scrypt(self.password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("INSERT OR IGNORE INTO auth_accounts(member_id,salt,password_hash,is_site_admin) VALUES(?,?,?,1)",
                                 (member_id, salt, digest))
                    conn.execute("INSERT OR IGNORE INTO auth_project_admins(project_id,member_id) VALUES(?,?)",
                                 (project_id, member_id))
        return result
