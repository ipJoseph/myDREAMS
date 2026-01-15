#!/usr/bin/env python3
"""
Database migration script for Property Extension v3.

Adds new columns to the properties table if they don't exist.
Safe to run multiple times.
"""

import sqlite3
import os
from pathlib import Path

# Get database path
DB_PATH = os.getenv('DREAMS_DB_PATH', str(Path(__file__).parent.parent / 'data' / 'dreams.db'))

# New columns to add
NEW_COLUMNS = [
    ('redfin_id', 'TEXT'),
    ('redfin_url', 'TEXT'),
    ('realtor_id', 'TEXT'),
    ('hoa_fee', 'INTEGER'),
    ('tax_assessed_value', 'INTEGER'),
    ('tax_annual_amount', 'INTEGER'),
    ('zestimate', 'INTEGER'),
    ('rent_zestimate', 'INTEGER'),
    ('page_views', 'INTEGER'),
    ('favorites_count', 'INTEGER'),
    ('heating', 'TEXT'),
    ('cooling', 'TEXT'),
    ('garage', 'TEXT'),
    ('sewer', 'TEXT'),
    ('roof', 'TEXT'),
    ('stories', 'INTEGER'),
    ('subdivision', 'TEXT'),
    ('latitude', 'REAL'),
    ('longitude', 'REAL'),
    ('school_elementary_rating', 'INTEGER'),
    ('school_middle_rating', 'INTEGER'),
    ('school_high_rating', 'INTEGER'),
    ('added_for', 'TEXT'),
    ('added_by', 'TEXT'),
    ('notion_page_id', 'TEXT'),
    ('notion_synced_at', 'TEXT'),
    ('sync_status', 'TEXT DEFAULT "pending"'),
    ('sync_error', 'TEXT'),
]

# New indexes
NEW_INDEXES = [
    ('idx_properties_zillow_id', 'properties(zillow_id)'),
    ('idx_properties_redfin_id', 'properties(redfin_id)'),
    ('idx_properties_mls', 'properties(mls_number)'),
    ('idx_properties_sync_status', 'properties(sync_status)'),
]


def get_existing_columns(conn: sqlite3.Connection) -> set:
    """Get list of existing columns in properties table."""
    cursor = conn.execute("PRAGMA table_info(properties)")
    return {row[1] for row in cursor.fetchall()}


def migrate():
    """Run the migration."""
    print(f"Migrating database: {DB_PATH}")

    if not os.path.exists(DB_PATH):
        print("Database doesn't exist yet. It will be created on first use.")
        return

    conn = sqlite3.connect(DB_PATH)

    try:
        existing = get_existing_columns(conn)
        print(f"Existing columns: {len(existing)}")

        # Add new columns
        added = 0
        for col_name, col_type in NEW_COLUMNS:
            if col_name not in existing:
                try:
                    conn.execute(f"ALTER TABLE properties ADD COLUMN {col_name} {col_type}")
                    print(f"  Added column: {col_name}")
                    added += 1
                except sqlite3.OperationalError as e:
                    print(f"  Skip {col_name}: {e}")

        # Add new indexes
        for idx_name, idx_def in NEW_INDEXES:
            try:
                conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_def}")
                print(f"  Created index: {idx_name}")
            except sqlite3.OperationalError as e:
                print(f"  Skip index {idx_name}: {e}")

        conn.commit()
        print(f"\nMigration complete! Added {added} new columns.")

    finally:
        conn.close()


if __name__ == '__main__':
    migrate()
