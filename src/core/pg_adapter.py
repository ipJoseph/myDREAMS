"""
PostgreSQL adapter with sqlite3-compatible interface.

Drop-in replacement for sqlite3 connections. Translates ? → %s for
parameterized queries and returns dict-like rows. This lets the 163
methods in DREAMSDatabase and 16 get_db() functions across the codebase
work with PostgreSQL without rewriting their SQL.

Usage:
    from src.core.pg_adapter import get_connection, raw_connection

    # Via the adapter (sqlite3-compatible interface):
    with get_connection() as conn:
        conn.execute("INSERT INTO leads (id, email) VALUES (?, ?)", [id, email])
        conn.commit()

    # Raw psycopg2 connection (for code that needs PostgreSQL-specific features):
    with raw_connection() as conn:
        ...

When DATABASE_URL is not set, falls back to sqlite3 so DEV keeps working.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

logger = logging.getLogger(__name__)

# Check if psycopg2 is available
try:
    import psycopg2
    import psycopg2.extras
    import psycopg2.pool
    _PG_AVAILABLE = True
    _PG_IMPORT_ERROR: Optional[str] = None
except ImportError as _pg_err:
    _PG_AVAILABLE = False
    _PG_IMPORT_ERROR = str(_pg_err)

_pool: Optional[Any] = None  # psycopg2.pool.ThreadedConnectionPool


def _get_database_url() -> Optional[str]:
    """Get DATABASE_URL from environment. Returns None if not set."""
    url = os.getenv("DATABASE_URL", "").strip()
    return url if url else None


# Fail loudly at module import when DATABASE_URL is set but psycopg2 is
# missing. Silent fallback to SQLite was the root cause of a real PRD
# incident: services kept running, pointed at a stale 905 MB SQLite file,
# and nobody noticed for days. Crash-fast is the correct behaviour.
#
# The DREAMS_ALLOW_SQLITE_FALLBACK escape hatch was removed — there is no
# scenario where production should run on SQLite. Fix the deployment.
def _assert_backend_consistent() -> None:
    url = _get_database_url()
    if url and not _PG_AVAILABLE:
        raise ImportError(
            "DATABASE_URL is set but psycopg2 is NOT installed in this "
            "Python environment. SQLite fallback has been removed. "
            "FIX: pip install psycopg2-binary."
        )


_assert_backend_consistent()


def is_postgres() -> bool:
    """True if we're configured to use PostgreSQL."""
    return bool(_get_database_url()) and _PG_AVAILABLE


def active_backend() -> str:
    """Return 'postgres' or 'sqlite' for health-check reporting."""
    return "postgres" if is_postgres() else "sqlite"


def _get_pool():
    """Get or create the connection pool."""
    global _pool
    if _pool is None:
        url = _get_database_url()
        if not url:
            raise RuntimeError("DATABASE_URL not set")
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=5,
            dsn=url,
        )
        logger.info("PostgreSQL connection pool created (min=2, max=5)")
    return _pool


class PgCursorWrapper:
    """
    Wraps a psycopg2 cursor to return dict-like rows (matching sqlite3.Row behavior).
    """

    def __init__(self, cursor):
        self._cursor = cursor
        self.description = cursor.description
        self.rowcount = cursor.rowcount
        self.lastrowid = None

    def fetchone(self) -> Optional[Dict[str, Any]]:
        row = self._cursor.fetchone()
        if row is None:
            return None
        # RealDictRow is already dict-like, but convert to regular dict
        # so it supports both dict[key] and tuple indexing
        return DictRow(row)

    def fetchall(self) -> List[Dict[str, Any]]:
        rows = self._cursor.fetchall()
        return [DictRow(r) for r in rows]

    def __iter__(self):
        return self

    def __next__(self):
        row = self._cursor.fetchone()
        if row is None:
            raise StopIteration
        return DictRow(row)


class DictRow(dict):
    """
    Dict that also supports integer indexing (like sqlite3.Row).
    This is needed because some code does `row[0]` while other code does `row['id']`.
    """

    def __init__(self, mapping):
        super().__init__(mapping)
        self._keys = list(mapping.keys())

    def __getitem__(self, key):
        if isinstance(key, int):
            return super().__getitem__(self._keys[key])
        return super().__getitem__(key)


# Regex to translate ? placeholders to %s, but NOT inside quoted strings
# This handles: "INSERT INTO t (a, b) VALUES (?, ?)" → "INSERT INTO t (a, b) VALUES (%s, %s)"
# It skips ? inside single-quoted strings like "WHERE name = 'what?'"
def _translate_placeholders(query: str) -> str:
    """Translate sqlite3 ? placeholders to psycopg2 %s placeholders.

    Handles:
    - '' (escaped single quote inside a string literal) without toggling in_quote
    - % in LIKE patterns (escaped to %% for psycopg2)
    """
    result = []
    in_quote = False
    i = 0
    while i < len(query):
        ch = query[i]
        if ch == "'":
            if in_quote and i + 1 < len(query) and query[i + 1] == "'":
                # Escaped single quote inside a string literal — emit both, stay in quote
                result.append("''")
                i += 2
                continue
            in_quote = not in_quote
            result.append(ch)
        elif ch == '?' and not in_quote:
            result.append('%s')
        elif ch == '%':
            # psycopg2 interprets % in the entire query string, including inside
            # SQL string literals. All % must be doubled.
            result.append('%%')
        else:
            result.append(ch)
        i += 1

    return ''.join(result)


class PgConnectionWrapper:
    """
    Wraps a psycopg2 connection to provide a sqlite3-compatible interface.
    """

    def __init__(self, conn):
        self._conn = conn
        self._cursor = None

    def execute(self, query: str, params: Any = None) -> PgCursorWrapper:
        """Execute a query with sqlite3-style ? placeholders."""
        pg_query = _translate_placeholders(query)

        # Normalise params to a tuple for psycopg2. We DO NOT coerce bool
        # to int here: psycopg2 maps Python bool -> PostgreSQL boolean
        # natively, which is what every boolean column in the schema
        # actually wants (e.g. listings.photo_ready, idx_opt_in, etc.).
        # The previous bool->int coercion broke every sync UPDATE that
        # touched a boolean column with "column ... is of type boolean
        # but expression is of type integer" — that was the second half
        # of the 2026-04-20 PRD incident. If any caller is passing a
        # Python bool to an INTEGER column, fix the caller.
        if isinstance(params, list):
            params = tuple(params)

        cursor = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cursor.execute(pg_query, params)
        except Exception:
            # Log the failed query for debugging (without params to avoid PII)
            logger.debug("Failed query: %s", pg_query[:200])
            raise

        wrapper = PgCursorWrapper(cursor)
        self._cursor = wrapper
        return wrapper

    def executemany(self, query: str, params_list: Sequence) -> None:
        """Execute a query with multiple parameter sets."""
        pg_query = _translate_placeholders(query)
        cursor = self._conn.cursor()
        params_as_tuples = [tuple(p) if isinstance(p, list) else p for p in params_list]
        cursor.executemany(pg_query, params_as_tuples)

    def executescript(self, script: str) -> None:
        """Execute multiple SQL statements (PostgreSQL equivalent of sqlite3.executescript)."""
        cursor = self._conn.cursor()
        cursor.execute(script)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        """Return connection to pool instead of closing."""
        try:
            self._conn.rollback()  # Cancel any uncommitted transaction
        except Exception:
            pass
        try:
            _get_pool().putconn(self._conn)
        except Exception:
            try:
                self._conn.close()
            except Exception:
                pass

    def fetchone(self) -> Optional[Dict[str, Any]]:
        if self._cursor:
            return self._cursor.fetchone()
        return None

    def fetchall(self) -> List[Dict[str, Any]]:
        if self._cursor:
            return self._cursor.fetchall()
        return []

    @property
    def row_factory(self):
        return None

    @row_factory.setter
    def row_factory(self, value):
        pass  # No-op; we always return dicts

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        self.close()
        return False


def get_connection() -> PgConnectionWrapper:
    """Get a PostgreSQL connection from the pool, wrapped for sqlite3 compatibility."""
    pool = _get_pool()
    conn = pool.getconn()
    conn.autocommit = False
    return PgConnectionWrapper(conn)


@contextmanager
def raw_connection():
    """
    Context manager yielding a raw psycopg2 connection from the pool.

    The connection is returned to the pool on exit, even if an exception
    is raised. Use this for migration scripts or code that needs
    PostgreSQL-specific features not available through PgConnectionWrapper.

    Usage:
        with raw_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
    """
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)


@contextmanager
def get_connection_ctx():
    """Context manager for PostgreSQL connections."""
    conn = get_connection()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Unified get_db() for all apps
# ---------------------------------------------------------------------------

def get_db(db_path: Optional[str] = None):
    """
    Unified database connection factory.

    When DATABASE_URL is set: returns a pooled PostgreSQL connection wrapped
    for sqlite3-compatible interface. The db_path argument is ignored.

    When DATABASE_URL is NOT set and db_path is provided: returns a raw
    sqlite3 connection (test-isolation mode only). This path is intentionally
    narrow — production must always have DATABASE_URL set.

    When DATABASE_URL is NOT set and db_path is None: raises RuntimeError
    (no silent fallback to the orphan data/dreams.db).
    """
    if is_postgres():
        return get_connection()

    if db_path:
        # Test-isolation mode: SQLite with the explicit path.
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    raise RuntimeError(
        "pg_adapter.get_db() requires DATABASE_URL to be set. "
        "The SQLite fallback (data/dreams.db) is removed; production "
        "must run on Postgres. For test-mode SQLite isolation, unset "
        "DATABASE_URL and pass an explicit db_path."
    )
