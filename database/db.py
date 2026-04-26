"""
db.py — Database connection helper and generic query utilities.
Golf Match Captain | PostgreSQL / Supabase

Uses a connection pool cached via st.cache_resource so the TCP + SSL +
auth handshake happens once per app session instead of once per query.
This is the main performance fix for Supabase free tier.

Credentials: add SUPABASE_DB_URL to .streamlit/secrets.toml
  SUPABASE_DB_URL = "postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres"
"""

from __future__ import annotations

import os
import psycopg2
import psycopg2.pool
import psycopg2.extras


# ---------------------------------------------------------------
# Connection URL
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


# ---------------------------------------------------------------
# Connection pool — cached for the lifetime of the Streamlit app
# ---------------------------------------------------------------

def _get_pool() -> psycopg2.pool.SimpleConnectionPool:
    """
    Return a cached connection pool.
    st.cache_resource keeps it alive across Streamlit reruns so we
    don't pay the connection overhead on every query.
    """
    try:
        import streamlit as st

        @st.cache_resource
        def _build_pool():
            return psycopg2.pool.SimpleConnectionPool(
                minconn=1,
                maxconn=5,
                dsn=_get_db_url(),
            )

        return _build_pool()
    except Exception:
        # Fallback for non-Streamlit contexts (e.g. tests / CLI)
        return psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=5,
            dsn=_get_db_url(),
        )


def _get_conn() -> psycopg2.extensions.connection:
    """
    Get a connection from the pool.
    If the pooled connection has gone stale (Supabase free tier can pause),
    clears the cache and rebuilds the pool automatically.
    """
    try:
        conn = _get_pool().getconn()
        if conn.closed:
            raise psycopg2.OperationalError("Stale connection")
        # Quick liveness check
        conn.cursor().execute("SELECT 1")
        return conn
    except Exception:
        # Clear the cached pool and try once more with a fresh connection
        try:
            import streamlit as st
            st.cache_resource.clear()
        except Exception:
            pass
        conn = _get_pool().getconn()
        return conn


def _put_conn(conn) -> None:
    """Return a connection to the pool."""
    try:
        if not conn.closed:
            _get_pool().putconn(conn)
    except Exception:
        pass


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
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        _put_conn(conn)


def fetchone(sql: str, params: tuple = ()) -> dict | None:
    """Execute a SELECT and return the first row as a dict, or None."""
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        _put_conn(conn)


def execute(sql: str, params: tuple = ()) -> int:
    """
    Execute an INSERT / UPDATE / DELETE.

    For INSERT statements: appends RETURNING * and returns the value of the
    first column (always the SERIAL primary key in this schema).
    For UPDATE / DELETE: returns rowcount.
    """
    is_insert = sql.strip().upper().startswith("INSERT")
    conn = _get_conn()
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
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)


def executemany(sql: str, param_list: list[tuple]) -> None:
    """Execute an INSERT / UPDATE for a list of parameter tuples."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.executemany(sql, param_list)
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_conn(conn)
