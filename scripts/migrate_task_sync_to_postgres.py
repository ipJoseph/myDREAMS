"""
One-shot migration: task_sync.db + linear_sync.db SQLite -> Postgres.

Creates prefixed tables (task_sync_*, linear_sync_*) in the dreams Postgres
database and copies critical state data (sync_state cursor + deal_cache)
from the legacy SQLite files. Skips the bulky sync_log audit trail
(restarts fresh in Postgres).

Idempotent: safe to re-run. Schema uses CREATE TABLE IF NOT EXISTS, data
copy uses ON CONFLICT DO UPDATE so re-runs don't duplicate.

Usage:
    python3 scripts/migrate_task_sync_to_postgres.py             # both modules
    python3 scripts/migrate_task_sync_to_postgres.py --task-only
    python3 scripts/migrate_task_sync_to_postgres.py --linear-only
    python3 scripts/migrate_task_sync_to_postgres.py --schema-only
"""

import argparse
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

TASK_SYNC_DB = PROJECT_ROOT / "data" / "task_sync.db"
LINEAR_SYNC_DB = PROJECT_ROOT / "data" / "linear_sync.db"

# Standard timestamp default: ISO 8601 string in UTC, matches SQLite datetime('now')
TS_DEFAULT = "to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS')"

TASK_SYNC_SCHEMA = f"""
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
    created_at TEXT DEFAULT {TS_DEFAULT},
    updated_at TEXT DEFAULT {TS_DEFAULT}
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
    fetched_at TEXT DEFAULT {TS_DEFAULT},
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
    created_at TEXT DEFAULT {TS_DEFAULT}
);

CREATE TABLE IF NOT EXISTS task_sync_sync_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT {TS_DEFAULT}
);

CREATE TABLE IF NOT EXISTS task_sync_sync_log (
    id SERIAL PRIMARY KEY,
    timestamp TEXT DEFAULT {TS_DEFAULT},
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

LINEAR_SYNC_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS linear_sync_issue_map (
    id SERIAL PRIMARY KEY,
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
    created_at TEXT DEFAULT {TS_DEFAULT},
    updated_at TEXT DEFAULT {TS_DEFAULT}
);
CREATE INDEX IF NOT EXISTS idx_linear_sync_issue_map_linear ON linear_sync_issue_map(linear_issue_id);
CREATE INDEX IF NOT EXISTS idx_linear_sync_issue_map_fub ON linear_sync_issue_map(fub_task_id);
CREATE INDEX IF NOT EXISTS idx_linear_sync_issue_map_person ON linear_sync_issue_map(fub_person_id);

CREATE TABLE IF NOT EXISTS linear_sync_linear_cache (
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
    fetched_at TEXT DEFAULT {TS_DEFAULT}
);
CREATE INDEX IF NOT EXISTS idx_linear_sync_linear_cache_team ON linear_sync_linear_cache(team_id);

CREATE TABLE IF NOT EXISTS linear_sync_deal_cache (
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
    fetched_at TEXT DEFAULT {TS_DEFAULT},
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_linear_sync_deal_cache_person ON linear_sync_deal_cache(person_id);

CREATE TABLE IF NOT EXISTS linear_sync_person_labels (
    id SERIAL PRIMARY KEY,
    fub_person_id INTEGER UNIQUE,
    fub_person_name TEXT,
    linear_label_id TEXT,
    linear_label_name TEXT,
    created_at TEXT DEFAULT {TS_DEFAULT}
);
CREATE INDEX IF NOT EXISTS idx_linear_sync_person_labels_fub ON linear_sync_person_labels(fub_person_id);

CREATE TABLE IF NOT EXISTS linear_sync_team_config (
    id SERIAL PRIMARY KEY,
    team_key TEXT UNIQUE NOT NULL,
    team_id TEXT NOT NULL,
    team_name TEXT,
    process_group TEXT,
    default_state_id TEXT,
    completed_state_id TEXT,
    created_at TEXT DEFAULT {TS_DEFAULT}
);

CREATE TABLE IF NOT EXISTS linear_sync_sync_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT {TS_DEFAULT}
);

CREATE TABLE IF NOT EXISTS linear_sync_sync_log (
    id SERIAL PRIMARY KEY,
    timestamp TEXT DEFAULT {TS_DEFAULT},
    direction TEXT NOT NULL,
    action TEXT NOT NULL,
    linear_issue_id TEXT,
    fub_task_id INTEGER,
    fub_person_id INTEGER,
    fub_deal_id INTEGER,
    details TEXT,
    status TEXT DEFAULT 'success'
);
CREATE INDEX IF NOT EXISTS idx_linear_sync_sync_log_time ON linear_sync_sync_log(timestamp);

CREATE TABLE IF NOT EXISTS linear_sync_project_instances (
    id SERIAL PRIMARY KEY,
    linear_project_id TEXT UNIQUE NOT NULL,
    linear_project_name TEXT NOT NULL,
    fub_person_id INTEGER NOT NULL,
    fub_person_name TEXT,
    phase TEXT NOT NULL,
    property_address TEXT,
    linear_team_id TEXT NOT NULL,
    person_label_id TEXT,
    status TEXT DEFAULT 'active',
    issue_count INTEGER DEFAULT 0,
    completed_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT {TS_DEFAULT},
    updated_at TEXT DEFAULT {TS_DEFAULT}
);
CREATE INDEX IF NOT EXISTS idx_linear_sync_project_instances_person ON linear_sync_project_instances(fub_person_id);
CREATE INDEX IF NOT EXISTS idx_linear_sync_project_instances_phase ON linear_sync_project_instances(phase);

CREATE TABLE IF NOT EXISTS linear_sync_project_milestones (
    id SERIAL PRIMARY KEY,
    linear_milestone_id TEXT UNIQUE NOT NULL,
    linear_project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    sort_order REAL DEFAULT 0,
    created_at TEXT DEFAULT {TS_DEFAULT}
);
CREATE INDEX IF NOT EXISTS idx_linear_sync_project_milestones_project ON linear_sync_project_milestones(linear_project_id);
"""


def create_schemas(pg_conn, do_task: bool, do_linear: bool):
    if do_task:
        print("Creating task_sync_* tables...")
        pg_conn.executescript(TASK_SYNC_SCHEMA)
    if do_linear:
        print("Creating linear_sync_* tables...")
        pg_conn.executescript(LINEAR_SYNC_SCHEMA)
    pg_conn.commit()


def _copy_table(src_conn, pg_conn, src_table: str, pg_table: str, columns: list[str], conflict_col: str = None):
    """Copy rows from SQLite src_table -> PG pg_table. Returns row count."""
    cols_csv = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    rows = src_conn.execute(f"SELECT {cols_csv} FROM {src_table}").fetchall()

    if conflict_col:
        update_cols = [c for c in columns if c != conflict_col]
        update_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
        sql = (
            f"INSERT INTO {pg_table} ({cols_csv}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_col}) DO UPDATE SET {update_clause}"
        )
    else:
        sql = f"INSERT INTO {pg_table} ({cols_csv}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

    for r in rows:
        pg_conn.execute(sql, tuple(r))
    return len(rows)


def copy_task_sync(pg_conn):
    if not TASK_SYNC_DB.exists():
        print(f"  task_sync.db not found at {TASK_SYNC_DB}; skipping data copy.")
        return
    print(f"Copying from {TASK_SYNC_DB}...")
    src = sqlite3.connect(str(TASK_SYNC_DB))
    src.row_factory = sqlite3.Row
    try:
        n = _copy_table(src, pg_conn, "sync_state", "task_sync_sync_state",
                        ["key", "value", "updated_at"], conflict_col="key")
        print(f"  sync_state: {n} rows")

        n = _copy_table(src, pg_conn, "deal_cache", "task_sync_deal_cache",
                        ["id", "person_id", "pipeline_id", "stage_id", "stage_name",
                         "deal_name", "deal_value", "property_address", "property_city",
                         "property_state", "property_zip", "person_name", "person_email",
                         "person_phone", "todoist_project_id", "todoist_section_id",
                         "fetched_at", "updated_at"],
                        conflict_col="id")
        print(f"  deal_cache: {n} rows")

        n = _copy_table(src, pg_conn, "task_map", "task_sync_task_map",
                        ["todoist_task_id", "fub_task_id", "fub_person_id", "fub_deal_id",
                         "todoist_project_id", "todoist_section_id", "origin", "sync_status",
                         "last_synced_at", "todoist_updated_at", "fub_updated_at",
                         "created_at", "updated_at"])
        print(f"  task_map: {n} rows")

        n = _copy_table(src, pg_conn, "todoist_projects", "task_sync_todoist_projects",
                        ["todoist_project_id", "project_name", "fub_pipeline_id",
                         "fub_stage_id", "project_type", "created_at"],
                        conflict_col="todoist_project_id")
        print(f"  todoist_projects: {n} rows")

        # sync_log intentionally skipped (57K bulky audit rows; restart fresh)
        sync_log_count = src.execute("SELECT COUNT(*) FROM sync_log").fetchone()[0]
        print(f"  sync_log: {sync_log_count} rows (SKIPPED, audit trail restarts fresh)")

        pg_conn.commit()
    finally:
        src.close()


def copy_linear_sync(pg_conn):
    if not LINEAR_SYNC_DB.exists():
        print(f"  linear_sync.db not found at {LINEAR_SYNC_DB}; skipping data copy.")
        return
    print(f"Copying from {LINEAR_SYNC_DB}...")
    src = sqlite3.connect(str(LINEAR_SYNC_DB))
    src.row_factory = sqlite3.Row
    try:
        # All linear_sync tables are empty on PRD as of 2026-05-11; copy
        # anyway for robustness in case DEV has data or a future re-run picks
        # up new state.
        n = _copy_table(src, pg_conn, "sync_state", "linear_sync_sync_state",
                        ["key", "value", "updated_at"], conflict_col="key")
        print(f"  sync_state: {n} rows")

        n = _copy_table(src, pg_conn, "issue_map", "linear_sync_issue_map",
                        ["linear_issue_id", "linear_identifier", "fub_task_id", "fub_person_id",
                         "fub_deal_id", "linear_team_id", "linear_project_id", "person_label_id",
                         "origin", "sync_status", "last_synced_at", "linear_updated_at",
                         "fub_updated_at", "created_at", "updated_at"])
        print(f"  issue_map: {n} rows")

        n = _copy_table(src, pg_conn, "person_labels", "linear_sync_person_labels",
                        ["fub_person_id", "fub_person_name", "linear_label_id",
                         "linear_label_name", "created_at"],
                        conflict_col="fub_person_id")
        print(f"  person_labels: {n} rows")

        n = _copy_table(src, pg_conn, "team_config", "linear_sync_team_config",
                        ["team_key", "team_id", "team_name", "process_group",
                         "default_state_id", "completed_state_id", "created_at"],
                        conflict_col="team_key")
        print(f"  team_config: {n} rows")

        n = _copy_table(src, pg_conn, "deal_cache", "linear_sync_deal_cache",
                        ["id", "person_id", "pipeline_id", "stage_id", "stage_name",
                         "deal_name", "deal_value", "property_address", "property_city",
                         "close_date", "fetched_at", "updated_at"],
                        conflict_col="id")
        print(f"  deal_cache: {n} rows")

        n = _copy_table(src, pg_conn, "linear_cache", "linear_sync_linear_cache",
                        ["id", "identifier", "title", "description", "priority",
                         "state_id", "state_name", "state_type", "team_id", "team_name",
                         "project_id", "project_name", "due_date", "completed_at",
                         "created_at", "updated_at", "label_ids", "label_names", "fetched_at"],
                        conflict_col="id")
        print(f"  linear_cache: {n} rows")

        n = _copy_table(src, pg_conn, "project_instances", "linear_sync_project_instances",
                        ["linear_project_id", "linear_project_name", "fub_person_id",
                         "fub_person_name", "phase", "property_address", "linear_team_id",
                         "person_label_id", "status", "issue_count", "completed_count",
                         "created_at", "updated_at"],
                        conflict_col="linear_project_id")
        print(f"  project_instances: {n} rows")

        n = _copy_table(src, pg_conn, "project_milestones", "linear_sync_project_milestones",
                        ["linear_milestone_id", "linear_project_id", "name", "sort_order",
                         "created_at"],
                        conflict_col="linear_milestone_id")
        print(f"  project_milestones: {n} rows")

        sync_log_count = src.execute("SELECT COUNT(*) FROM sync_log").fetchone()[0]
        print(f"  sync_log: {sync_log_count} rows (SKIPPED, audit trail restarts fresh)")

        pg_conn.commit()
    finally:
        src.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-only", action="store_true", help="Only migrate task_sync")
    parser.add_argument("--linear-only", action="store_true", help="Only migrate linear_sync")
    parser.add_argument("--schema-only", action="store_true", help="Create tables, skip data copy")
    args = parser.parse_args()

    do_task = not args.linear_only
    do_linear = not args.task_only

    from src.core.pg_adapter import get_db
    pg_conn = get_db()

    create_schemas(pg_conn, do_task, do_linear)

    if not args.schema_only:
        if do_task:
            copy_task_sync(pg_conn)
        if do_linear:
            copy_linear_sync(pg_conn)

    pg_conn.close()
    print("\nMigration complete.")


if __name__ == "__main__":
    main()
