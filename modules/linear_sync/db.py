"""Database layer for Linear Sync module."""

import json
import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import config

logger = logging.getLogger(__name__)


class Database:
    """SQLite database for Linear sync state and mappings."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or config.DB_PATH
        self._ensure_db_dir()
        self._init_schema()

    def _ensure_db_dir(self):
        """Ensure the database directory exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

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
            # Issue mapping table - bridges Linear issues and FUB tasks
            conn.execute("""
                CREATE TABLE IF NOT EXISTS issue_map (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    linear_issue_id TEXT UNIQUE,
                    linear_identifier TEXT,
                    fub_task_id INTEGER UNIQUE,
                    fub_person_id INTEGER,
                    fub_deal_id INTEGER,
                    linear_team_id TEXT,
                    linear_project_id TEXT,
                    person_label_id TEXT,
                    origin TEXT NOT NULL,
                    sync_status TEXT DEFAULT 'synced',
                    last_synced_at TEXT,
                    linear_updated_at TEXT,
                    fub_updated_at TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)

            # Linear cache - snapshot of Linear issues
            conn.execute("""
                CREATE TABLE IF NOT EXISTS linear_cache (
                    id TEXT PRIMARY KEY,
                    identifier TEXT,
                    title TEXT NOT NULL,
                    description TEXT,
                    priority INTEGER,
                    state_id TEXT,
                    state_name TEXT,
                    state_type TEXT,
                    team_id TEXT,
                    team_name TEXT,
                    project_id TEXT,
                    project_name TEXT,
                    due_date TEXT,
                    completed_at TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    label_ids TEXT,
                    label_names TEXT,
                    fetched_at TEXT DEFAULT (datetime('now'))
                )
            """)

            # Deal cache - snapshot of FUB deals for quick lookups
            conn.execute("""
                CREATE TABLE IF NOT EXISTS deal_cache (
                    id INTEGER PRIMARY KEY,
                    person_id INTEGER NOT NULL,
                    pipeline_id INTEGER,
                    stage_id INTEGER,
                    stage_name TEXT,
                    deal_name TEXT,
                    deal_value REAL,
                    property_address TEXT,
                    property_city TEXT,
                    close_date TEXT,
                    fetched_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT
                )
            """)

            # Person label mapping - tracks Linear labels for people
            conn.execute("""
                CREATE TABLE IF NOT EXISTS person_labels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fub_person_id INTEGER UNIQUE,
                    fub_person_name TEXT,
                    linear_label_id TEXT,
                    linear_label_name TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)

            # Team config - stores Linear team configuration
            conn.execute("""
                CREATE TABLE IF NOT EXISTS team_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    team_key TEXT UNIQUE NOT NULL,
                    team_id TEXT NOT NULL,
                    team_name TEXT,
                    process_group TEXT,
                    default_state_id TEXT,
                    completed_state_id TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)

            # Sync state - key-value store for sync cursors
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)

            # Sync log - audit trail
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT DEFAULT (datetime('now')),
                    direction TEXT NOT NULL,
                    action TEXT NOT NULL,
                    linear_issue_id TEXT,
                    fub_task_id INTEGER,
                    fub_person_id INTEGER,
                    fub_deal_id INTEGER,
                    details TEXT,
                    status TEXT DEFAULT 'success'
                )
            """)

            # Indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_issue_map_linear ON issue_map(linear_issue_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_issue_map_fub ON issue_map(fub_task_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_issue_map_person ON issue_map(fub_person_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_linear_cache_team ON linear_cache(team_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_cache_person ON deal_cache(person_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_person_labels_fub ON person_labels(fub_person_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sync_log_time ON sync_log(timestamp)")

    # =========================================================================
    # SYNC STATE
    # =========================================================================

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
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = datetime('now')
            """, (key, value))

    # =========================================================================
    # ISSUE MAPPINGS
    # =========================================================================

    def get_mapping_by_linear(self, linear_issue_id: str) -> Optional[dict]:
        """Get mapping by Linear issue ID."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM issue_map WHERE linear_issue_id = ?",
                (linear_issue_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_mapping_by_fub(self, fub_task_id: int) -> Optional[dict]:
        """Get mapping by FUB task ID."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM issue_map WHERE fub_task_id = ?",
                (fub_task_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_mappings_by_person(self, fub_person_id: int) -> list[dict]:
        """Get all mappings for a person."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM issue_map WHERE fub_person_id = ?",
                (fub_person_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def create_mapping(
        self,
        linear_issue_id: str,
        linear_identifier: str,
        fub_task_id: int,
        fub_person_id: int,
        origin: str,
        linear_team_id: str = None,
        linear_project_id: str = None,
        fub_deal_id: int = None,
        person_label_id: str = None,
        linear_updated_at: str = None,
        fub_updated_at: str = None,
    ) -> int:
        """Create a new mapping."""
        with self.connection() as conn:
            cursor = conn.execute("""
                INSERT INTO issue_map (
                    linear_issue_id, linear_identifier, fub_task_id, fub_person_id,
                    fub_deal_id, linear_team_id, linear_project_id, person_label_id,
                    origin, sync_status, last_synced_at, linear_updated_at, fub_updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'synced', datetime('now'), ?, ?)
            """, (
                linear_issue_id, linear_identifier, fub_task_id, fub_person_id,
                fub_deal_id, linear_team_id, linear_project_id, person_label_id,
                origin, linear_updated_at, fub_updated_at
            ))
            return cursor.lastrowid

    def update_mapping(
        self,
        mapping_id: int,
        sync_status: str = None,
        linear_updated_at: str = None,
        fub_updated_at: str = None,
    ):
        """Update a mapping."""
        updates = ["updated_at = datetime('now')", "last_synced_at = datetime('now')"]
        params = []

        if sync_status is not None:
            updates.append("sync_status = ?")
            params.append(sync_status)
        if linear_updated_at is not None:
            updates.append("linear_updated_at = ?")
            params.append(linear_updated_at)
        if fub_updated_at is not None:
            updates.append("fub_updated_at = ?")
            params.append(fub_updated_at)

        params.append(mapping_id)

        with self.connection() as conn:
            conn.execute(
                f"UPDATE issue_map SET {', '.join(updates)} WHERE id = ?",
                params
            )

    def delete_mapping(self, mapping_id: int):
        """Delete a mapping."""
        with self.connection() as conn:
            conn.execute("DELETE FROM issue_map WHERE id = ?", (mapping_id,))

    def get_all_mappings(self) -> list[dict]:
        """Get all mappings."""
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM issue_map ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

    # =========================================================================
    # PERSON LABELS
    # =========================================================================

    def get_person_label(self, fub_person_id: int) -> Optional[dict]:
        """Get Linear label for a FUB person."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM person_labels WHERE fub_person_id = ?",
                (fub_person_id,)
            ).fetchone()
            return dict(row) if row else None

    def set_person_label(
        self,
        fub_person_id: int,
        fub_person_name: str,
        linear_label_id: str,
        linear_label_name: str,
    ):
        """Set or update Linear label for a FUB person."""
        with self.connection() as conn:
            conn.execute("""
                INSERT INTO person_labels (
                    fub_person_id, fub_person_name, linear_label_id, linear_label_name
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(fub_person_id) DO UPDATE SET
                    fub_person_name = excluded.fub_person_name,
                    linear_label_id = excluded.linear_label_id,
                    linear_label_name = excluded.linear_label_name
            """, (fub_person_id, fub_person_name, linear_label_id, linear_label_name))

    def get_all_person_labels(self) -> list[dict]:
        """Get all person labels."""
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM person_labels").fetchall()
            return [dict(r) for r in rows]

    # =========================================================================
    # TEAM CONFIG
    # =========================================================================

    def get_team_config(self, team_key: str) -> Optional[dict]:
        """Get team configuration by key."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM team_config WHERE team_key = ?",
                (team_key,)
            ).fetchone()
            return dict(row) if row else None

    def set_team_config(
        self,
        team_key: str,
        team_id: str,
        team_name: str,
        process_group: str,
        default_state_id: str = None,
        completed_state_id: str = None,
    ):
        """Set or update team configuration."""
        with self.connection() as conn:
            conn.execute("""
                INSERT INTO team_config (
                    team_key, team_id, team_name, process_group,
                    default_state_id, completed_state_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(team_key) DO UPDATE SET
                    team_id = excluded.team_id,
                    team_name = excluded.team_name,
                    process_group = excluded.process_group,
                    default_state_id = excluded.default_state_id,
                    completed_state_id = excluded.completed_state_id
            """, (team_key, team_id, team_name, process_group, default_state_id, completed_state_id))

    def get_all_team_configs(self) -> list[dict]:
        """Get all team configurations."""
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM team_config").fetchall()
            return [dict(r) for r in rows]

    # =========================================================================
    # LINEAR CACHE
    # =========================================================================

    def cache_issue(self, issue: 'LinearIssue'):
        """Cache a Linear issue."""
        with self.connection() as conn:
            conn.execute("""
                INSERT INTO linear_cache (
                    id, identifier, title, description, priority,
                    state_id, state_name, state_type, team_id, team_name,
                    project_id, project_name, due_date, completed_at,
                    created_at, updated_at, label_ids, label_names, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    identifier = excluded.identifier,
                    title = excluded.title,
                    description = excluded.description,
                    priority = excluded.priority,
                    state_id = excluded.state_id,
                    state_name = excluded.state_name,
                    state_type = excluded.state_type,
                    team_id = excluded.team_id,
                    team_name = excluded.team_name,
                    project_id = excluded.project_id,
                    project_name = excluded.project_name,
                    due_date = excluded.due_date,
                    completed_at = excluded.completed_at,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    label_ids = excluded.label_ids,
                    label_names = excluded.label_names,
                    fetched_at = datetime('now')
            """, (
                issue.id, issue.identifier, issue.title, issue.description, issue.priority,
                issue.state_id, issue.state_name, issue.state_type, issue.team_id, issue.team_name,
                issue.project_id, issue.project_name, issue.due_date, issue.completed_at,
                issue.created_at, issue.updated_at,
                json.dumps(issue.label_ids), json.dumps(issue.label_names)
            ))

    def get_cached_issue(self, issue_id: str) -> Optional[dict]:
        """Get a cached issue."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM linear_cache WHERE id = ?", (issue_id,)
            ).fetchone()
            return dict(row) if row else None

    # =========================================================================
    # DEAL CACHE
    # =========================================================================

    def cache_deal(self, deal: 'FUBDeal'):
        """Cache a FUB deal."""
        with self.connection() as conn:
            conn.execute("""
                INSERT INTO deal_cache (
                    id, person_id, pipeline_id, stage_id, stage_name,
                    deal_name, deal_value, property_address, property_city,
                    close_date, fetched_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
                ON CONFLICT(id) DO UPDATE SET
                    person_id = excluded.person_id,
                    pipeline_id = excluded.pipeline_id,
                    stage_id = excluded.stage_id,
                    stage_name = excluded.stage_name,
                    deal_name = excluded.deal_name,
                    deal_value = excluded.deal_value,
                    property_address = excluded.property_address,
                    property_city = excluded.property_city,
                    close_date = excluded.close_date,
                    fetched_at = datetime('now'),
                    updated_at = excluded.updated_at
            """, (
                deal.id, deal.person_id, deal.pipeline_id, deal.stage_id, deal.stage_name,
                deal.name, deal.price, deal.property_address, deal.property_city,
                deal.close_date, deal.updated
            ))

    def get_cached_deal(self, deal_id: int) -> Optional[dict]:
        """Get a cached deal."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM deal_cache WHERE id = ?", (deal_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_cached_deals_for_person(self, person_id: int) -> list[dict]:
        """Get cached deals for a person."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM deal_cache WHERE person_id = ?",
                (person_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    # =========================================================================
    # SYNC LOG
    # =========================================================================

    def log_sync(
        self,
        direction: str,
        action: str,
        linear_issue_id: str = None,
        fub_task_id: int = None,
        fub_person_id: int = None,
        fub_deal_id: int = None,
        details: dict = None,
        status: str = 'success',
    ):
        """Log a sync action."""
        with self.connection() as conn:
            conn.execute("""
                INSERT INTO sync_log (
                    direction, action, linear_issue_id, fub_task_id,
                    fub_person_id, fub_deal_id, details, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                direction, action, linear_issue_id, fub_task_id,
                fub_person_id, fub_deal_id,
                json.dumps(details) if details else None,
                status
            ))

    def get_recent_logs(self, limit: int = 50) -> list[dict]:
        """Get recent sync logs."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM sync_log ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_sync_stats(self) -> dict:
        """Get sync statistics."""
        with self.connection() as conn:
            # Total mappings
            total = conn.execute("SELECT COUNT(*) as c FROM issue_map").fetchone()['c']

            # By origin
            by_origin = conn.execute("""
                SELECT origin, COUNT(*) as c FROM issue_map GROUP BY origin
            """).fetchall()

            # By status
            by_status = conn.execute("""
                SELECT sync_status, COUNT(*) as c FROM issue_map GROUP BY sync_status
            """).fetchall()

            # Recent log counts
            today = datetime.now().strftime('%Y-%m-%d')
            today_logs = conn.execute("""
                SELECT action, COUNT(*) as c FROM sync_log
                WHERE timestamp >= ? GROUP BY action
            """, (today,)).fetchall()

            return {
                'total_mappings': total,
                'by_origin': {r['origin']: r['c'] for r in by_origin},
                'by_status': {r['sync_status']: r['c'] for r in by_status},
                'today_actions': {r['action']: r['c'] for r in today_logs},
            }


# Module-level singleton
db = Database()
