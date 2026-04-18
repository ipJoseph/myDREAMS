"""
PostgreSQL adapter with sqlite3-compatible interface.

Drop-in replacement for sqlite3 connections. Translates ? → %s for
parameterized queries and returns dict-like rows. This lets the 163
methods in DREAMSDatabase and 16 get_db() functions across the codebase
work with PostgreSQL without rewriting their SQL.

Usage:
    from src.core.pg_adapter import get_connection, get_raw_connection

    # Via the adapter (sqlite3-compatible interface):
    with get_connection() as conn:
        conn.execute("INSERT INTO leads (id, email) VALUES (?, ?)", [id, email])
        conn.commit()

    # Raw psycopg2 connection (for code that needs PostgreSQL-specific features):
    conn = get_raw_connection()

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
except ImportError:
    _PG_AVAILABLE = False

_pool: Optional[Any] = None  # psycopg2.pool.ThreadedConnectionPool


def _get_database_url() -> Optional[str]:
    """Get DATABASE_URL from environment. Returns None if not set."""
    url = os.getenv("DATABASE_URL", "").strip()
    return url if url else None


def is_postgres() -> bool:
    """True if we're configured to use PostgreSQL."""
    return bool(_get_database_url()) and _PG_AVAILABLE


def _get_pool():
    """Get or create the connection pool."""
    global _pool
    if _pool is None:
        url = _get_database_url()
        if not url:
            raise RuntimeError("DATABASE_URL not set")
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=url,
        )
        logger.info("PostgreSQL connection pool created (min=2, max=10)")
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
    """Translate sqlite3 ? placeholders to psycopg2 %s placeholders."""
    # Also escape any literal % signs that aren't already %% (psycopg2 treats % as format)
    # First, protect existing %% pairs
    query = query.replace('%%', '\x00DOUBLEPCT\x00')
    # Escape lone % that aren't followed by s (which would be our translated placeholders)
    # Actually, simpler: just replace ? with %s, then handle % escaping
    # We need to be careful about % in LIKE patterns

    result = []
    in_quote = False
    i = 0
    while i < len(query):
        ch = query[i]
        if ch == "'":
            in_quote = not in_quote
            result.append(ch)
        elif ch == '?' and not in_quote:
            result.append('%s')
        elif ch == '%' and not in_quote:
            # Check if this is already a %s (from our translation) or a LIKE %
            # If next char is 's' and we just added it, skip
            # For LIKE patterns, we need to keep % as-is since psycopg2
            # handles them correctly in parameterized queries
            result.append('%%')
        else:
            result.append(ch)
        i += 1

    out = ''.join(result)
    out = out.replace('\x00DOUBLEPCT\x00', '%%')
    return out


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

        # Convert params: list→tuple, booleans→int (PostgreSQL is strict
        # about boolean vs integer; SQLite treats them interchangeably).
        # See docs/DECISIONS.md D1.
        if params is not None:
            if isinstance(params, (list, tuple)):
                params = tuple(
                    int(p) if isinstance(p, bool) else p for p in params
                )
            elif isinstance(params, bool):
                params = int(params)

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


def get_raw_connection():
    """Get a raw psycopg2 connection (for migration scripts etc.)."""
    pool = _get_pool()
    return pool.getconn()


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

    If DATABASE_URL is set and psycopg2 is available → PostgreSQL (pooled).
    Otherwise → sqlite3 with WAL mode and 30s busy_timeout (existing behavior).

    This function replaces the 16 separate get_db() implementations across
    the codebase. Import it from here instead of creating local connections.
    """
    if is_postgres():
        return get_connection()

    # Fallback to SQLite
    if db_path is None:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        db_path = os.getenv("DREAMS_DB_PATH", os.path.join(project_root, "data", "dreams.db"))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
