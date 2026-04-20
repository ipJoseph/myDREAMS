#!/usr/bin/env python3
"""
Download full photo galleries for Canopy MLS listings in WNC Zone 1 & 2.

Uses the MLS Grid replication pattern: paginated $expand=Media queries
(same approach as incremental sync, zero extra per-listing API calls).
The API returns fresh CDN URLs inline; we download them in parallel.

Rate controls:
  - API requests: uses mlsgrid_throttle (3s between requests, 3000/hr cap)
  - CDN downloads: parallel workers (CDN is separate from API rate limits)
  - 429 handling: respects Retry-After header
  - Daily cap: stops if approaching 20k API requests/day

Storage estimate: ~14 GB for ~30k gallery photos at ~481 KB avg.

Usage:
    python3 scripts/download_gallery_photos.py
    python3 scripts/download_gallery_photos.py --dry-run
    python3 scripts/download_gallery_photos.py --max-pages 50
    python3 scripts/download_gallery_photos.py --workers 5
    python3 scripts/download_gallery_photos.py --counties Buncombe Henderson
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.mlsgrid_throttle import get_throttle

DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'
PHOTOS_DIR = PROJECT_ROOT / 'data' / 'photos' / 'mlsgrid'
MLS_SOURCE = 'CanopyMLS'

# WNC Zone 1 (core service area)
ZONE_1 = [
    'Buncombe', 'Henderson', 'Haywood', 'Transylvania', 'Madison',
]

# WNC Zone 2 (extended service area)
ZONE_2 = [
    'McDowell', 'Rutherford', 'Burke', 'Yancey', 'Jackson', 'Polk',
    'Caldwell', 'Mitchell', 'Avery', 'Watauga', 'Swain', 'Graham',
    'Macon', 'Clay', 'Cherokee',
]

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


def get_target_mls_numbers(counties: list) -> dict:
    """Get MLS numbers of active Canopy listings in target counties.
    Returns dict of mls_number -> photo_count."""
    conn = sqlite3.connect(str(DB_PATH))
    placeholders = ','.join(['?' for _ in counties])
    rows = conn.execute(f"""
        SELECT mls_number, COALESCE(photo_count, 0)
        FROM listings
        WHERE mls_source = ? AND UPPER(status) = 'ACTIVE'
        AND county IN ({placeholders})
    """, [MLS_SOURCE] + counties).fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}


def scan_existing_photos(mls_numbers: set) -> dict:
    """Scan disk to find which listings already have gallery photos.
    Returns dict of mls_number -> set of existing filenames."""
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    all_files = set(os.listdir(PHOTOS_DIR))

    existing = {}
    for mls in mls_numbers:
        files = set()
        for f in all_files:
            if f.startswith(mls) and (f.endswith('.jpg') or f.endswith('.jpeg')
                                      or f.endswith('.png') or f.endswith('.webp')):
                files.add(f)
        if files:
            existing[mls] = files
    return existing


def download_single_photo(mls: str, url: str, filename: str) -> dict:
    """Download one photo from CDN. Returns status dict."""
    filepath = PHOTOS_DIR / filename
    if filepath.exists() and filepath.stat().st_size > 0:
        return {'mls': mls, 'file': filename, 'status': 'exists'}

    try:
        resp = requests.get(url, timeout=30, stream=True)
        resp.raise_for_status()

        with open(filepath, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        if filepath.stat().st_size > 0:
            return {'mls': mls, 'file': filename, 'status': 'downloaded'}
        else:
            filepath.unlink(missing_ok=True)
            return {'mls': mls, 'file': filename, 'status': 'empty'}

    except Exception as e:
        return {'mls': mls, 'file': filename, 'status': 'error', 'error': str(e)}


def update_photos_column(updates: list):
    """Update the photos column with local URLs so templates render correctly."""
    if not updates:
        return
    conn = sqlite3.connect(str(DB_PATH), timeout=60)
    conn.execute('PRAGMA busy_timeout=60000')
    for mls, local_files in updates:
        local_urls = [f"/api/public/photos/mlsgrid/{Path(p).name}" for p in local_files]
        primary_path = str(local_files[0]) if local_files else None
        conn.execute(
            "UPDATE listings SET photos = ?, photo_local_path = COALESCE(photo_local_path, ?) "
            "WHERE mls_source = ? AND mls_number = ?",
            [json.dumps(local_urls), primary_path, MLS_SOURCE, mls]
        )
    conn.commit()
    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Download full photo galleries for Canopy MLS listings in WNC"
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without downloading')
    parser.add_argument('--max-pages', type=int, default=500,
                        help='Max API pages to fetch (default: 500)')
    parser.add_argument('--workers', type=int, default=8,
                        help='Parallel CDN download workers (default: 8)')
    parser.add_argument('--counties', nargs='+', default=None,
                        help='Specific counties (default: Zone 1+2)')
    parser.add_argument('--zone', type=int, choices=[1, 2], default=None,
                        help='Download only Zone 1 or Zone 2 (default: both)')
    args = parser.parse_args()

    load_env()

    token = os.environ.get('MLSGRID_TOKEN')
    if not token:
        logger.error("MLSGRID_TOKEN not set in environment")
        return 1

    # Determine target counties
    if args.counties:
        counties = args.counties
    elif args.zone == 1:
        counties = ZONE_1
    elif args.zone == 2:
        counties = ZONE_2
    else:
        counties = ZONE_1 + ZONE_2

    logger.info(f"Target counties: {', '.join(counties)}")

    # Step 1: Find target listings
    targets = get_target_mls_numbers(counties)
    logger.info(f"Active Canopy listings in target area: {len(targets)}")

    # Step 2: Scan existing photos on disk
    existing = scan_existing_photos(set(targets.keys()))
    needs_gallery = {}
    for mls, expected_count in targets.items():
        on_disk = existing.get(mls, set())
        # Count gallery files (excluding primary)
        gallery_on_disk = sum(1 for f in on_disk if '_' in f.rsplit('.', 1)[0])
        gallery_expected = max(0, expected_count - 1)
        if gallery_expected > gallery_on_disk:
            needs_gallery[mls] = {
                'expected': expected_count,
                'has_primary': any(
                    f.startswith(mls) and '_' not in f.rsplit('.', 1)[0]
                    for f in on_disk
                ),
                'gallery_on_disk': gallery_on_disk,
            }

    logger.info(f"Listings needing gallery photos: {len(needs_gallery)}")
    total_needed = sum(
        max(0, v['expected'] - v['gallery_on_disk'] - (1 if v['has_primary'] else 0))
        for v in needs_gallery.values()
    )
    logger.info(f"Estimated photos to download: {total_needed}")
    logger.info(f"Estimated storage: {total_needed * 481 / 1024 / 1024:.1f} GB")

    if not needs_gallery:
        logger.info("All gallery photos already downloaded. Nothing to do.")
        return 0

    if args.dry_run:
        logger.info("DRY RUN: would fetch API pages and download gallery photos")
        # Show top 10 listings needing most photos
        by_need = sorted(needs_gallery.items(),
                         key=lambda x: x[1]['expected'] - x[1]['gallery_on_disk'],
                         reverse=True)
        for mls, info in by_need[:10]:
            need = info['expected'] - info['gallery_on_disk'] - (1 if info['has_primary'] else 0)
            logger.info(f"  {mls}: need {need} of {info['expected']} photos")
        return 0

    # Step 3: Fetch from API using replication pattern
    throttle = get_throttle()
    session = requests.Session()
    session.headers.update({
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip,deflate',
    })

    base_url = (
        "https://api.mlsgrid.com/v2/Property"
        "?$filter=OriginatingSystemName eq 'carolina' and MlgCanView eq true"
        " and StandardStatus eq 'Active'"
        "&$expand=Media"
        "&$top=500"
    )

    stats = {
        'api_pages': 0,
        'listings_processed': 0,
        'photos_downloaded': 0,
        'photos_skipped': 0,
        'photos_error': 0,
        'db_updates': 0,
    }
    db_update_batch = []
    start_time = time.time()
    url = base_url

    while url and stats['api_pages'] < args.max_pages:
        stats['api_pages'] += 1

        # Rate limit via throttle
        throttle.wait()

        try:
            resp = session.get(url, timeout=60)
            throttle.record()

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

            # Collect download tasks for this page
            download_tasks = []

            for prop in records:
                mls = prop.get('ListingId', '')
                if mls not in needs_gallery:
                    continue

                media = prop.get('Media', [])
                if not media:
                    continue

                # Extract all photo URLs in order
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
                    continue

                photos.sort(key=lambda x: x[0])

                # Build download list: primary + gallery
                for idx, (_, photo_url) in enumerate(photos):
                    parsed = urlparse(photo_url)
                    path_lower = parsed.path.lower()
                    ext = '.png' if path_lower.endswith('.png') else \
                          '.webp' if path_lower.endswith('.webp') else '.jpg'

                    if idx == 0:
                        filename = f"{mls}{ext}"
                    else:
                        filename = f"{mls}_{idx:02d}{ext}"

                    # Skip if already on disk
                    filepath = PHOTOS_DIR / filename
                    if filepath.exists() and filepath.stat().st_size > 0:
                        stats['photos_skipped'] += 1
                        continue

                    download_tasks.append((mls, photo_url, filename))

                stats['listings_processed'] += 1

            # Download in parallel (CDN, not API, so parallelism is safe)
            if download_tasks:
                local_paths_by_mls = {}
                with ThreadPoolExecutor(max_workers=args.workers) as executor:
                    futures = {
                        executor.submit(download_single_photo, mls, purl, fname): (mls, fname)
                        for mls, purl, fname in download_tasks
                    }
                    for future in as_completed(futures):
                        result = future.result()
                        if result['status'] == 'downloaded':
                            stats['photos_downloaded'] += 1
                            mls = result['mls']
                            if mls not in local_paths_by_mls:
                                local_paths_by_mls[mls] = []
                            local_paths_by_mls[mls].append(
                                str(PHOTOS_DIR / result['file'])
                            )
                        elif result['status'] == 'error':
                            stats['photos_error'] += 1

                # Collect DB updates
                for mls, paths in local_paths_by_mls.items():
                    # Get ALL files on disk for this listing (including pre-existing)
                    all_files = sorted([
                        str(PHOTOS_DIR / f)
                        for f in os.listdir(PHOTOS_DIR)
                        if f.startswith(mls) and (
                            f.endswith('.jpg') or f.endswith('.jpeg')
                            or f.endswith('.png') or f.endswith('.webp')
                        )
                    ])
                    db_update_batch.append((mls, all_files))
                    needs_gallery.pop(mls, None)

                # Batch DB update every 200 listings
                if len(db_update_batch) >= 200:
                    update_photos_column(db_update_batch)
                    stats['db_updates'] += len(db_update_batch)
                    db_update_batch = []

            # Progress
            elapsed = time.time() - start_time
            logger.info(
                f"Page {stats['api_pages']}: {len(records)} records, "
                f"{stats['photos_downloaded']} downloaded, "
                f"{len(needs_gallery)} listings remaining "
                f"({elapsed:.0f}s elapsed)"
            )

            # All done?
            if not needs_gallery:
                logger.info("All target gallery photos downloaded!")
                break

            # Follow pagination
            url = data.get('@odata.nextLink')

        except requests.exceptions.RequestException as e:
            logger.error(f"Request error on page {stats['api_pages']}: {e}")
            stats['photos_error'] += 1
            time.sleep(5)
            continue

    # Final DB update
    if db_update_batch:
        update_photos_column(db_update_batch)
        stats['db_updates'] += len(db_update_batch)

    elapsed = time.time() - start_time

    print()
    print("=" * 60)
    print("GALLERY PHOTO DOWNLOAD SUMMARY")
    print("=" * 60)
    print(f"  Counties:           {', '.join(counties)}")
    print(f"  API pages fetched:  {stats['api_pages']}")
    print(f"  Listings processed: {stats['listings_processed']}")
    print(f"  Photos downloaded:  {stats['photos_downloaded']}")
    print(f"  Photos skipped:     {stats['photos_skipped']} (already on disk)")
    print(f"  Photos errored:     {stats['photos_error']}")
    print(f"  DB records updated: {stats['db_updates']}")
    print(f"  Listings remaining: {len(needs_gallery)}")
    print(f"  Duration:           {elapsed:.0f}s ({elapsed/60:.1f}m)")
    print("=" * 60)

    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
