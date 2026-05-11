"""
Database management for Task Sync module (Postgres-backed).

Bridges Todoist <-> FUB. Tables live in the dreams Postgres DB with the
task_sync_* prefix. Schema is created idempotently at module load via
CREATE TABLE IF NOT EXISTS. The legacy data/task_sync.db SQLite store
has been migrated; see scripts/migrate_task_sync_to_postgres.py.
"""

import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# ISO-8601 UTC timestamp matching the prior SQLite datetime('now') usage
# closely enough that downstream code that JSON-encodes or displays these
# strings sees no behavioral change.
_TS_DEFAULT = "to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS')"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS task_sync_task_map (
    id SERIAL PRIMARY KEY,
    todoist_task_id TEXT UNIQUE,
    fub_task_id INTEGER UNIQUE,
    fub_person_id INTEGER,
    fub_deal_id INTEGER,
    todoist_project_id TEXT,
    todoist_section_id TEXT,
    origin TEXT NOT NULL,
    sync_status TEXT DEFAULT 'synced',
    last_synced_at TEXT,
    todoist_updated_at TEXT,
    fub_updated_at TEXT,
    created_at TEXT DEFAULT {_TS_DEFAULT},
    updated_at TEXT DEFAULT {_TS_DEFAULT}
);
CREATE INDEX IF NOT EXISTS idx_task_sync_task_map_todoist ON task_sync_task_map(todoist_task_id);
CREATE INDEX IF NOT EXISTS idx_task_sync_task_map_fub ON task_sync_task_map(fub_task_id);
CREATE INDEX IF NOT EXISTS idx_task_sync_task_map_deal ON task_sync_task_map(fub_deal_id);
CREATE INDEX IF NOT EXISTS idx_task_sync_task_map_person ON task_sync_task_map(fub_person_id);
CREATE INDEX IF NOT EXISTS idx_task_sync_task_map_status ON task_sync_task_map(sync_status);

CREATE TABLE IF NOT EXISTS task_sync_deal_cache (
    id INTEGER PRIMARY KEY,
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
    fetched_at TEXT DEFAULT {_TS_DEFAULT},
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_task_sync_deal_cache_person ON task_sync_deal_cache(person_id);
CREATE INDEX IF NOT EXISTS idx_task_sync_deal_cache_stage ON task_sync_deal_cache(stage_id);

CREATE TABLE IF NOT EXISTS task_sync_todoist_projects (
    id SERIAL PRIMARY KEY,
    todoist_project_id TEXT UNIQUE NOT NULL,
    project_name TEXT NOT NULL,
    fub_pipeline_id INTEGER,
    fub_stage_id INTEGER,
    project_type TEXT NOT NULL,
    created_at TEXT DEFAULT {_TS_DEFAULT}
);

CREATE TABLE IF NOT EXISTS task_sync_sync_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT {_TS_DEFAULT}
);

CREATE TABLE IF NOT EXISTS task_sync_sync_log (
    id SERIAL PRIMARY KEY,
    timestamp TEXT DEFAULT {_TS_DEFAULT},
    direction TEXT NOT NULL,
    action TEXT NOT NULL,
    todoist_task_id TEXT,
    fub_task_id INTEGER,
    fub_deal_id INTEGER,
    details TEXT,
    status TEXT DEFAULT 'success'
);
CREATE INDEX IF NOT EXISTS idx_task_sync_sync_log_timestamp ON task_sync_sync_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_task_sync_sync_log_status ON task_sync_sync_log(status);
"""


class Database:
    """Task sync database manager (Postgres-backed via pg_adapter)."""

    def __init__(self):
        self._init_schema()

    def _get_connection(self):
        """Get a pooled Postgres connection wrapped for sqlite3-compatible interface."""
        from src.core.pg_adapter import get_db
        return get_db()

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
        """Initialize database schema (idempotent)."""
        with self.connection() as conn:
            conn.executescript(SCHEMA)

    # ==========================================================================
    # Sync State
    # ==========================================================================

    def get_state(self, key: str) -> Optional[str]:
        """Get a sync state value."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT value FROM task_sync_sync_state WHERE key = ?", (key,)
            ).fetchone()
            return row['value'] if row else None

    def set_state(self, key: str, value: str):
        """Set a sync state value."""
        with self.connection() as conn:
            conn.execute(
                f"INSERT INTO task_sync_sync_state (key, value, updated_at) "
                f"VALUES (?, ?, {_TS_DEFAULT}) "
                f"ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                f"updated_at = excluded.updated_at",
                (key, value)
            )

    # ==========================================================================
    # Task Map (Bridge Table)
    # ==========================================================================

    def get_mapping_by_fub_id(self, fub_task_id: int) -> Optional[dict]:
        """Get task mapping by FUB task ID."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM task_sync_task_map WHERE fub_task_id = ?", (fub_task_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_mapping_by_todoist_id(self, todoist_task_id: str) -> Optional[dict]:
        """Get task mapping by Todoist task ID."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM task_sync_task_map WHERE todoist_task_id = ?", (todoist_task_id,)
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
            cursor = conn.execute(
                f"INSERT INTO task_sync_task_map ("
                f"    fub_task_id, todoist_task_id, fub_person_id, fub_deal_id,"
                f"    todoist_project_id, todoist_section_id, origin,"
                f"    sync_status, last_synced_at"
                f") VALUES (?, ?, ?, ?, ?, ?, ?, 'synced', {_TS_DEFAULT}) "
                f"RETURNING id",
                (fub_task_id, todoist_task_id, fub_person_id, fub_deal_id,
                 todoist_project_id, todoist_section_id, origin)
            )
            return cursor.fetchone()['id']

    def update_mapping(self, mapping_id: int, **kwargs):
        """Update a task mapping."""
        if not kwargs:
            return

        kwargs['updated_at'] = datetime.now().isoformat()

        sets = ', '.join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [mapping_id]

        with self.connection() as conn:
            conn.execute(f"UPDATE task_sync_task_map SET {sets} WHERE id = ?", values)

    def get_pending_syncs(self, direction: str) -> list[dict]:
        """Get tasks pending sync in a direction."""
        status = f'pending_to_{"todoist" if direction == "fub_to_todoist" else "fub"}'
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM task_sync_task_map WHERE sync_status = ?", (status,)
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
                INSERT INTO task_sync_sync_log (
                    direction, action, todoist_task_id, fub_task_id,
                    fub_deal_id, details, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (direction, action, todoist_task_id, fub_task_id, fub_deal_id, details, status))

    def get_recent_logs(self, limit: int = 50) -> list[dict]:
        """Get recent sync log entries."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM task_sync_sync_log ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(row) for row in rows]

    # ==========================================================================
    # Deal Cache
    # ==========================================================================

    def cache_deal(self, deal: dict):
        """Cache a FUB deal for quick lookups."""
        with self.connection() as conn:
            conn.execute("""
                INSERT INTO task_sync_deal_cache (
                    id, person_id, pipeline_id, stage_id, stage_name,
                    deal_name, deal_value, property_address, property_city,
                    property_state, property_zip, person_name, person_email,
                    person_phone, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    person_id = excluded.person_id,
                    pipeline_id = excluded.pipeline_id,
                    stage_id = excluded.stage_id,
                    stage_name = excluded.stage_name,
                    deal_name = excluded.deal_name,
                    deal_value = excluded.deal_value,
                    property_address = excluded.property_address,
                    property_city = excluded.property_city,
                    property_state = excluded.property_state,
                    property_zip = excluded.property_zip,
                    person_name = excluded.person_name,
                    person_email = excluded.person_email,
                    person_phone = excluded.person_phone,
                    fetched_at = """ + _TS_DEFAULT + """,
                    updated_at = excluded.updated_at
            """, (
                deal.get('id'),
                deal.get('person_id'),
                deal.get('pipeline_id'),
                deal.get('stage_id'),
                deal.get('stage_name'),
                deal.get('deal_name'),
                deal.get('deal_value'),
                deal.get('property_address'),
                deal.get('property_city'),
                deal.get('property_state'),
                deal.get('property_zip'),
                deal.get('person_name'),
                deal.get('person_email'),
                deal.get('person_phone'),
                deal.get('updated'),
            ))

    def get_cached_deal(self, deal_id: int) -> Optional[dict]:
        """Get a cached deal by ID."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM task_sync_deal_cache WHERE id = ?", (deal_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_deals_for_person(self, person_id: int) -> list[dict]:
        """Get all cached deals for a person."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM task_sync_deal_cache WHERE person_id = ? ORDER BY updated_at DESC", (person_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    # ==========================================================================
    # Dashboard Queries
    # ==========================================================================

    def get_dashboard_tasks(self, limit: int = 10) -> list[dict]:
        """Get tasks for dashboard display."""
        with self.connection() as conn:
            rows = conn.execute("""
                SELECT
                    tm.id as mapping_id,
                    tm.todoist_task_id,
                    tm.fub_task_id,
                    tm.fub_person_id,
                    tm.fub_deal_id,
                    tm.todoist_project_id,
                    tm.sync_status,
                    tm.last_synced_at,
                    dc.person_name,
                    dc.stage_name as deal_stage,
                    dc.deal_name,
                    dc.property_address
                FROM task_sync_task_map tm
                LEFT JOIN task_sync_deal_cache dc ON tm.fub_deal_id = dc.id
                WHERE tm.sync_status = 'synced'
                ORDER BY tm.last_synced_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(row) for row in rows]

    def get_all_mappings(self, include_completed: bool = False) -> list[dict]:
        """Get all task mappings for dashboard display."""
        with self.connection() as conn:
            rows = conn.execute("""
                SELECT
                    tm.*,
                    dc.person_name,
                    dc.stage_name as deal_stage,
                    dc.deal_name,
                    dc.property_address
                FROM task_sync_task_map tm
                LEFT JOIN task_sync_deal_cache dc ON tm.fub_deal_id = dc.id
                ORDER BY tm.created_at DESC
            """).fetchall()
            return [dict(row) for row in rows]


# Module-level instance
db = Database()
