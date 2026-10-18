"""SQLite persistence: connection, schema, seeding and CRUD for users, medicines and cabinet."""
from __future__ import annotations

import csv
import hashlib
import hmac
import secrets
import sqlite3
import threading
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional, Union

import config
from src.utils.logging_setup import get_logger

log = get_logger(__name__)
_LOCK = threading.RLock()
Row = dict[str, Any]


# --------------------------------------------------------------------------
# Connection / low-level helpers
# --------------------------------------------------------------------------
def connect(db_path: Union[str, Path, None] = None) -> sqlite3.Connection:
    """Open a SQLite connection (safe to share across Streamlit threads via the module lock)."""
    path = str(db_path) if db_path is not None else str(config.DB_PATH)
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _query(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[Row]:
    with _LOCK:
        return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def _query_one(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> Optional[Row]:
    rows = _query(conn, sql, params)
    return rows[0] if rows else None


def _execute(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> int:
    """Execute a write statement, commit, and return lastrowid."""
    with _LOCK:
        cur = conn.execute(sql, tuple(params))
        conn.commit()
        return int(cur.lastrowid or 0)


# --------------------------------------------------------------------------
# Schema and seeding
# --------------------------------------------------------------------------
def create_schema(conn: sqlite3.Connection) -> None:
    """Create all tables from ``schema.sql`` if they do not exist."""
    with _LOCK:
        conn.executescript(config.SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()


def seed_medicines(conn: sqlite3.Connection, csv_path: Union[str, Path, None] = None) -> int:
    """Load the medicines CSV into the table; returns the number of rows inserted."""
    path = Path(csv_path) if csv_path else config.SEED_CSV_PATH
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    with _LOCK:
        conn.executemany(
            "INSERT OR IGNORE INTO medicines (brand_name, generic_name, active_ingredient, "
            "strength, category, uses, warnings, source) VALUES (?,?,?,?,?,?,?,?)",
            [
                (
                    r["brand_name"].strip(), r["generic_name"].strip(), r["active_ingredient"].strip(),
                    r.get("strength", ""), r.get("category", ""), r.get("uses", ""),
                    r.get("warnings", ""), r.get("source") or config.SEED_SOURCE,
                )
                for r in rows
            ],
        )
        conn.commit()
    log.info("Seeded %d medicines", len(rows))
    return len(rows)


def init_db(conn: sqlite3.Connection, seed_csv: Union[str, Path, None] = None) -> None:
    """Create the schema, seed medicines if the table is empty and ensure the demo user exists."""
    create_schema(conn)
    count = _query_one(conn, "SELECT COUNT(*) AS n FROM medicines") or {"n": 0}
    if count["n"] == 0:
        seed_medicines(conn, seed_csv)
    ensure_demo_user(conn)


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------
def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256; format ``pbkdf2_sha256$iters$salt$hash``."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, config.PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${config.PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of a password against a stored hash string."""
    try:
        scheme, iters, salt_hex, hash_hex = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------
# Users
# --------------------------------------------------------------------------
def _public_user(row: Optional[Row]) -> Optional[Row]:
    if row is None:
        return None
    return {k: v for k, v in row.items() if k != "password_hash"}


def create_user(
    conn: sqlite3.Connection, name: str, email: str, password: str,
    language_pref: str = config.DEFAULT_LANGUAGE,
) -> int:
    """Register a new user. Raises ``ValueError`` for invalid input or a duplicate email."""
    name, email = name.strip(), email.strip().lower()
    if not name:
        raise ValueError("Please enter your name.")
    if "@" not in email or "." not in email.split("@")[-1]:
        raise ValueError("Please enter a valid email address.")
    if len(password) < config.MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {config.MIN_PASSWORD_LENGTH} characters.")
    if language_pref not in config.LANGUAGES:
        language_pref = config.DEFAULT_LANGUAGE
    if _query_one(conn, "SELECT id FROM users WHERE email = ?", (email,)):
        raise ValueError("An account with this email already exists.")
    return _execute(
        conn,
        "INSERT INTO users (name, email, password_hash, language_pref) VALUES (?,?,?,?)",
        (name, email, hash_password(password), language_pref),
    )


def authenticate(conn: sqlite3.Connection, email: str, password: str) -> Optional[Row]:
    """Return the public user record if the credentials are valid, else None."""
    row = _query_one(conn, "SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
    if row and verify_password(password, row["password_hash"]):
        return _public_user(row)
    return None


def get_user(conn: sqlite3.Connection, user_id: int) -> Optional[Row]:
    """Fetch a user (without the password hash)."""
    return _public_user(_query_one(conn, "SELECT * FROM users WHERE id = ?", (user_id,)))


def get_user_by_email(conn: sqlite3.Connection, email: str) -> Optional[Row]:
    """Fetch a user by email (without the password hash)."""
    return _public_user(
        _query_one(conn, "SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
    )


def update_user_profile(conn: sqlite3.Connection, user_id: int, name: str, language_pref: str) -> None:
    """Update the display name and language preference."""
    if not name.strip():
        raise ValueError("Name cannot be empty.")
    if language_pref not in config.LANGUAGES:
        raise ValueError("Unsupported language.")
    _execute(
        conn, "UPDATE users SET name = ?, language_pref = ? WHERE id = ?",
        (name.strip(), language_pref, user_id),
    )


def ensure_demo_user(conn: sqlite3.Connection) -> Row:
    """Create the demo user (with a small sample cabinet) if it does not exist yet."""
    existing = get_user_by_email(conn, config.DEMO_EMAIL)
    if existing:
        return existing
    # Random password: the demo account is reachable only via the "Continue as Demo User" button.
    user_id = _execute(
        conn,
        "INSERT INTO users (name, email, password_hash, language_pref) VALUES (?,?,?,?)",
        (config.DEMO_NAME, config.DEMO_EMAIL, hash_password(secrets.token_hex(16)), config.DEFAULT_LANGUAGE),
    )
    today = date.today()
    samples = [  # (brand, days until expiry) - mix of ok / expiring soon / expired / duplicates
        ("Panadol", 30), ("Calpol", 400), ("Brufen", -20), ("Nurofen", 300), ("Zyrtec", 500),
    ]
    for brand, offset in samples:
        med = get_medicine_by_brand(conn, brand)
        if med:
            add_cabinet_item(
                conn, user_id, med["id"], "demo data", 100.0, (today + timedelta(days=offset)).isoformat()
            )
    return get_user(conn, user_id) or {}


# --------------------------------------------------------------------------
# Medicines
# --------------------------------------------------------------------------
def list_medicines(conn: sqlite3.Connection) -> list[Row]:
    """Return all medicines ordered by brand name."""
    return _query(conn, "SELECT * FROM medicines ORDER BY brand_name COLLATE NOCASE")


def get_medicine(conn: sqlite3.Connection, medicine_id: int) -> Optional[Row]:
    """Fetch one medicine by id."""
    return _query_one(conn, "SELECT * FROM medicines WHERE id = ?", (medicine_id,))


def get_medicine_by_brand(conn: sqlite3.Connection, brand_name: str) -> Optional[Row]:
    """Fetch one medicine by (case-insensitive) brand name."""
    return _query_one(
        conn, "SELECT * FROM medicines WHERE brand_name = ? COLLATE NOCASE", (brand_name,)
    )


def add_medicine(conn: sqlite3.Connection, **fields: Any) -> int:
    """Insert a medicine (used by tests/admin scripts)."""
    cols = ["brand_name", "generic_name", "active_ingredient", "strength", "category", "uses", "warnings", "source"]
    values = [fields.get(c, config.SEED_SOURCE if c == "source" else "") for c in cols]
    return _execute(
        conn, f"INSERT INTO medicines ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", values
    )


# --------------------------------------------------------------------------
# Cabinet
# --------------------------------------------------------------------------
_CABINET_SELECT = (
    "SELECT c.id, c.user_id, c.medicine_id, c.raw_ocr_text, c.match_confidence, c.expiry_date, "
    "c.status, c.scanned_at, m.brand_name, m.generic_name, m.active_ingredient, m.strength, "
    "m.category, m.uses, m.warnings "
    "FROM cabinet c JOIN medicines m ON m.id = c.medicine_id WHERE c.user_id = ?"
)


def add_cabinet_item(
    conn: sqlite3.Connection, user_id: int, medicine_id: int, raw_ocr_text: str,
    match_confidence: float, expiry_date: Optional[str],
) -> int:
    """Save a confirmed scan to the user's cabinet; returns the new cabinet id."""
    if get_medicine(conn, medicine_id) is None:
        raise ValueError("Unknown medicine.")
    return _execute(
        conn,
        "INSERT INTO cabinet (user_id, medicine_id, raw_ocr_text, match_confidence, expiry_date, status) "
        "VALUES (?,?,?,?,?,?)",
        (user_id, medicine_id, raw_ocr_text, float(match_confidence), expiry_date, config.STATUS_ACTIVE),
    )


def list_cabinet(conn: sqlite3.Connection, user_id: int, status: Optional[str] = None) -> list[Row]:
    """Return a user's cabinet rows joined with medicine info, newest scan first."""
    sql, params = _CABINET_SELECT, [user_id]
    if status:
        sql += " AND c.status = ?"
        params.append(status)
    return _query(conn, sql + " ORDER BY c.scanned_at DESC, c.id DESC", params)


def set_cabinet_status(conn: sqlite3.Connection, user_id: int, cabinet_id: int, status: str) -> bool:
    """Change an item's status (active / used_up). Returns True if a row was updated."""
    if status not in (config.STATUS_ACTIVE, config.STATUS_USED_UP):
        raise ValueError("Invalid status.")
    with _LOCK:
        cur = conn.execute(
            "UPDATE cabinet SET status = ? WHERE id = ? AND user_id = ?", (status, cabinet_id, user_id)
        )
        conn.commit()
        return cur.rowcount > 0


def delete_cabinet_item(conn: sqlite3.Connection, user_id: int, cabinet_id: int) -> bool:
    """Delete an item from the user's cabinet. Returns True if a row was removed."""
    with _LOCK:
        cur = conn.execute("DELETE FROM cabinet WHERE id = ? AND user_id = ?", (cabinet_id, user_id))
        conn.commit()
        return cur.rowcount > 0
