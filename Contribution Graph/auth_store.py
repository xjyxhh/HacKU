"""Password accounts and opaque cookie sessions stored in the contribution database."""

import hashlib
import hmac
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from uuid import uuid4


SESSION_TTL_SECONDS = 60 * 60 * 24 * 7
SCRYPT_N = 1 << 14
SCRYPT_R = 8
SCRYPT_P = 1


class AuthStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=10)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS member_auth (
                    member_id TEXT PRIMARY KEY REFERENCES members(id) ON DELETE CASCADE,
                    password_hash TEXT NOT NULL,
                    email TEXT UNIQUE,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS member_sessions (
                    token_hash TEXT PRIMARY KEY,
                    member_id TEXT NOT NULL REFERENCES member_auth(member_id) ON DELETE CASCADE,
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS member_sessions_by_expiry
                    ON member_sessions(expires_at);
                CREATE TABLE IF NOT EXISTS member_profiles (
                    member_id TEXT PRIMARY KEY REFERENCES members(id) ON DELETE CASCADE,
                    bio TEXT NOT NULL DEFAULT '',
                    avatar_url TEXT NOT NULL DEFAULT '',
                    wallet_address TEXT NOT NULL DEFAULT ''
                );
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(member_auth)")}
            if "email" not in columns:
                conn.execute("ALTER TABLE member_auth ADD COLUMN email TEXT")

    @staticmethod
    def _password_hash(password):
        if not isinstance(password, str) or not 12 <= len(password) <= 1024:
            raise ValueError("password must be between 12 and 1024 characters")
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=SCRYPT_N,
            r=SCRYPT_R, p=SCRYPT_P, dklen=32,
        )
        return "scrypt${}${}${}${}${}".format(
            SCRYPT_N, SCRYPT_R, SCRYPT_P,
            salt.hex(), digest.hex(),
        )

    @staticmethod
    def _verify_password(password, encoded):
        if not isinstance(password, str) or not 12 <= len(password) <= 1024:
            return False
        try:
            algorithm, n, r, p, salt_hex, digest_hex = encoded.split("$")
            if algorithm != "scrypt":
                return False
            digest = hashlib.scrypt(
                password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
                n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(digest_hex)),
            )
        except (AttributeError, TypeError, ValueError):
            return False
        return hmac.compare_digest(digest.hex(), digest_hex)

    @staticmethod
    def _token_hash(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def provision_account(self, member_id, password, email=None):
        if not isinstance(member_id, str) or not member_id.strip():
            raise ValueError("member id must be nonempty")
        normalized_email = self._normalize_email(email) if email else None
        password_hash = self._password_hash(password)
        now = int(time.time())
        with closing(sqlite3.connect(self.path, timeout=10)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                conn.execute("BEGIN IMMEDIATE")
                if not conn.execute(
                    "SELECT 1 FROM project_members WHERE member_id = ? LIMIT 1", (member_id,)
                ).fetchone():
                    raise ValueError(f"unknown project member {member_id}")
                if normalized_email and conn.execute(
                    "SELECT 1 FROM member_auth WHERE email = ? AND member_id != ?",
                    (normalized_email, member_id),
                ).fetchone():
                    raise ValueError("email is already in use")
                conn.execute(
                    "INSERT INTO member_auth (member_id, password_hash, email, updated_at) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(member_id) DO UPDATE SET password_hash = excluded.password_hash, "
                    "email = COALESCE(excluded.email, member_auth.email), "
                    "updated_at = excluded.updated_at",
                    (member_id, password_hash, normalized_email, now),
                )
                conn.execute("DELETE FROM member_sessions WHERE member_id = ?", (member_id,))
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    @staticmethod
    def _normalize_email(email):
        if not isinstance(email, str):
            raise ValueError("email is required")
        value = email.strip().casefold()
        if (len(value) > 320 or value.count("@") != 1
                or any(character.isspace() for character in value)
                or "." not in value.rsplit("@", 1)[1]):
            raise ValueError("a valid email address is required")
        return value

    def register(self, email, display_name, password):
        normalized_email = self._normalize_email(email)
        if not isinstance(display_name, str) or not display_name.strip() or len(display_name) > 120:
            raise ValueError("display name must be between 1 and 120 characters")
        password_hash = self._password_hash(password)
        member_id = uuid4().hex
        now = int(time.time())
        with closing(sqlite3.connect(self.path, timeout=10)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                conn.execute("BEGIN IMMEDIATE")
                if conn.execute(
                    "SELECT 1 FROM member_auth WHERE email = ?", (normalized_email,)
                ).fetchone():
                    raise ValueError("email is already registered")
                conn.execute(
                    "INSERT INTO members (id, name) VALUES (?, ?)",
                    (member_id, display_name.strip()),
                )
                conn.execute(
                    "INSERT INTO member_auth (member_id, password_hash, email, updated_at) "
                    "VALUES (?, ?, ?, ?)",
                    (member_id, password_hash, normalized_email, now),
                )
                conn.execute(
                    "INSERT INTO member_profiles (member_id) VALUES (?)", (member_id,)
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return member_id

    def create_session(self, member_id, password):
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        with closing(sqlite3.connect(self.path, timeout=10)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT member_id, password_hash FROM member_auth "
                    "WHERE member_id = ? COLLATE NOCASE OR email = ? COLLATE NOCASE "
                    "ORDER BY CASE WHEN member_id = ? THEN 0 ELSE 1 END LIMIT 1",
                    (member_id, member_id, member_id),
                ).fetchone()
                if not row or not self._verify_password(password, row[1]):
                    conn.rollback()
                    return None
                member_id = row[0]
                conn.execute("DELETE FROM member_sessions WHERE expires_at <= ?", (now,))
                conn.execute(
                    "INSERT INTO member_sessions (token_hash, member_id, expires_at, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (self._token_hash(token), member_id, now + SESSION_TTL_SECONDS, now),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return token

    def session_member(self, token):
        if not token:
            return None
        now = int(time.time())
        with closing(sqlite3.connect(self.path, timeout=10)) as conn:
            row = conn.execute(
                "SELECT s.member_id FROM member_sessions AS s "
                "JOIN members AS m ON m.id = s.member_id "
                "WHERE s.token_hash = ? AND s.expires_at > ?",
                (self._token_hash(token), now),
            ).fetchone()
        return row[0] if row else None

    def member_name(self, member_id):
        with closing(sqlite3.connect(self.path, timeout=10)) as conn:
            row = conn.execute("SELECT name FROM members WHERE id = ?", (member_id,)).fetchone()
        return row[0] if row else None

    def profile(self, member_id):
        with closing(sqlite3.connect(self.path, timeout=10)) as conn:
            row = conn.execute(
                "SELECT m.id, m.name, a.email, p.bio, p.avatar_url, p.wallet_address "
                "FROM members AS m JOIN member_auth AS a ON a.member_id = m.id "
                "LEFT JOIN member_profiles AS p ON p.member_id = m.id WHERE m.id = ?",
                (member_id,),
            ).fetchone()
        if row is None:
            raise ValueError("unknown user profile")
        return {
            "id": row[0], "displayName": row[1], "email": row[2],
            "bio": row[3] or "", "avatarUrl": row[4] or "",
            "walletAddress": row[5] or "",
        }

    def update_profile(self, member_id, display_name, email, bio="", avatar_url="", wallet_address=""):
        if not isinstance(display_name, str) or not display_name.strip() or len(display_name) > 120:
            raise ValueError("display name must be between 1 and 120 characters")
        normalized_email = self._normalize_email(email)
        values = (bio, avatar_url, wallet_address)
        limits = (2000, 2048, 256)
        if any(not isinstance(value, str) or len(value) > limit
               for value, limit in zip(values, limits)):
            raise ValueError("profile field exceeds its maximum length")
        with closing(sqlite3.connect(self.path, timeout=10)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                conn.execute("BEGIN IMMEDIATE")
                if conn.execute(
                    "SELECT 1 FROM member_auth WHERE email = ? AND member_id != ?",
                    (normalized_email, member_id),
                ).fetchone():
                    raise ValueError("email is already in use")
                conn.execute("UPDATE members SET name = ? WHERE id = ?",
                             (display_name.strip(), member_id))
                conn.execute("UPDATE member_auth SET email = ? WHERE member_id = ?",
                             (normalized_email, member_id))
                conn.execute(
                    "INSERT INTO member_profiles "
                    "(member_id, bio, avatar_url, wallet_address) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(member_id) DO UPDATE SET bio = excluded.bio, "
                    "avatar_url = excluded.avatar_url, wallet_address = excluded.wallet_address",
                    (member_id, bio.strip(), avatar_url.strip(), wallet_address.strip()),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return self.profile(member_id)

    def find_member(self, identifier):
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("member ID or email is required")
        with closing(sqlite3.connect(self.path, timeout=10)) as conn:
            row = conn.execute(
                "SELECT m.id, m.name FROM members AS m "
                "JOIN member_auth AS a ON a.member_id = m.id "
                "WHERE m.id = ? COLLATE NOCASE OR a.email = ? COLLATE NOCASE "
                "ORDER BY CASE WHEN m.id = ? THEN 0 ELSE 1 END LIMIT 1",
                (identifier.strip(), identifier.strip(), identifier.strip()),
            ).fetchone()
        return row

    def delete_session(self, token):
        if not token:
            return
        with closing(sqlite3.connect(self.path, timeout=10)) as conn:
            conn.execute(
                "DELETE FROM member_sessions WHERE token_hash = ?",
                (self._token_hash(token),),
            )
            conn.commit()
