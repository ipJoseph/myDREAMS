#!/usr/bin/env python3
"""
Migrate myDREAMS from SQLite to PostgreSQL.

Usage:
    # Set DATABASE_URL in .env first, then:
    python3 scripts/migrate_to_postgres.py

    # Or specify paths explicitly:
    DATABASE_URL=postgresql://dreams:pass@localhost/dreams \
    python3 scripts/migrate_to_postgres.py --sqlite data/dreams.db

This script:
1. Reads the SQLite schema
2. Converts it to PostgreSQL DDL
3. Creates tables in PostgreSQL
4. Copies all data from SQLite to PostgreSQL
5. Verifies row counts match

Safe to run multiple times (drops and recreates tables).
"""

import argparse
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)


def get_sqlite_tables(sqlite_conn) -> list:
    """Get all table names from SQLite."""
    cursor = sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [row[0] for row in cursor.fetchall()]


def get_sqlite_schema(sqlite_conn, table: str) -> str:
    """Get CREATE TABLE statement for a SQLite table."""
    cursor = sqlite_conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    row = cursor.fetchone()
    return row[0] if row else ""


def sqlite_to_pg_type(col_type: str) -> str:
    """Convert SQLite column type to PostgreSQL type."""
    t = col_type.upper().strip()
    if not t:
        return "TEXT"
    if "INT" in t:
        return "BIGINT" if "BIG" in t else "INTEGER"
    if "REAL" in t or "FLOAT" in t or "DOUBLE" in t:
        return "DOUBLE PRECISION"
    if "BLOB" in t:
        return "BYTEA"
    if "BOOL" in t:
        return "BOOLEAN"
    return "TEXT"


def convert_schema_to_pg(sqlite_sql: str, table_name: str) -> str:
    """Convert a SQLite CREATE TABLE statement to PostgreSQL."""
    if not sqlite_sql:
        return ""

    # Remove SQLite-specific AUTOINCREMENT (we use TEXT UUIDs anyway)
    sql = sqlite_sql.replace("AUTOINCREMENT", "")

    # Remove IF NOT EXISTS for clean migration (we drop first)
    sql = sql.replace("IF NOT EXISTS ", "")

    # Convert column type keywords
    sql = re.sub(r'\bINTEGER PRIMARY KEY\b', 'SERIAL PRIMARY KEY', sql)

    # Handle DEFAULT CURRENT_TIMESTAMP (works in both)
    # Handle BOOLEAN → keep as-is (PostgreSQL supports it)

    # Add IF NOT EXISTS back for safety
    sql = sql.replace(f"CREATE TABLE {table_name}", f"CREATE TABLE IF NOT EXISTS {table_name}")
    sql = sql.replace(f'CREATE TABLE "{table_name}"', f'CREATE TABLE IF NOT EXISTS "{table_name}"')

    return sql


def migrate_table_data(sqlite_conn, pg_conn, table: str, batch_size: int = 1000) -> int:
    """Copy all rows from a SQLite table to PostgreSQL."""
    # Get column names
    cursor = sqlite_conn.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]

    if not columns:
        return 0

    # Count rows
    row_count = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    if row_count == 0:
        return 0

    # Build INSERT statement
    col_list = ", ".join(f'"{c}"' for c in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    insert_sql = f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'

    # Batch copy
    pg_cursor = pg_conn.cursor()
    offset = 0
    inserted = 0

    while offset < row_count:
        rows = sqlite_conn.execute(
            f"SELECT * FROM {table} LIMIT {batch_size} OFFSET {offset}"
        ).fetchall()

        if not rows:
            break

        # Convert sqlite3.Row to tuple
        data = [tuple(row) for row in rows]

        try:
            pg_cursor.executemany(insert_sql, data)
            pg_conn.commit()
            inserted += len(data)
        except Exception as e:
            pg_conn.rollback()
            # Try one-by-one for the batch that failed
            for row_data in data:
                try:
                    pg_cursor.execute(insert_sql, row_data)
                    pg_conn.commit()
                    inserted += 1
                except Exception as row_err:
                    pg_conn.rollback()
                    # Skip problematic rows (log first few)
                    if inserted < 5:
                        print(f"    SKIP row in {table}: {str(row_err)[:100]}")

        offset += batch_size
        if offset % 10000 == 0 and row_count > 10000:
            print(f"    {offset}/{row_count}...")

    return inserted


def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite to PostgreSQL")
    parser.add_argument("--sqlite", default=str(PROJECT_ROOT / "data" / "dreams.db"),
                        help="Path to SQLite database")
    parser.add_argument("--drop", action="store_true", default=True,
                        help="Drop existing PostgreSQL tables before migration")
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set. Add it to .env or set it in the environment.")
        sys.exit(1)

    print(f"SQLite source: {args.sqlite}")
    print(f"PostgreSQL target: {database_url.split('@')[1] if '@' in database_url else database_url}")
    print()

    # Connect to both databases
    sqlite_conn = sqlite3.connect(args.sqlite)
    sqlite_conn.row_factory = sqlite3.Row
    pg_conn = psycopg2.connect(database_url)

    # Get all tables
    tables = get_sqlite_tables(sqlite_conn)
    print(f"Found {len(tables)} tables in SQLite")
    print()

    # Phase 1: Create schema
    print("=== Phase 1: Schema Migration ===")
    pg_cursor = pg_conn.cursor()

    if args.drop:
        # Drop all tables (in reverse order to handle foreign keys)
        for table in reversed(tables):
            pg_cursor.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
        pg_conn.commit()
        print(f"Dropped {len(tables)} existing tables")

    schema_ok = 0
    schema_fail = 0

    for table in tables:
        sqlite_schema = get_sqlite_schema(sqlite_conn, table)
        if not sqlite_schema:
            print(f"  SKIP {table} (no schema)")
            continue

        pg_schema = convert_schema_to_pg(sqlite_schema, table)
        try:
            pg_cursor.execute(pg_schema)
            pg_conn.commit()
            schema_ok += 1
        except Exception as e:
            pg_conn.rollback()
            err = str(e).strip()[:120]
            print(f"  FAIL {table}: {err}")
            # Try a simpler approach: create table with just TEXT columns
            try:
                columns = sqlite_conn.execute(f"PRAGMA table_info({table})").fetchall()
                cols_sql = ", ".join(
                    f'"{c[1]}" {sqlite_to_pg_type(c[2])}' +
                    (" PRIMARY KEY" if c[5] else "") +
                    (" NOT NULL" if c[3] else "") +
                    (f" DEFAULT {c[4]}" if c[4] is not None else "")
                    for c in columns
                )
                simple_sql = f'CREATE TABLE IF NOT EXISTS "{table}" ({cols_sql})'
                pg_cursor.execute(simple_sql)
                pg_conn.commit()
                schema_ok += 1
                print(f"  OK   {table} (simplified schema)")
            except Exception as e2:
                pg_conn.rollback()
                print(f"  FAIL {table} (simplified also failed): {str(e2)[:100]}")
                schema_fail += 1

    print(f"\nSchema: {schema_ok} OK, {schema_fail} failed")
    print()

    # Phase 2: Migrate data
    print("=== Phase 2: Data Migration ===")
    total_rows = 0
    start_time = time.time()

    for table in tables:
        sqlite_count = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if sqlite_count == 0:
            continue

        inserted = migrate_table_data(sqlite_conn, pg_conn, table)
        total_rows += inserted

        status = "OK" if inserted == sqlite_count else f"PARTIAL ({inserted}/{sqlite_count})"
        print(f"  {status:12s} {table}: {inserted:,} rows")

    elapsed = time.time() - start_time
    print(f"\nMigrated {total_rows:,} total rows in {elapsed:.1f}s")
    print()

    # Phase 3: Verify
    print("=== Phase 3: Verification ===")
    pg_cursor = pg_conn.cursor()
    mismatches = 0

    for table in tables:
        sqlite_count = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        try:
            pg_cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
            pg_count = pg_cursor.fetchone()[0]
        except Exception:
            pg_conn.rollback()
            pg_count = -1

        if sqlite_count != pg_count:
            print(f"  MISMATCH {table}: SQLite={sqlite_count}, PG={pg_count}")
            mismatches += 1

    if mismatches == 0:
        print(f"  ALL {len(tables)} tables match")
    else:
        print(f"\n  {mismatches} table(s) have mismatches")

    print()
    print("=== Migration Complete ===")
    print(f"Tables: {schema_ok}/{len(tables)}")
    print(f"Rows:   {total_rows:,}")
    print(f"Time:   {elapsed:.1f}s")
    if mismatches == 0:
        print("Status: READY for cutover")
    else:
        print("Status: REVIEW mismatches before cutover")

    sqlite_conn.close()
    pg_conn.close()


if __name__ == "__main__":
    main()
