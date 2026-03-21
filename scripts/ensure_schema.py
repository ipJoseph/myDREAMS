#!/usr/bin/env python3
"""
Ensure all required schema columns exist in the database.

Run this after any database sync from PRD to DEV, or on app startup,
to guarantee columns added via ALTER TABLE are present.

Usage:
    python3 scripts/ensure_schema.py              # uses default DB path
    python3 scripts/ensure_schema.py --db /path   # specify DB path
"""

import argparse
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_DB = PROJECT_ROOT / 'data' / 'dreams.db'

# Columns that may be missing after a DB sync from PRD
LISTINGS_COLUMNS = {
    'zone': 'INTEGER',
    'photos_local': 'TEXT',
    'photos_refreshed_at': 'TEXT',
}

SHOWINGS_COLUMNS = {
    'package_id': 'TEXT',
    'name': 'TEXT',
    'scheduled_date': 'TEXT',
    'scheduled_time': 'TEXT',
    'route_optimized': 'INTEGER',
    'route_data': 'TEXT',
    'total_drive_time': 'INTEGER',
    'total_distance': 'REAL',
    'updated_at': 'TEXT',
}

SHOWING_PROPERTIES_COLUMNS = {
    'showing_id': 'TEXT',
    'property_id': 'TEXT',
    'stop_order': 'INTEGER',
    'time_at_property': 'INTEGER',
}

PROPERTY_PACKAGES_COLUMNS = {
    'viewed_at': 'TEXT',
}


def ensure_columns(conn, table, columns):
    """Add missing columns to a table. Returns count of columns added."""
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    added = 0
    for col, ctype in columns.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ctype}")
            print(f"  Added {table}.{col} ({ctype})")
            added += 1
    return added


def ensure_indexes(conn):
    """Create indexes if they don't exist."""
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_listings_zone ON listings(zone)",
    ]
    for idx in indexes:
        conn.execute(idx)


def main():
    parser = argparse.ArgumentParser(description='Ensure database schema is complete')
    parser.add_argument('--db', type=str, default=str(DEFAULT_DB), help='Database path')
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)

    total = 0
    total += ensure_columns(conn, 'listings', LISTINGS_COLUMNS)
    total += ensure_columns(conn, 'showings', SHOWINGS_COLUMNS)
    total += ensure_columns(conn, 'showing_properties', SHOWING_PROPERTIES_COLUMNS)
    total += ensure_columns(conn, 'property_packages', PROPERTY_PACKAGES_COLUMNS)
    ensure_indexes(conn)

    conn.commit()
    conn.close()

    if total:
        print(f"Schema updated: {total} columns added")
    else:
        print("Schema OK: all columns present")


if __name__ == '__main__':
    main()
