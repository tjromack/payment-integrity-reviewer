"""SQLite schema + connection helpers.

Three tables mirror the workflow: `claim` (one row per claim line, carrying the
authored ground-truth label), `flag` (what the rules engine produces — rule id,
exact triggering fields, rule-derived confidence, and later the LLM explanation),
and `decision` (the human's approve/dismiss/escalate, stored as a label).

Detection and the explanation are kept strictly separate columns on `flag`: the
detection columns are populated by the deterministic engine; the explanation
columns are filled later by the LLM and never feed back into detection.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "claims.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS claim (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id                 TEXT NOT NULL,           -- groups lines of one submission
    line_id                  TEXT NOT NULL UNIQUE,    -- natural key for a claim line
    member_id                TEXT NOT NULL,
    provider_id              TEXT NOT NULL,
    provider_npi             TEXT NOT NULL,
    provider_network_status  TEXT NOT NULL,           -- 'in' | 'out' (provider's contract)
    paid_as_network          TEXT NOT NULL,           -- 'in' | 'out' (how it adjudicated)
    auth_or_emergency        INTEGER NOT NULL,        -- 0/1: authorized referral or emergency
    date_of_service          TEXT NOT NULL,           -- ISO date
    submitted_date           TEXT NOT NULL,           -- ISO date
    place_of_service         TEXT NOT NULL,
    cpt_code                 TEXT NOT NULL,
    modifiers                TEXT NOT NULL,            -- JSON array, e.g. ["59"]
    units                    INTEGER NOT NULL,
    billed_amount            REAL NOT NULL,
    allowed_amount           REAL NOT NULL,
    diagnosis_codes          TEXT NOT NULL,            -- JSON array
    -- ground truth (used only by the eval; never read by detection) -----------
    label                    TEXT NOT NULL,           -- clean|duplicate|unbundling|oon_mismatch
    is_near_miss             INTEGER NOT NULL DEFAULT 0,
    created_at               TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS flag (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_line_id            TEXT NOT NULL,           -- FK -> claim.line_id (subject line)
    rule_id                  TEXT NOT NULL,
    triggering_fields        TEXT NOT NULL,           -- JSON: exact fields/values that fired
    confidence               REAL NOT NULL,           -- rule-derived, NOT from the LLM
    -- explanation columns (Phase 3 — filled by the LLM, never feed detection) --
    explanation              TEXT,
    explanation_model        TEXT,
    explanation_prompt_version TEXT,
    created_at               TEXT NOT NULL,
    FOREIGN KEY (claim_line_id) REFERENCES claim (line_id)
);

CREATE TABLE IF NOT EXISTS decision (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    flag_id                  INTEGER NOT NULL,
    action                   TEXT NOT NULL,           -- approve | dismiss | escalate
    reviewer                 TEXT NOT NULL,
    note                     TEXT,
    created_at               TEXT NOT NULL,
    FOREIGN KEY (flag_id) REFERENCES flag (id)
);
"""


def connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    """Open a connection with row access by column name and FKs enforced."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist."""
    conn.executescript(SCHEMA)
    conn.commit()
