"""Who is allowed to operate the console.

The console drives a security pipeline: it trains models, accepts training
contributions and can roll a deployed model back.  Anyone who can reach it can
do all of that, so it is gated.

Three decisions worth stating, because each one is a place this is commonly got
wrong.

**Passwords are never stored.**  Only a PBKDF2-HMAC-SHA256 derivation of them,
with a per-user random salt and a work factor high enough to make a stolen file
expensive to attack.  Verification is a constant-time comparison, so the
response time does not leak how much of a hash matched.

**There is no default password in this source tree.**  A shipped credential is
a credential in every deployment that ever forgets to change it.  The first
account is created on first run with a password generated from
:mod:`secrets` and printed once to the terminal that started the server.

**The gate covers the API, not only the pages.**  A login screen in front of
the HTML while ``/api/...`` stays open protects nothing: every operator action
has a JSON endpoint behind it.  Both are behind the same session.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import DATA_DIR
from . import db

USERS_PATH = DATA_DIR / "users.json"

COOKIE_NAME = "cihdt_session"
SESSION_IDLE_SECONDS = 8 * 60 * 60        # signed out after 8 hours idle

# PBKDF2 work factor.  High enough to be costly to attack offline, low enough
# that a sign-in on a laptop-class machine stays well under a tenth of a second.
_ITERATIONS = 240_000
_ALGO = "pbkdf2_sha256"

# A handful of wrong guesses in a row stops being a typo and starts being a
# guessing attempt, so the account pauses briefly rather than answering faster.
_MAX_FAILURES = 5
_LOCKOUT_SECONDS = 60


# A pragmatic address check, not RFC 5322.  The goal is to reject what is
# obviously not an address and normalise what is, not to litigate the grammar
# of comments inside quoted local parts.
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[A-Za-z]{2,24}$")

MIN_PASSWORD = 8
REGISTRATION_CODE_KEY = "registration_code"


def normalise_email(value: str) -> str:
    return (value or "").strip().lower()


def valid_email(value: str) -> bool:
    return bool(_EMAIL.match(normalise_email(value)))


def open_registration() -> bool:
    """Whether anyone may create an account with just an email and password.

    Open by default: this console is run locally by a small team, and making
    them pass a code around to enrol is friction that buys nothing on a
    machine only they can reach.

    It is worth knowing what the default gives up, though, because it is not
    nothing.  The console trains models, accepts training contributions and can
    roll a deployed model back, so wherever it is reachable by people who
    should not operate it, open enrolment means the sign-in page is a
    formality.  ``CIHDT_REQUIRE_REGISTRATION_CODE=1`` puts the code back, and
    the sign-up page then asks for it.
    """
    return os.environ.get(
        "CIHDT_REQUIRE_REGISTRATION_CODE", "").strip().lower() not in (
            "1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# password hashing
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """Derive a storable representation of a password."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                                 _ITERATIONS)
    return f"{_ALGO}${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Check a password against its stored derivation, in constant time."""
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != _ALGO:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                     bytes.fromhex(salt_hex), int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def generate_password(words: int = 4) -> str:
    """A readable password for the first account."""
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return "-".join("".join(secrets.choice(alphabet) for _ in range(4))
                    for _ in range(words))


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------
@dataclass
class User:
    email: str
    password_hash: str
    display_name: str = ""
    created_at: float = field(default_factory=time.time)
    last_login: Optional[float] = None

    def public(self) -> Dict[str, Any]:
        """Everything about this user that is safe to render."""
        return {"email": self.email,
                "display_name": self.display_name or self.email,
                "created_at": self.created_at,
                "last_login": self.last_login}


class UserStore:
    """The account list, held in the ``users`` table.

    An existing ``data/users.json`` from before the database is imported once
    on first open, so upgrading does not lose anybody's account.
    """

    def __init__(self, database: Optional[Any] = None,
                 legacy_path: Path = USERS_PATH) -> None:
        self.db = database if database is not None else db.DB
        self.legacy_path = Path(legacy_path)
        self._failures: Dict[str, Tuple[int, float]] = {}
        self.initial_password: Optional[str] = None
        self.initial_email: Optional[str] = None
        self._import_legacy()
        if self.count == 0:
            self._bootstrap()

    # ------------------------------------------------------------- storage
    @staticmethod
    def _row_to_user(row: Any) -> User:
        return User(email=row["email"],
                    password_hash=row["password_hash"],
                    display_name=row["display_name"] or "",
                    created_at=row["created_at"],
                    last_login=row["last_login"])

    def _import_legacy(self) -> None:
        """Carry a pre-database users.json into the table, once."""
        if not self.legacy_path.exists() or self.count:
            return
        try:
            blob = json.loads(self.legacy_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):               # pragma: no cover
            return
        rows = []
        for u in blob.get("users", []):
            name = u.get("username") or u.get("email")
            if not name:
                continue
            # A pre-email account had a bare name; give it an address so it
            # can still be signed in to.
            email = name if "@" in name else f"{name}@local"
            rows.append((email, u["password_hash"], u.get("display_name", ""),
                         u.get("created_at", time.time()), u.get("last_login")))
        if not rows:
            return
        self.db.execute_many(
            "INSERT OR IGNORE INTO users"
            " (email, password_hash, display_name, created_at, last_login)"
            " VALUES (?, ?, ?, ?, ?)", rows)
        # Keep the old file as a backup rather than deleting someone's data.
        try:
            self.legacy_path.replace(
                self.legacy_path.with_suffix(".json.imported"))
        except OSError:                                        # pragma: no cover
            pass

    def _bootstrap(self) -> None:
        """Create the first account with a generated password.

        The password is held in memory only long enough for the caller to print
        it, and never written anywhere but the operator's terminal.
        """
        password = os.environ.get("CIHDT_ADMIN_PASSWORD") or generate_password()
        email = normalise_email(
            os.environ.get("CIHDT_ADMIN_EMAIL") or "operator@cihdt.local")
        self.db.execute(
            "INSERT INTO users"
            " (email, password_hash, display_name, created_at)"
            " VALUES (?, ?, ?, ?)",
            (email, hash_password(password), "Operator", time.time()))
        self.initial_email = email
        self.initial_password = password

    # -------------------------------------------------------------- queries
    def get(self, email: str) -> Optional[User]:
        row = self.db.query_one("SELECT * FROM users WHERE email = ?",
                                (normalise_email(email),))
        return self._row_to_user(row) if row else None

    def list_users(self) -> List[Dict[str, Any]]:
        rows = self.db.query("SELECT * FROM users ORDER BY email")
        return [self._row_to_user(r).public() for r in rows]

    @property
    def count(self) -> int:
        row = self.db.query_one("SELECT COUNT(*) AS n FROM users")
        return int(row["n"]) if row else 0

    # ---------------------------------------------------------- credentials
    def locked_for(self, email: str) -> float:
        """Seconds remaining before this account will answer again."""
        failures, last = self._failures.get(normalise_email(email), (0, 0.0))
        if failures < _MAX_FAILURES:
            return 0.0
        return max(0.0, _LOCKOUT_SECONDS - (time.time() - last))

    def authenticate(self, email: str, password: str) -> Optional[User]:
        """Return the user when the credentials are right, else ``None``."""
        key = normalise_email(email)
        if self.locked_for(key) > 0:
            return None

        user = self.get(key)
        # Derive even when the user does not exist, so a missing account and a
        # wrong password take the same time and cannot be told apart.
        reference = user.password_hash if user else hash_password("x")
        ok = verify_password(password or "", reference)

        if not (user and ok):
            failures, _ = self._failures.get(key, (0, 0.0))
            self._failures[key] = (failures + 1, time.time())
            return None

        self._failures.pop(key, None)
        user.last_login = time.time()
        self.db.execute("UPDATE users SET last_login = ? WHERE email = ?",
                        (user.last_login, key))
        return user

    def add_user(self, email: str, password: str,
                 display_name: str = "") -> User:
        key = normalise_email(email)
        if not valid_email(key):
            raise ValueError("That does not look like an email address.")
        if self.get(key) is not None:
            raise ValueError("An account already exists for that address.")
        if len(password or "") < MIN_PASSWORD:
            raise ValueError(
                f"A password must be at least {MIN_PASSWORD} characters.")

        user = User(email=key, password_hash=hash_password(password),
                    display_name=(display_name or "").strip()[:48])
        self.db.execute(
            "INSERT INTO users"
            " (email, password_hash, display_name, created_at)"
            " VALUES (?, ?, ?, ?)",
            (user.email, user.password_hash, user.display_name,
             user.created_at))
        return user

    def set_password(self, email: str, password: str) -> None:
        key = normalise_email(email)
        if self.get(key) is None:
            raise ValueError("No such account.")
        if len(password or "") < MIN_PASSWORD:
            raise ValueError(
                f"A password must be at least {MIN_PASSWORD} characters.")
        self.db.execute("UPDATE users SET password_hash = ? WHERE email = ?",
                        (hash_password(password), key))

    def remove_user(self, email: str) -> None:
        key = normalise_email(email)
        if self.get(key) is None:
            raise ValueError("No such account.")
        if self.count == 1:
            raise ValueError("This is the only account; the console would "
                             "become unreachable.")
        # ON DELETE CASCADE takes this account's sessions with it, so removing
        # someone genuinely locks them out rather than leaving a live cookie.
        self.db.execute("DELETE FROM users WHERE email = ?", (key,))
        self._failures.pop(key, None)


    # --------------------------------------------------------- registration
    def registration_code(self) -> str:
        """The shared code that lets someone enrol themselves.

        Persisted, so restarting the server does not invalidate a code already
        handed to a colleague.
        """
        code = db.get_setting(self.db, REGISTRATION_CODE_KEY)
        if not code:
            code = os.environ.get("CIHDT_REGISTRATION_CODE") or generate_password(2)
            db.set_setting(self.db, REGISTRATION_CODE_KEY, code)
        return code

    def registration_code_ok(self, supplied: str) -> bool:
        """Constant-time check of a supplied registration code."""
        if open_registration():
            return True
        return hmac.compare_digest((supplied or "").strip(),
                                   self.registration_code())

    def register(self, email: str, password: str, confirm: str,
                 display_name: str, code: str) -> User:
        """Self-service enrolment, from the sign-up page."""
        if not self.registration_code_ok(code):
            raise ValueError("That registration code is not correct. Ask an "
                             "operator for the current one.")
        if (password or "") != (confirm or ""):
            raise ValueError("The two passwords do not match.")
        return self.add_user(email, password, display_name)


# ---------------------------------------------------------------------------
# sessions
# ---------------------------------------------------------------------------
class SessionStore:
    """Sessions, in the ``sessions`` table.

    Held server side on purpose: nothing about the session travels in the
    cookie except an opaque token, so there is no signed payload to forge and
    signing out genuinely ends the session rather than asking the browser to
    forget it.  Keeping them in the database rather than a dict means a server
    restart does not sign everybody out mid-run -- which on this console could
    mean losing a twelve-step walkthrough.
    """

    def __init__(self, database: Optional[Any] = None) -> None:
        self.db = database if database is not None else db.DB

    def create(self, email: str, ip: str = "", user_agent: str = "") -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        self.db.execute(
            "INSERT INTO sessions"
            " (token, email, created_at, last_seen, ip, user_agent)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (token, normalise_email(email), now, now, ip[:64],
             (user_agent or "")[:200]))
        return token

    def resolve(self, token: Optional[str]) -> Optional[str]:
        """The email for a live session, refreshing its idle clock."""
        if not token:
            return None
        row = self.db.query_one(
            "SELECT email, last_seen FROM sessions WHERE token = ?",
            (token,))
        if row is None:
            return None
        now = time.time()
        if now - row["last_seen"] > SESSION_IDLE_SECONDS:
            self.destroy(token)
            return None
        # Only touch the row when the clock has moved enough to matter; a write
        # on every request would serialise the whole console behind one lock.
        if now - row["last_seen"] > 30:
            self.db.execute(
                "UPDATE sessions SET last_seen = ? WHERE token = ?",
                (now, token))
        return row["email"]

    def destroy(self, token: Optional[str]) -> None:
        if token:
            self.db.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def destroy_for_user(self, email: str) -> int:
        """End every session for an account."""
        return self.db.execute("DELETE FROM sessions WHERE email = ?",
                               (normalise_email(email),))

    def purge_expired(self) -> int:
        cutoff = time.time() - SESSION_IDLE_SECONDS
        return self.db.execute("DELETE FROM sessions WHERE last_seen < ?",
                               (cutoff,))

    def list_sessions(self) -> List[Dict[str, Any]]:
        rows = self.db.query(
            "SELECT token, email, created_at, last_seen, ip, user_agent"
            " FROM sessions ORDER BY last_seen DESC")
        out = []
        for r in rows:
            entry = dict(r)
            # Never render a live token; a shoulder-surfed screen would hand
            # someone an active session.
            entry["token"] = entry["token"][:6] + "…"
            out.append(entry)
        return out

    @property
    def active(self) -> int:
        row = self.db.query_one("SELECT COUNT(*) AS n FROM sessions")
        return int(row["n"]) if row else 0


USERS = UserStore()
SESSIONS = SessionStore()


def announce_initial_password() -> None:
    """Print the generated first password, once, to the starting terminal."""
    if not USERS.initial_password:
        return
    line = "=" * 66
    print(line)
    print("  A console account has been created, because none existed.")
    print()
    print(f"     email      {USERS.initial_email}")
    print(f"     password   {USERS.initial_password}")
    print()
    print("  This is shown once. Only a salted PBKDF2 hash of it is stored,")
    print(f"  in {db.DB.path}.")
    print("  Sign in and change it, or add your own accounts.")
    print()
    if open_registration():
        print("  Anyone can create their own account at /register with an")
        print("  email and a password. Set CIHDT_REQUIRE_REGISTRATION_CODE=1")
        print("  to require a shared code instead.")
    else:
        print("  To let someone enrol themselves, give them this code:")
        print()
        print(f"     registration code   {USERS.registration_code()}")
    print(line)
    USERS.initial_password = None
