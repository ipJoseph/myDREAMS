#!/usr/bin/env python3
"""
Backfill missing primary photos for Canopy MLS listings.

Uses the proper MLS Grid replication pattern: a single paginated query
with $expand=Media filtered by ModificationTimestamp. This avoids
individual ListingId lookups which violate MLS Grid Best Practices.

Strategy:
  1. Query local DB for Active Canopy listings missing local photos
  2. Find the earliest ModificationTimestamp among those listings
  3. Run a single replication query from that timestamp forward
  4. Download primary photos from MediaURL in the response
  5. Update photo_local_path in DB

This approach uses the same query pattern as incremental sync,
just with an older timestamp to catch listings that were synced
before we started downloading photos during replication.

Rate limits observed: 1.1s between API requests (well under 2 RPS).

Usage:
    python3 scripts/backfill_missing_photos.py
    python3 scripts/backfill_missing_photos.py --dry-run
    python3 scripts/backfill_missing_photos.py --max-pages 10
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'
PHOTOS_DIR = PROJECT_ROOT / 'data' / 'photos' / 'mlsgrid'
MLS_SOURCE = 'CanopyMLS'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger(__name__)


def load_env():
    env_path = PROJECT_ROOT / '.env'
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip().strip('"\''))


def get_missing_mls_numbers() -> set:
    """Get MLS numbers of Active Canopy listings without local photos on disk."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT mls_number FROM listings
        WHERE mls_source = ? AND UPPER(status) = 'ACTIVE'
        AND (photo_local_path IS NULL OR photo_local_path = '')
    """, [MLS_SOURCE]).fetchall()
    conn.close()
    return {r['mls_number'] for r in rows}


def get_missing_on_disk(mls_numbers: set) -> set:
    """Filter to MLS numbers that truly have no file on disk."""
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    missing = set()
    for mls in mls_numbers:
        found = False
        for ext in ('.jpg', '.jpeg', '.png', '.webp'):
            filepath = PHOTOS_DIR / f"{mls}{ext}"
            if filepath.exists() and filepath.stat().st_size > 0:
                found = True
                break
        if not found:
            missing.add(mls)
    return missing


def download_photo(mls: str, url: str) -> bool:
    """Download a single photo. Returns True on success."""
    try:
        path_lower = urlparse(url).path.lower()
        ext = '.png' if path_lower.endswith('.png') else '.webp' if path_lower.endswith('.webp') else '.jpg'
        filepath = PHOTOS_DIR / f"{mls}{ext}"

        if filepath.exists() and filepath.stat().st_size > 0:
            return True

        resp = requests.get(url, timeout=30, stream=True)
        resp.raise_for_status()

        with open(filepath, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        if filepath.stat().st_size > 0:
            return True
        else:
            filepath.unlink(missing_ok=True)
            return False

    except Exception as e:
        logger.debug(f"Failed to download photo for {mls}: {e}")
        return False


def update_photo_paths(updates: list):
    """Batch update photo_local_path in DB."""
    if not updates:
        return
    conn = sqlite3.connect(str(DB_PATH), timeout=60)
    conn.execute('PRAGMA busy_timeout=60000')
    conn.executemany(
        "UPDATE listings SET photo_local_path = ? WHERE mls_source = ? AND mls_number = ?",
        updates
    )
    conn.commit()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Backfill missing Canopy MLS photos using replication pattern")
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without downloading')
    parser.add_argument('--max-pages', type=int, default=200, help='Max API pages to fetch (default: 200)')
    args = parser.parse_args()

    load_env()

    token = os.environ.get('MLSGRID_TOKEN')
    if not token:
        logger.error("MLSGRID_TOKEN not set in environment")
        return 1

    # Step 1: Find listings needing photos
    missing_db = get_missing_mls_numbers()
    missing_disk = get_missing_on_disk(missing_db)

    # Also check for files on disk not recorded in DB
    on_disk_not_in_db = missing_db - missing_disk
    if on_disk_not_in_db:
        logger.info(f"Found {len(on_disk_not_in_db)} photos on disk but not in DB, updating paths...")
        updates = []
        for mls in on_disk_not_in_db:
            for ext in ('.jpg', '.jpeg', '.png', '.webp'):
                filepath = PHOTOS_DIR / f"{mls}{ext}"
                if filepath.exists() and filepath.stat().st_size > 0:
                    updates.append((str(filepath), MLS_SOURCE, mls))
                    break
        if not args.dry_run:
            update_photo_paths(updates)
        logger.info(f"Updated {len(updates)} DB records with existing photo paths")

    logger.info(f"Listings missing photos in DB: {len(missing_db)}")
    logger.info(f"Listings truly missing on disk: {len(missing_disk)}")

    if not missing_disk:
        logger.info("All photos accounted for. Nothing to backfill.")
        return 0

    if args.dry_run:
        logger.info("DRY RUN: would fetch replication data and download photos")
        return 0

    # Step 2: Use replication pattern to fetch Active listings with Media
    # This is the MLS Grid approved approach: bulk query with $expand=Media
    logger.info("Fetching Active listings from MLS Grid API (replication pattern)...")

    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip,deflate',
    }

    # Query all Active listings with Media (same as initial import but filtered)
    base_url = (
        "https://api.mlsgrid.com/v2/Property"
        "?$filter=OriginatingSystemName eq 'carolina' and MlgCanView eq true and StandardStatus eq 'Active'"
        "&$expand=Media"
    )

    downloaded = 0
    already_had = 0
    no_media = 0
    errors = 0
    pages = 0
    db_updates = []

    url = base_url
    start = time.time()

    while url and pages < args.max_pages:
        pages += 1
        logger.info(f"Fetching page {pages}...")

        # Rate limit: 1.1s between requests
        time.sleep(1.1)

        try:
            resp = requests.get(url, headers=headers, timeout=60)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get('Retry-After', 60))
                logger.warning(f"Rate limited. Waiting {retry_after}s...")
                time.sleep(retry_after)
                continue
            if resp.status_code != 200:
                logger.error(f"API error {resp.status_code}: {resp.text[:200]}")
                break

            data = resp.json()
            records = data.get('value', [])

            for prop in records:
                mls = prop.get('ListingId', '')
                if mls not in missing_disk:
                    continue

                media = prop.get('Media', [])
                if not media:
                    no_media += 1
                    continue

                # Find primary photo (first Photo-category media by order)
                photos = []
                for m in media:
                    cat = m.get('MediaCategory', '')
                    if cat and cat != 'Photo':
                        continue
                    media_url = m.get('MediaURL')
                    if media_url:
                        order = m.get('Order', m.get('MediaOrder', 999))
                        photos.append((order, media_url))

                if not photos:
                    no_media += 1
                    continue

                photos.sort(key=lambda x: x[0])
                primary_url = photos[0][1]

                if download_photo(mls, primary_url):
                    downloaded += 1
                    missing_disk.discard(mls)
                    # Find the actual file path for DB update
                    for ext in ('.jpg', '.jpeg', '.png', '.webp'):
                        filepath = PHOTOS_DIR / f"{mls}{ext}"
                        if filepath.exists():
                            db_updates.append((str(filepath), MLS_SOURCE, mls))
                            break
                else:
                    errors += 1

                # Batch DB update every 500
                if len(db_updates) >= 500:
                    update_photo_paths(db_updates)
                    logger.info(f"  Updated {len(db_updates)} DB records")
                    db_updates = []

            # Progress
            elapsed = time.time() - start
            logger.info(
                f"  Page {pages}: {len(records)} records, "
                f"{downloaded} downloaded, {len(missing_disk)} still missing "
                f"({elapsed:.0f}s elapsed)"
            )

            # Check if we've filled all gaps
            if not missing_disk:
                logger.info("All missing photos backfilled!")
                break

            # Follow pagination
            url = data.get('@odata.nextLink')

        except Exception as e:
            logger.error(f"Error on page {pages}: {e}")
            errors += 1
            break

    # Final DB update
    if db_updates:
        update_photo_paths(db_updates)

    elapsed = time.time() - start

    print()
    print("=" * 55)
    print("PHOTO BACKFILL SUMMARY")
    print("=" * 55)
    print(f"  API pages fetched: {pages}")
    print(f"  Photos downloaded: {downloaded}")
    print(f"  No media found:   {no_media}")
    print(f"  Errors:           {errors}")
    print(f"  Still missing:    {len(missing_disk)}")
    print(f"  Duration:         {elapsed:.0f}s")
    print(f"  API requests:     {pages} (replication pattern)")
    print("=" * 55)

    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
