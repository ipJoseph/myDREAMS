#!/usr/bin/env python3
"""
Bulk gallery photo downloader for Canopy MLS (MLS Grid).

Fetches fresh photo URLs from the MLS Grid API in small batches,
downloads all photos immediately (while tokens are valid), then
updates the database. This avoids the token expiration problem
that occurs when URLs are fetched once and downloaded later.

Usage:
    python3 scripts/bulk_gallery_download.py
    python3 scripts/bulk_gallery_download.py --workers 10
    python3 scripts/bulk_gallery_download.py --batch-size 100
    python3 scripts/bulk_gallery_download.py --max 500
"""

import argparse
import json
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

from apps.mlsgrid.client import MLSGridClient
from apps.navica.field_mapper import extract_photos

DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'
PHOTOS_DIR = PROJECT_ROOT / 'data' / 'photos' / 'mlsgrid'
LOCAL_URL_PREFIX = '/api/public/photos/mlsgrid'


def load_env():
    env_path = PROJECT_ROOT / '.env'
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip().strip('"\''))


def download_photo(url: str, filepath: Path) -> dict:
    """Download a single photo. Returns status dict."""
    if filepath.exists() and filepath.stat().st_size > 0:
        return {'status': 'skipped', 'size': filepath.stat().st_size}

    try:
        resp = requests.get(url, timeout=30, stream=True)
        resp.raise_for_status()

        with open(filepath, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        size = filepath.stat().st_size
        if size == 0:
            filepath.unlink()
            return {'status': 'error', 'error': 'Empty file'}

        return {'status': 'downloaded', 'size': size}

    except requests.RequestException as e:
        if filepath.exists():
            filepath.unlink()
        return {'status': 'error', 'error': str(e)}


def get_ext_from_url(url: str) -> str:
    path_lower = urlparse(url).path.lower()
    if path_lower.endswith('.png'):
        return '.png'
    elif path_lower.endswith('.webp'):
        return '.webp'
    return '.jpg'


def download_listing_photos(mls_number: str, photo_urls: list, photos_dir: Path, workers: int = 3) -> dict:
    """Download all photos for a single listing using fresh URLs."""
    downloaded = 0
    skipped = 0
    errors = 0
    total_bytes = 0
    local_paths = []

    download_tasks = []
    for i, url in enumerate(photo_urls):
        if not url:
            continue

        ext = get_ext_from_url(url)
        filename = f"{mls_number}{ext}" if i == 0 else f"{mls_number}_{i:02d}{ext}"
        filepath = photos_dir / filename
        local_url = f"{LOCAL_URL_PREFIX}/{filename}"

        local_paths.append(local_url)
        download_tasks.append((url, filepath))

    # Download with thread pool (within this listing)
    with ThreadPoolExecutor(max_workers=min(workers, len(download_tasks))) as executor:
        futures = {executor.submit(download_photo, url, fp): fp for url, fp in download_tasks}
        for future in as_completed(futures):
            result = future.result()
            if result['status'] == 'downloaded':
                downloaded += 1
                total_bytes += result.get('size', 0)
            elif result['status'] == 'skipped':
                skipped += 1
            else:
                errors += 1

    return {
        'mls': mls_number,
        'downloaded': downloaded,
        'skipped': skipped,
        'errors': errors,
        'bytes': total_bytes,
        'local_paths': local_paths,
    }


def get_listings_needing_gallery(db_path: Path, limit: int = None) -> list:
    """Get MLS numbers of active listings that still have CDN URLs in photos column."""
    conn = sqlite3.connect(str(db_path), timeout=120)
    conn.execute('PRAGMA busy_timeout=120000')
    conn.row_factory = sqlite3.Row

    query = """
        SELECT mls_number FROM listings
        WHERE mls_source = 'CanopyMLS'
        AND UPPER(status) = 'ACTIVE'
        AND photos IS NOT NULL
        AND photos LIKE '%mlsgrid.com%'
        ORDER BY list_price DESC
    """
    rows = conn.execute(query).fetchall()
    conn.close()

    mls_numbers = [r['mls_number'] for r in rows]
    if limit:
        mls_numbers = mls_numbers[:limit]
    return mls_numbers


def fetch_batch_from_api(client: MLSGridClient, mls_numbers: list) -> dict:
    """
    Fetch a batch of listings from MLS Grid API with fresh photo URLs.

    Returns dict mapping mls_number -> list of photo URLs.
    """
    # Build OData filter for specific listings
    # MLS Grid supports: ListingKey eq 'xxx' or ListingKey eq 'yyy'
    # But ListingId/MLS number filtering via $filter is more reliable
    filter_parts = [f"ListingId eq '{mls}'" for mls in mls_numbers]
    filter_str = " or ".join(filter_parts)

    params = {
        "$filter": f"OriginatingSystemName eq 'carolina' and ({filter_str})",
        "$expand": "Media",
    }

    try:
        data = client.get("/Property", params)
        results = data.get('value', [])
    except Exception as e:
        print(f"  API error: {e}")
        return {}

    # Extract photos per listing
    photo_map = {}
    for record in results:
        mls = record.get('ListingId', '')
        media = record.get('Media', [])
        _, photo_urls, _ = extract_photos(media)
        if photo_urls:
            photo_map[mls] = photo_urls

    return photo_map


def update_db_photos(db_path: Path, updates: list):
    """Batch update photos column with local paths. Retries on lock."""
    if not updates:
        return
    for attempt in range(5):
        try:
            conn = sqlite3.connect(str(db_path), timeout=120)
            conn.execute('PRAGMA busy_timeout=120000')
            conn.executemany(
                "UPDATE listings SET photos = ? WHERE mls_number = ?",
                updates
            )
            conn.commit()
            conn.close()
            return
        except sqlite3.OperationalError as e:
            if 'locked' in str(e) and attempt < 4:
                import time
                time.sleep(5)
            else:
                raise


def main():
    parser = argparse.ArgumentParser(description="Bulk gallery download with fresh API URLs")
    parser.add_argument('--workers', type=int, default=5, help='Download workers per listing (default: 5)')
    parser.add_argument('--batch-size', type=int, default=50, help='Listings per API batch (default: 50)')
    parser.add_argument('--max', type=int, help='Maximum listings to process')
    args = parser.parse_args()

    load_env()
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize MLS Grid client
    client = MLSGridClient.from_env()

    # Get listings needing gallery downloads
    mls_numbers = get_listings_needing_gallery(DB_PATH, limit=args.max)
    print(f"Listings needing gallery download: {len(mls_numbers):,}")
    print(f"Batch size: {args.batch_size}")
    print(f"Download workers per listing: {args.workers}")
    print()

    if not mls_numbers:
        print("Nothing to download.")
        return

    start = time.time()
    total_downloaded = 0
    total_skipped = 0
    total_errors = 0
    total_bytes = 0
    total_listings_done = 0
    api_requests = 0

    # Process in batches
    for batch_start in range(0, len(mls_numbers), args.batch_size):
        batch = mls_numbers[batch_start:batch_start + args.batch_size]
        batch_num = (batch_start // args.batch_size) + 1
        total_batches = (len(mls_numbers) + args.batch_size - 1) // args.batch_size

        # Fetch fresh URLs from API
        photo_map = fetch_batch_from_api(client, batch)
        api_requests += 1

        if not photo_map:
            print(f"  Batch {batch_num}/{total_batches}: No photos from API, skipping")
            continue

        # Download photos for each listing in this batch
        db_updates = []
        for mls in batch:
            if mls not in photo_map:
                continue

            result = download_listing_photos(
                mls, photo_map[mls], PHOTOS_DIR, workers=args.workers
            )
            total_downloaded += result['downloaded']
            total_skipped += result['skipped']
            total_errors += result['errors']
            total_bytes += result['bytes']
            total_listings_done += 1

            if result['local_paths']:
                db_updates.append((json.dumps(result['local_paths']), mls))

        # Update DB for this batch
        update_db_photos(DB_PATH, db_updates)

        elapsed = time.time() - start
        rate = total_downloaded / elapsed if elapsed > 0 else 0
        mb = total_bytes / (1024 * 1024)

        print(
            f"  Batch {batch_num}/{total_batches} | "
            f"Listings: {total_listings_done:,}/{len(mls_numbers):,} | "
            f"Photos: {total_downloaded:,} new, {total_skipped:,} exist, {total_errors:,} err | "
            f"{rate:.0f}/sec | {mb:.0f} MB | "
            f"API calls: {api_requests}"
        )

    elapsed = time.time() - start
    mb = total_bytes / (1024 * 1024)

    print()
    print("=" * 65)
    print("BULK GALLERY DOWNLOAD SUMMARY")
    print("=" * 65)
    print(f"  Listings processed: {total_listings_done:,}")
    print(f"  Photos downloaded:  {total_downloaded:,}")
    print(f"  Photos skipped:     {total_skipped:,}")
    print(f"  Errors:             {total_errors:,}")
    print(f"  Total size:         {mb:.1f} MB")
    print(f"  API requests:       {api_requests}")
    print(f"  Duration:           {elapsed:.0f}s ({elapsed/3600:.1f}h)")
    if total_downloaded:
        print(f"  Avg photo size:     {total_bytes / total_downloaded / 1024:.0f} KB")
        print(f"  Rate:               {total_downloaded / elapsed:.1f} photos/sec")
    print("=" * 65)


if __name__ == '__main__':
    main()
