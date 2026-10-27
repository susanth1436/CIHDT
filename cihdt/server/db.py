"""The console's database.

SQLite, through the standard library.  That is a deliberate choice rather than
a shortcut, and the reason is the same one that shapes the rest of the project:
this console is meant to run on an edge gateway, where everything stays on the
local network.  A client/server database would add a process to install, a port
to listen on, and a network dependency to a system whose selling point is not
having one.  SQLite gives real transactions, real indexes and real constraints
in a single file, with nothing to administer.

It is still a proper database, used properly:

* the schema is versioned, and migrations run on open, so an existing
  installation is upgraded rather than overwritten;
* every statement is parameterised -- no value is ever formatted into SQL;
* foreign keys are enforced, which SQLite does not do unless asked;
* write-ahead logging is on, so a reader never blocks on a writer;
* each thread gets its own connection, because FastAPI runs blocking work in a
  thread pool and a SQLite connection is not safe to share across threads.

If this ever has to move to PostgreSQL or MySQL, the work is confined to this
module: everything above it speaks in :class:`sqlite3.Row` objects obtained
from :func:`query` and :func:`execute`, not in SQL.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..config import DATA_DIR

DB_PATH = DATA_DIR / "cihdt.sqlite3"

SCHEMA_VERSION = 2

# Migrations, applied in order for every version above the one on disk.
#
# The v1 statements are all CREATE ... IF NOT EXISTS and so are safe to re-run;
# the v2 renames are not, which is exactly why the applied version is recorded
# and only the gap is run.
_MIGRATIONS: Dict[int, List[str]] = {
    # --- v1: accounts, sessions, audit trail ----------------------------
    1: [
        """
        CREATE TABLE IF NOT EXISTS users (
            username      TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            display_name  TEXT NOT NULL DEFAULT '',
            created_at    REAL NOT NULL,
            last_login    REAL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token      TEXT PRIMARY KEY,
            username   TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
            created_at REAL NOT NULL,
            last_seen  REAL NOT NULL,
            ip         TEXT NOT NULL DEFAULT '',
            user_agent TEXT NOT NULL DEFAULT ''
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(username);",
        "CREATE INDEX IF NOT EXISTS idx_sessions_seen ON sessions(last_seen);",
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            at       REAL NOT NULL,
            username TEXT NOT NULL DEFAULT '',
            action   TEXT NOT NULL,
            detail   TEXT NOT NULL DEFAULT '',
            outcome  TEXT NOT NULL DEFAULT 'ok',
            ip       TEXT NOT NULL DEFAULT ''
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_log(at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(username);",
    ],

    # --- v2: an email address is the identity, not a username -----------
    # SQLite carries a foreign-key reference through a column rename, so the
    # sessions -> users link survives this without the table being rebuilt.
    2: [
        # Open sessions are keyed to the identity that is about to change, and
        # there is no ON UPDATE CASCADE to carry them across. Ending them is
        # the right answer anyway: the identity someone signed in with no
        # longer exists, so they should sign in again under the new one.
        "DELETE FROM sessions;",
        "ALTER TABLE users RENAME COLUMN username TO email;",
        "ALTER TABLE sessions RENAME COLUMN username TO email;",
        "ALTER TABLE audit_log RENAME COLUMN username TO actor;",
        # Anything created before this migration had a bare name. Give it a
        # shape that is at least a valid address, rather than leaving a row
        # nobody can ever sign in to.
        "UPDATE users SET email = email || '@local' WHERE email NOT LIKE '%@%';",
        """
        CREATE TABLE IF NOT EXISTS settings (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at REAL NOT NULL
        );
        """,
    ],
}


class Database:
    """A SQLite database, one connection per thread."""

    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self.migrate()

    # ------------------------------------------------------------ plumbing
    @property
    def connection(self) -> sqlite3.Connection:
        """This thread's connection, opened on first use."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=10.0,
                                   isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 10000")
            self._local.conn = conn
        return conn

    @contextmanager
    def transaction(self):
        """Run a write inside a transaction, serialised across threads."""
        with self._write_lock:
            conn = self.connection
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except Exception:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # ------------------------------------------------------------ queries
    def query(self, sql: str,
              params: Sequence[Any] = ()) -> List[sqlite3.Row]:
        return list(self.connection.execute(sql, params))

    def query_one(self, sql: str,
                  params: Sequence[Any] = ()) -> Optional[sqlite3.Row]:
        row = self.connection.execute(sql, params).fetchone()
        return row

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """One write. Returns the number of rows it touched."""
        with self.transaction() as conn:
            cur = conn.execute(sql, params)
            return cur.rowcount

    def execute_many(self, sql: str,
                     rows: Iterable[Sequence[Any]]) -> None:
        with self.transaction() as conn:
            conn.executemany(sql, rows)

    # ----------------------------------------------------------- migration
    def migrate(self) -> int:
        """Bring the schema up to date. Safe to call on every start.

        Each version is applied in its own transaction, so a failure part-way
        leaves the database at the last version that fully succeeded rather
        than somewhere in between.
        """
        conn = self.connection
        conn.execute("PRAGMA foreign_keys = ON")
        current = int(conn.execute("PRAGMA user_version").fetchone()[0])

        for version in sorted(_MIGRATIONS):
            if version <= current:
                continue
            with self._write_lock:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    for statement in _MIGRATIONS[version]:
                        conn.execute(statement)
                    conn.execute(f"PRAGMA user_version = {version}")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
                conn.execute("COMMIT")
            current = version
        return current

    # ------------------------------------------------------------ reporting
    def stats(self) -> Dict[str, Any]:
        """What the console shows about its own storage."""
        def count(table: str) -> int:
            row = self.query_one(f"SELECT COUNT(*) AS n FROM {table}")
            return int(row["n"]) if row else 0

        size = self.path.stat().st_size if self.path.exists() else 0
        return {
            "engine": "SQLite " + sqlite3.sqlite_version,
            "path": str(self.path),
            "size_kb": round(size / 1024, 1),
            "schema_version": self.connection.execute(
                "PRAGMA user_version").fetchone()[0],
            "users": count("users"),
            "sessions": count("sessions"),
            "audit_entries": count("audit_log"),
            "journal_mode": self.connection.execute(
                "PRAGMA journal_mode").fetchone()[0],
        }


# ---------------------------------------------------------------------------
# audit trail
# ---------------------------------------------------------------------------
def record(db: Database, actor: str, action: str, detail: str = "",
           outcome: str = "ok", ip: str = "") -> None:
    """Write one line to the audit trail.

    A security console that cannot say who rolled the model back is missing
    the one record an incident review would ask for first.  Auditing must
    never break the action it is recording, so a failure here is swallowed.
    """
    try:
        db.execute(
            "INSERT INTO audit_log (at, actor, action, detail, outcome, ip)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (time.time(), actor or "", action, detail[:500], outcome,
             ip[:64]))
    except sqlite3.Error:                                    # pragma: no cover
        pass


def recent(db: Database, limit: int = 100,
           actor: str = "") -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    if actor:
        rows = db.query(
            "SELECT * FROM audit_log WHERE actor = ?"
            " ORDER BY at DESC LIMIT ?", (actor, limit))
    else:
        rows = db.query("SELECT * FROM audit_log ORDER BY at DESC LIMIT ?",
                        (limit,))
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# small persisted settings
# ---------------------------------------------------------------------------
def get_setting(db: Database, key: str,
                default: Optional[str] = None) -> Optional[str]:
    row = db.query_one("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row else default


def set_setting(db: Database, key: str, value: str) -> None:
    db.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value,"
        " updated_at = excluded.updated_at",
        (key, value, time.time()))


DB = Database()
