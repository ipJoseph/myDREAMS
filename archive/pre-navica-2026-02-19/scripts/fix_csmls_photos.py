#!/usr/bin/env python3
"""
Fix MLS Photo Linking

Links orphaned MLS photos to listings and populates the photos/photo_count fields.
Works across ALL listing sources (CSMLS, PropStream, etc.)

Issues fixed:
1. Photos exist on disk but primary_photo not set on listing
2. primary_photo set but photos JSON array empty
3. photo_count is 0 even when photos exist

Usage:
    python scripts/fix_csmls_photos.py           # Run fixes
    python scripts/fix_csmls_photos.py --dry-run # Preview without changes
    python scripts/fix_csmls_photos.py --stats   # Show stats only
    python scripts/fix_csmls_photos.py --source CSMLS  # Fix specific source only
"""

import argparse
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'
PHOTOS_DIR = PROJECT_ROOT / 'data' / 'photos'


def get_photo_files():
    """Get all MLS numbers that have photo files on disk."""
    photo_mls = {}
    if not PHOTOS_DIR.exists():
        return photo_mls

    for f in PHOTOS_DIR.glob('*.jpg'):
        # Extract MLS number from filename (format: MLSNUM.jpg)
        mls_num = f.stem
        if mls_num.isdigit() or mls_num.replace('-', '').isdigit():
            photo_mls[mls_num] = f'/photos/{f.name}'

    return photo_mls


def show_stats(conn, source=None):
    """Show current photo coverage stats."""
    source_filter = f"WHERE mls_source = '{source}'" if source else ""
    source_label = source or "All Sources"

    print(f"\n=== Photo Stats ({source_label}) ===\n")

    # Overall stats
    stats_row = conn.execute(f"""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN primary_photo IS NOT NULL AND primary_photo != '' THEN 1 END) as has_primary,
            COUNT(CASE WHEN photos IS NOT NULL AND photos != '[]' AND photos != '' THEN 1 END) as has_json,
            COUNT(CASE WHEN photo_count > 0 THEN 1 END) as has_count
        FROM listings
        {source_filter}
    """).fetchone()

    total = stats_row['total']
    has_primary = stats_row['has_primary']
    has_json = stats_row['has_json']
    has_count = stats_row['has_count']

    print(f"Total listings:           {total:,}")
    print(f"Has primary_photo:        {has_primary:,} ({has_primary/total*100:.1f}%)" if total else "Has primary_photo:        0")
    print(f"Has photos JSON:          {has_json:,} ({has_json/total*100:.1f}%)" if total else "Has photos JSON:          0")
    print(f"Has photo_count > 0:      {has_count:,} ({has_count/total*100:.1f}%)" if total else "Has photo_count > 0:      0")

    # Photo files on disk
    photo_files = get_photo_files()
    print(f"\nPhoto files on disk:      {len(photo_files):,}")

    # Find orphans - check against ALL listings with MLS numbers
    listings_with_photos = set()
    for row in conn.execute("SELECT mls_number FROM listings WHERE primary_photo IS NOT NULL AND primary_photo != '' AND mls_number IS NOT NULL"):
        listings_with_photos.add(row['mls_number'])

    all_mls_nums = set()
    for row in conn.execute("SELECT mls_number FROM listings WHERE mls_number IS NOT NULL AND mls_number != ''"):
        all_mls_nums.add(row['mls_number'])

    photos_matching_listings = set(photo_files.keys()) & all_mls_nums
    orphan_photos = set(photo_files.keys()) - all_mls_nums
    unlinked_photos = photos_matching_listings - listings_with_photos

    print(f"\nPhoto files matching listings: {len(photos_matching_listings):,}")
    print(f"Orphan photos (no listing):    {len(orphan_photos):,}")
    print(f"Unlinked (can be linked):      {len(unlinked_photos):,}")

    # By source breakdown
    print("\n--- By Source ---")
    for row in conn.execute("""
        SELECT
            mls_source,
            COUNT(*) as total,
            COUNT(CASE WHEN primary_photo IS NOT NULL AND primary_photo != '' THEN 1 END) as has_photo
        FROM listings
        GROUP BY mls_source
    """):
        pct = row['has_photo'] / row['total'] * 100 if row['total'] else 0
        print(f"  {row['mls_source'] or 'Unknown':12} {row['has_photo']:,}/{row['total']:,} ({pct:.1f}%)")

    return {
        'total': total,
        'has_primary': has_primary,
        'photo_files': len(photo_files),
        'unlinked': len(unlinked_photos),
        'orphan': len(orphan_photos),
    }


def fix_photos(conn, dry_run=False, source=None):
    """Fix photo linking issues."""
    photo_files = get_photo_files()
    now = datetime.now().isoformat()

    stats = {
        'linked_primary': 0,
        'updated_json': 0,
        'updated_count': 0,
        'errors': 0,
    }

    source_label = source or "All Sources"
    print(f"\n=== Fixing Photos ({source_label}) ===\n")

    # Get listings with MLS numbers
    if source:
        listings = conn.execute("""
            SELECT id, mls_number, mls_source, primary_photo, photos, photo_count, photo_source
            FROM listings
            WHERE mls_source = ? AND mls_number IS NOT NULL AND mls_number != ''
        """, [source]).fetchall()
    else:
        listings = conn.execute("""
            SELECT id, mls_number, mls_source, primary_photo, photos, photo_count, photo_source
            FROM listings
            WHERE mls_number IS NOT NULL AND mls_number != ''
        """).fetchall()

    for listing in listings:
        mls_num = listing['mls_number']
        listing_id = listing['id']
        current_primary = listing['primary_photo']
        current_json = listing['photos']
        current_count = listing['photo_count'] or 0

        # Check if photo file exists for this MLS number
        photo_path = photo_files.get(mls_num)

        if not photo_path:
            continue

        updates = []
        values = []

        # Fix 1: Link primary_photo if missing
        if not current_primary:
            updates.append("primary_photo = ?")
            values.append(photo_path)
            updates.append("photo_source = ?")
            values.append('mls')
            updates.append("photo_review_status = ?")
            values.append('verified')
            stats['linked_primary'] += 1

        # Fix 2: Populate photos JSON if empty
        if not current_json or current_json == '[]' or current_json == '':
            # Use existing primary_photo or new one
            photo_url = current_primary or photo_path
            photos_array = [photo_url]
            updates.append("photos = ?")
            values.append(json.dumps(photos_array))
            stats['updated_json'] += 1

        # Fix 3: Set photo_count if 0
        if current_count == 0:
            updates.append("photo_count = ?")
            values.append(1)  # We have at least 1 photo
            stats['updated_count'] += 1

        if updates:
            updates.append("updated_at = ?")
            values.append(now)
            values.append(listing_id)

            if not dry_run:
                try:
                    sql = f"UPDATE listings SET {', '.join(updates)} WHERE id = ?"
                    conn.execute(sql, values)
                except Exception as e:
                    print(f"  Error updating {mls_num}: {e}")
                    stats['errors'] += 1

    if not dry_run:
        conn.commit()

    return stats


def main():
    parser = argparse.ArgumentParser(description="Fix MLS photo linking issues")
    parser.add_argument('--dry-run', action='store_true', help="Preview without database changes")
    parser.add_argument('--stats', action='store_true', help="Show stats only, no fixes")
    parser.add_argument('--source', type=str, help="Filter by source (CSMLS, PropStream)")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Show before stats
    before_stats = show_stats(conn, source=args.source)

    if args.stats:
        conn.close()
        return 0

    # Run fixes
    if args.dry_run:
        print("\n*** DRY RUN - No changes will be made ***")

    fix_stats = fix_photos(conn, dry_run=args.dry_run, source=args.source)

    print("\n=== Fix Results ===\n")
    print(f"Linked primary_photo:  {fix_stats['linked_primary']:,}")
    print(f"Updated photos JSON:   {fix_stats['updated_json']:,}")
    print(f"Updated photo_count:   {fix_stats['updated_count']:,}")
    print(f"Errors:                {fix_stats['errors']:,}")

    # Show after stats
    if not args.dry_run:
        print("\n")
        show_stats(conn, source=args.source)

    conn.close()
    return 0


if __name__ == '__main__':
    exit(main())
