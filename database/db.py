"""
db.py — Database connection helper and generic query utilities.
Golf Match Captain | Phase 1A
"""

from __future__ import annotations

import sqlite3
import os
from pathlib import Path

# Resolve the database path relative to this file's location
_BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = _BASE_DIR / "data" / "golf_captain.db"
SCHEMA_PATH = _BASE_DIR / "database" / "schema.sql"


def get_connection() -> sqlite3.Connection:
    """
    Open and return a SQLite connection with:
    - Row factory set to sqlite3.Row (enables dict-style access)
    - Foreign key enforcement enabled
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialise_database() -> None:
    """
    Create all tables from schema.sql if they do not already exist.
    Also runs any incremental migrations for existing databases.
    Safe to call on every app startup.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SCHEMA_PATH, "r") as f:
        schema = f.read()
    with get_connection() as conn:
        conn.executescript(schema)
    _run_migrations()


# ---------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------

def fetchall(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    """Execute a SELECT and return all rows."""
    with get_connection() as conn:
        cursor = conn.execute(sql, params)
        return cursor.fetchall()


def fetchone(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    """Execute a SELECT and return the first row, or None."""
    with get_connection() as conn:
        cursor = conn.execute(sql, params)
        return cursor.fetchone()


def execute(sql: str, params: tuple = ()) -> int:
    """
    Execute an INSERT / UPDATE / DELETE.
    Returns the lastrowid for INSERTs, or rowcount for others.
    """
    with get_connection() as conn:
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.lastrowid if cursor.lastrowid else cursor.rowcount


def executemany(sql: str, param_list: list[tuple]) -> None:
    """Execute an INSERT / UPDATE for a list of parameter tuples."""
    with get_connection() as conn:
        conn.executemany(sql, param_list)
        conn.commit()


def _run_migrations() -> None:
    """
    Incremental migrations for existing databases.
    Each migration is idempotent — safe to run repeatedly.
    """
    with get_connection() as conn:
        # Migration 001 — add hole_scores column to match table
        existing = [r[1] for r in conn.execute("PRAGMA table_info(match)").fetchall()]
        if "hole_scores" not in existing:
            conn.execute("ALTER TABLE match ADD COLUMN hole_scores TEXT")
            conn.commit()

        # Migration 002 — add role column to event_player table
        existing_ep = [r[1] for r in conn.execute("PRAGMA table_info(event_player)").fetchall()]
        if "role" not in existing_ep:
            conn.execute("ALTER TABLE event_player ADD COLUMN role TEXT DEFAULT 'Player'")
            conn.commit()

        # Migration 003 — add total_yards and notes columns to tee_deck table
        existing_td = [r[1] for r in conn.execute("PRAGMA table_info(tee_deck)").fetchall()]
        if "total_yards" not in existing_td:
            conn.execute("ALTER TABLE tee_deck ADD COLUMN total_yards INTEGER")
            conn.execute("ALTER TABLE tee_deck ADD COLUMN notes TEXT")
            conn.commit()
