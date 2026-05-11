#!/usr/bin/env python3
"""
Ensure all required schema columns exist in the Postgres database.

Run this after any database sync from PRD to DEV, or on cron, to guarantee
columns added via ALTER TABLE are present. Uses Postgres-native ADD COLUMN
IF NOT EXISTS syntax (atomic, idempotent).

Usage:
    python3 scripts/ensure_schema.py              # connects via DATABASE_URL
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

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

# Email detail columns added to contact_communications
CONTACT_COMMUNICATIONS_COLUMNS = {
    'email_from': 'TEXT',
    'email_to': 'TEXT',
    'subject': 'TEXT',
    'snippet': 'TEXT',
    'email_type': 'TEXT',
    'fub_email_id': 'TEXT',
}


def ensure_columns(conn, table, columns):
    """Add missing columns. Returns count of columns added."""
    existing = {
        row[0] for row in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
            (table,)
        ).fetchall()
    }
    added = 0
    for col, ctype in columns.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {ctype}")
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
    parser = argparse.ArgumentParser(description='Ensure Postgres schema is complete')
    parser.add_argument('--db', type=str, help='(Ignored; routes through pg_adapter via DATABASE_URL)')
    args = parser.parse_args()

    from src.core.pg_adapter import get_db
    conn = get_db()

    total = 0
    total += ensure_columns(conn, 'listings', LISTINGS_COLUMNS)
    total += ensure_columns(conn, 'showings', SHOWINGS_COLUMNS)
    total += ensure_columns(conn, 'showing_properties', SHOWING_PROPERTIES_COLUMNS)
    total += ensure_columns(conn, 'property_packages', PROPERTY_PACKAGES_COLUMNS)
    total += ensure_columns(conn, 'contact_communications', CONTACT_COMMUNICATIONS_COLUMNS)
    ensure_indexes(conn)

    conn.commit()
    conn.close()

    if total:
        print(f"Schema updated: {total} columns added")
    else:
        print("Schema OK: all columns present")


if __name__ == '__main__':
    main()
