#!/usr/bin/env python3
"""
Deduplicate listings that share the same parcel_id.

Strategy:
- For parcels with multiple listings, merge into one authoritative record
- Priority: Keep PropStream record (has coords), add MLS data from CSMLS
- Fields to merge from CSMLS: mls_number, mls_source, agent info, photos if better

Usage:
    python scripts/deduplicate_listings.py --dry-run   # Preview changes
    python scripts/deduplicate_listings.py             # Execute merge
"""

import argparse
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "dreams.db"

# Fields to copy from CSMLS to PropStream if PropStream is missing them
MERGE_FIELDS = [
    'mls_number',
    'mls_source',
    'listing_agent_name',
    'listing_agent_phone',
    'listing_agent_email',
    'listing_office_name',
    'listing_office_id',
    'status',
    'days_on_market',
]

# Photo fields - only copy if CSMLS has photo and PropStream doesn't
PHOTO_FIELDS = [
    'primary_photo',
    'photo_source',
    'photo_confidence',
    'photo_count',
]


def get_duplicate_parcels(conn):
    """Find parcels with multiple listings."""
    return conn.execute("""
        SELECT parcel_id, COUNT(*) as cnt
        FROM listings
        WHERE parcel_id IS NOT NULL
        GROUP BY parcel_id
        HAVING cnt > 1
        ORDER BY cnt DESC
    """).fetchall()


def get_listings_for_parcel(conn, parcel_id):
    """Get all listings for a parcel."""
    return conn.execute("""
        SELECT * FROM listings WHERE parcel_id = ?
        ORDER BY
            CASE source
                WHEN 'propstream_11county' THEN 1  -- PropStream first
                WHEN 'CSMLS' THEN 2
                ELSE 3
            END,
            id ASC
    """, [parcel_id]).fetchall()


def merge_listings(conn, keeper, duplicates, dry_run=False):
    """Merge duplicate listings into keeper."""
    keeper_id = keeper['id']
    updates = {}

    for dup in duplicates:
        # Merge standard fields
        for field in MERGE_FIELDS:
            if keeper[field] is None and dup[field] is not None:
                updates[field] = dup[field]

        # Merge photo fields only if keeper has no photo
        if keeper['primary_photo'] is None and dup['primary_photo'] is not None:
            for field in PHOTO_FIELDS:
                if dup[field] is not None:
                    updates[field] = dup[field]

    if updates:
        if not dry_run:
            set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
            conn.execute(
                f"UPDATE listings SET {set_clause} WHERE id = ?",
                list(updates.values()) + [keeper_id]
            )

    # Delete duplicates
    dup_ids = [d['id'] for d in duplicates]
    if not dry_run:
        conn.execute(
            f"DELETE FROM listings WHERE id IN ({','.join('?' * len(dup_ids))})",
            dup_ids
        )

    return updates, dup_ids


def main():
    parser = argparse.ArgumentParser(description="Deduplicate listings")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get stats before
    before_count = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    print(f"\n📊 Before: {before_count:,} listings")

    # Find duplicates
    duplicate_parcels = get_duplicate_parcels(conn)
    total_duplicates = sum(row['cnt'] - 1 for row in duplicate_parcels)

    print(f"🔍 Found {len(duplicate_parcels):,} parcels with duplicates")
    print(f"   {total_duplicates:,} duplicate listings to remove")

    if args.dry_run:
        print("\n🔄 DRY RUN - No changes will be made\n")

    # Process each duplicate parcel
    merged_count = 0
    deleted_count = 0
    fields_merged = {}

    for parcel_row in duplicate_parcels:
        parcel_id = parcel_row['parcel_id']
        listings = get_listings_for_parcel(conn, parcel_id)

        # First listing is keeper (PropStream preferred)
        keeper = dict(listings[0])
        duplicates = [dict(l) for l in listings[1:]]

        updates, deleted_ids = merge_listings(conn, keeper, duplicates, args.dry_run)

        if updates:
            merged_count += 1
            for field in updates:
                fields_merged[field] = fields_merged.get(field, 0) + 1

        deleted_count += len(deleted_ids)

    if not args.dry_run:
        conn.commit()

    # Get stats after
    after_count = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]

    print(f"\n📈 Results:")
    print(f"   Listings merged with new data: {merged_count:,}")
    print(f"   Duplicate listings removed: {deleted_count:,}")
    print(f"   After: {after_count:,} listings")

    if fields_merged:
        print(f"\n📋 Fields enriched from CSMLS:")
        for field, count in sorted(fields_merged.items(), key=lambda x: -x[1]):
            print(f"   {field}: {count:,} records")

    if args.dry_run:
        print(f"\n⚠️  Run without --dry-run to apply changes")
    else:
        print(f"\n✅ Deduplication complete!")

    conn.close()


if __name__ == "__main__":
    main()
