PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS medicines (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_name        TEXT NOT NULL UNIQUE,
    generic_name      TEXT NOT NULL,
    active_ingredient TEXT NOT NULL,
    strength          TEXT,
    category          TEXT,
    uses              TEXT,
    warnings          TEXT,
    source            TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    language_pref TEXT NOT NULL DEFAULT 'English',
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cabinet (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    medicine_id      INTEGER NOT NULL REFERENCES medicines(id),
    raw_ocr_text     TEXT,
    match_confidence REAL,
    expiry_date      TEXT,
    status           TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'used_up')),
    scanned_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cabinet_user ON cabinet(user_id);
CREATE INDEX IF NOT EXISTS idx_medicines_generic ON medicines(generic_name);
