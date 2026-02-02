"""
Database management for Task Sync module.

SQLite with WAL mode for concurrent access.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from .config import config


SCHEMA = """
-- Bridge table: maps task IDs between systems and associates with deals
CREATE TABLE IF NOT EXISTS task_map (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    todoist_task_id TEXT UNIQUE,
    fub_task_id INTEGER UNIQUE,
    fub_person_id INTEGER,
    fub_deal_id INTEGER,
    todoist_project_id TEXT,
    todoist_section_id TEXT,
    origin TEXT NOT NULL,  -- 'todoist' or 'fub'
    sync_status TEXT DEFAULT 'synced',  -- synced, pending_to_todoist, pending_to_fub, conflict, error
    last_synced_at TEXT,
    todoist_updated_at TEXT,
    fub_updated_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_task_map_todoist ON task_map(todoist_task_id);
CREATE INDEX IF NOT EXISTS idx_task_map_fub ON task_map(fub_task_id);
CREATE INDEX IF NOT EXISTS idx_task_map_deal ON task_map(fub_deal_id);
CREATE INDEX IF NOT EXISTS idx_task_map_person ON task_map(fub_person_id);
CREATE INDEX IF NOT EXISTS idx_task_map_status ON task_map(sync_status);

-- Deal cache: local snapshot of FUB deals
CREATE TABLE IF NOT EXISTS deal_cache (
    id INTEGER PRIMARY KEY,  -- FUB deal ID
    person_id INTEGER NOT NULL,
    pipeline_id INTEGER,
    stage_id INTEGER,
    stage_name TEXT,
    deal_name TEXT,
    deal_value REAL,
    property_address TEXT,
    property_city TEXT,
    property_state TEXT,
    property_zip TEXT,
    person_name TEXT,
    person_email TEXT,
    person_phone TEXT,
    todoist_project_id TEXT,
    todoist_section_id TEXT,
    fetched_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_deal_cache_person ON deal_cache(person_id);
CREATE INDEX IF NOT EXISTS idx_deal_cache_stage ON deal_cache(stage_id);

-- Todoist project/section mapping
CREATE TABLE IF NOT EXISTS todoist_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    todoist_project_id TEXT UNIQUE NOT NULL,
    project_name TEXT NOT NULL,
    fub_pipeline_id INTEGER,
    fub_stage_id INTEGER,
    project_type TEXT NOT NULL,  -- 'pipeline_stage', 'general', 'personal'
    created_at TEXT DEFAULT (datetime('now'))
);

-- Sync state: cursors, tokens, timestamps
CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Sync log: audit trail
CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    direction TEXT NOT NULL,  -- 'fub_to_todoist', 'todoist_to_fub', 'internal'
    action TEXT NOT NULL,  -- 'create', 'update', 'complete', 'delete', 'move', 'error'
    todoist_task_id TEXT,
    fub_task_id INTEGER,
    fub_deal_id INTEGER,
    details TEXT,  -- JSON
    status TEXT DEFAULT 'success'
);

CREATE INDEX IF NOT EXISTS idx_sync_log_timestamp ON sync_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_sync_log_status ON sync_log(status);
"""


class Database:
    """Task sync database manager."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or config.DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with WAL mode."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def connection(self):
        """Context manager for database connections."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self):
        """Initialize database schema."""
        with self.connection() as conn:
            conn.executescript(SCHEMA)

    # ==========================================================================
    # Sync State
    # ==========================================================================

    def get_state(self, key: str) -> Optional[str]:
        """Get a sync state value."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT value FROM sync_state WHERE key = ?", (key,)
            ).fetchone()
            return row['value'] if row else None

    def set_state(self, key: str, value: str):
        """Set a sync state value."""
        with self.connection() as conn:
            conn.execute("""
                INSERT INTO sync_state (key, value, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = datetime('now')
            """, (key, value, value))

    # ==========================================================================
    # Task Map (Bridge Table)
    # ==========================================================================

    def get_mapping_by_fub_id(self, fub_task_id: int) -> Optional[dict]:
        """Get task mapping by FUB task ID."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM task_map WHERE fub_task_id = ?", (fub_task_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_mapping_by_todoist_id(self, todoist_task_id: str) -> Optional[dict]:
        """Get task mapping by Todoist task ID."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM task_map WHERE todoist_task_id = ?", (todoist_task_id,)
            ).fetchone()
            return dict(row) if row else None

    def create_mapping(
        self,
        fub_task_id: Optional[int] = None,
        todoist_task_id: Optional[str] = None,
        fub_person_id: Optional[int] = None,
        fub_deal_id: Optional[int] = None,
        todoist_project_id: Optional[str] = None,
        todoist_section_id: Optional[str] = None,
        origin: str = 'fub'
    ) -> int:
        """Create a new task mapping. Returns mapping ID."""
        with self.connection() as conn:
            cursor = conn.execute("""
                INSERT INTO task_map (
                    fub_task_id, todoist_task_id, fub_person_id, fub_deal_id,
                    todoist_project_id, todoist_section_id, origin,
                    sync_status, last_synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'synced', datetime('now'))
            """, (
                fub_task_id, todoist_task_id, fub_person_id, fub_deal_id,
                todoist_project_id, todoist_section_id, origin
            ))
            return cursor.lastrowid

    def update_mapping(self, mapping_id: int, **kwargs):
        """Update a task mapping."""
        if not kwargs:
            return

        kwargs['updated_at'] = datetime.now().isoformat()

        sets = ', '.join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [mapping_id]

        with self.connection() as conn:
            conn.execute(f"UPDATE task_map SET {sets} WHERE id = ?", values)

    def get_pending_syncs(self, direction: str) -> list[dict]:
        """Get tasks pending sync in a direction."""
        status = f'pending_to_{"todoist" if direction == "fub_to_todoist" else "fub"}'
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM task_map WHERE sync_status = ?", (status,)
            ).fetchall()
            return [dict(row) for row in rows]

    # ==========================================================================
    # Sync Log
    # ==========================================================================

    def log_sync(
        self,
        direction: str,
        action: str,
        todoist_task_id: Optional[str] = None,
        fub_task_id: Optional[int] = None,
        fub_deal_id: Optional[int] = None,
        details: Optional[str] = None,
        status: str = 'success'
    ):
        """Log a sync action."""
        with self.connection() as conn:
            conn.execute("""
                INSERT INTO sync_log (
                    direction, action, todoist_task_id, fub_task_id,
                    fub_deal_id, details, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (direction, action, todoist_task_id, fub_task_id, fub_deal_id, details, status))

    def get_recent_logs(self, limit: int = 50) -> list[dict]:
        """Get recent sync log entries."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM sync_log ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(row) for row in rows]


# Module-level instance
db = Database()
