"""
db.py — Database connection helper and generic query utilities.
Golf Match Captain | PostgreSQL / Supabase

Replaces the SQLite implementation. All helper function signatures
are identical so no changes are needed in the modules that call them.

Credentials: add SUPABASE_DB_URL to .streamlit/secrets.toml
  SUPABASE_DB_URL = "postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres"
  (Use the Session Pooler URL from Supabase → Settings → Database → Connection string)
"""

from __future__ import annotations

import os
import psycopg2
import psycopg2.extras


# ---------------------------------------------------------------
# Connection
# ---------------------------------------------------------------

def _get_db_url() -> str:
    """Read the PostgreSQL connection URL from Streamlit secrets or env."""
    try:
        import streamlit as st
        url = st.secrets.get("SUPABASE_DB_URL") or st.secrets.get("DATABASE_URL")
        if url:
            return str(url)
    except Exception:
        pass
    url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    if url:
        return url
    raise ValueError(
        "Database URL not configured. "
        "Add SUPABASE_DB_URL to .streamlit/secrets.toml."
    )


def get_connection() -> psycopg2.extensions.connection:
    """Open and return a psycopg2 connection."""
    return psycopg2.connect(_get_db_url())


def initialise_database() -> None:
    """
    No-op: the GMC schema is managed directly in Supabase.
    Run database/schema_supabase.sql once in the Supabase SQL Editor.
    """
    pass


# ---------------------------------------------------------------
# Generic helpers
# (same signatures as the SQLite version — drop-in replacement)
# ---------------------------------------------------------------

def fetchall(sql: str, params: tuple = ()) -> list[dict]:
    """Execute a SELECT and return all rows as plain dicts."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def fetchone(sql: str, params: tuple = ()) -> dict | None:
    """Execute a SELECT and return the first row as a dict, or None."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def execute(sql: str, params: tuple = ()) -> int:
    """
    Execute an INSERT / UPDATE / DELETE.

    For INSERT statements: appends RETURNING * and returns the value of the
    first column (always the SERIAL primary key in this schema).
    For UPDATE / DELETE: returns rowcount.
    """
    is_insert = sql.strip().upper().startswith("INSERT")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if is_insert:
                returning_sql = sql.rstrip().rstrip(";") + " RETURNING *"
                cur.execute(returning_sql, params)
                row = cur.fetchone()
                conn.commit()
                return row[0] if row else 0
            else:
                cur.execute(sql, params)
                conn.commit()
                return cur.rowcount
    finally:
        conn.close()


def executemany(sql: str, param_list: list[tuple]) -> None:
    """Execute an INSERT / UPDATE for a list of parameter tuples."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.executemany(sql, param_list)
            conn.commit()
    finally:
        conn.close()
