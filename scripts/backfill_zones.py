#!/usr/bin/env python3
"""
One-time migration: add `zone` column to listings table and populate
it based on county/state using the ZONE_MAP from field_mapper.

Usage:
    python3 scripts/backfill_zones.py          # dry-run (report only)
    python3 scripts/backfill_zones.py --apply   # apply changes
"""

import argparse
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from apps.navica.field_mapper import compute_zone, normalize_county

DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'

ZONE_NAMES = {
    1: 'West',
    2: 'Central',
    3: 'East WNC',
    4: 'Rest of NC',
    5: 'Outside NC',
}


def main():
    parser = argparse.ArgumentParser(description='Backfill zone column on listings table')
    parser.add_argument('--apply', action='store_true', help='Apply changes (default is dry-run)')
    parser.add_argument('--db', type=str, default=str(DB_PATH), help='Path to database')
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    # Step 1: Ensure column exists
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(listings)").fetchall()}
    if 'zone' not in existing_cols:
        print("Adding 'zone' column to listings table...")
        if args.apply:
            conn.execute("ALTER TABLE listings ADD COLUMN zone INTEGER")
            conn.commit()
            print("  Column added.")
        else:
            print("  [dry-run] Would add column.")
    else:
        print("'zone' column already exists.")

    # Step 2: Create index
    if args.apply:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_listings_zone ON listings(zone)")
        conn.commit()
        print("Index idx_listings_zone ensured.")

    # Step 3: Backfill all rows
    rows = conn.execute("SELECT id, county, state FROM listings").fetchall()
    print(f"\nProcessing {len(rows)} listings...")

    zone_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    updates = []

    for row in rows:
        zone = compute_zone(normalize_county(row['county']), row['state'])
        zone_counts[zone] += 1
        updates.append((zone, row['id']))

    # Report
    print("\nZone distribution:")
    for z in sorted(zone_counts):
        print(f"  Zone {z} ({ZONE_NAMES[z]}): {zone_counts[z]:,}")
    total_wnc = zone_counts[1] + zone_counts[2]
    print(f"  Zones 1+2 (default WNC): {total_wnc:,}")
    print(f"  Total: {sum(zone_counts.values()):,}")

    if args.apply:
        print("\nApplying updates...")
        conn.executemany("UPDATE listings SET zone = ? WHERE id = ?", updates)
        conn.commit()
        print(f"  Updated {len(updates):,} listings.")

        # Verify
        verify = conn.execute(
            "SELECT zone, COUNT(*) as cnt FROM listings GROUP BY zone ORDER BY zone"
        ).fetchall()
        print("\nVerification (from DB):")
        for row in verify:
            z = row['zone'] or 0
            name = ZONE_NAMES.get(z, 'NULL')
            print(f"  Zone {z} ({name}): {row['cnt']:,}")
    else:
        print("\n[dry-run] No changes applied. Use --apply to write.")

    conn.close()


if __name__ == '__main__':
    main()
