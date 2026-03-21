"""
Download gallery photos for Canopy MLS (MLS Grid) listings.

Downloads all photos (not just the primary) for each listing.
Primary photo: {mls_number}.jpg (already handled by download_photos.py)
Gallery photos: {mls_number}_01.jpg, {mls_number}_02.jpg, etc.

After downloading, updates the `photos` column in the database with
local API paths so the public site can serve them without CDN URLs.

Usage:
    python3 -m apps.mlsgrid.download_gallery
    python3 -m apps.mlsgrid.download_gallery --max 100
    python3 -m apps.mlsgrid.download_gallery --workers 10
    python3 -m apps.mlsgrid.download_gallery --status ALL
    python3 -m apps.mlsgrid.download_gallery --update-db-only
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

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'
PHOTOS_DIR = PROJECT_ROOT / 'data' / 'photos' / 'mlsgrid'

MLS_SOURCE = 'CanopyMLS'
LOCAL_URL_PREFIX = '/api/public/photos/mlsgrid'


def load_env():
    """Load environment variables from .env file."""
    env_path = PROJECT_ROOT / '.env'
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip().strip('"\''))


def download_single(url: str, filepath: Path) -> dict:
    """Download a single photo file. Returns status dict."""
    if filepath.exists() and filepath.stat().st_size > 0:
        return {'status': 'skipped', 'size': filepath.stat().st_size}

    try:
        resp = requests.get(url, timeout=30, stream=True)
        resp.raise_for_status()

        content_type = resp.headers.get('Content-Type', '')
        if 'image' not in content_type and content_type:
            return {'status': 'error', 'error': f'Not an image: {content_type}'}

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
    """Determine file extension from URL."""
    path_lower = urlparse(url).path.lower()
    if path_lower.endswith('.png'):
        return '.png'
    elif path_lower.endswith('.webp'):
        return '.webp'
    return '.jpg'


def download_listing_gallery(mls_number: str, photos_json: str) -> dict:
    """
    Download all gallery photos for a single listing.

    Returns dict with mls_number, local_paths (list), stats.
    """
    try:
        urls = json.loads(photos_json)
    except (json.JSONDecodeError, TypeError):
        return {'mls': mls_number, 'downloaded': 0, 'errors': 0, 'skipped': 0, 'local_paths': []}

    if not urls or not isinstance(urls, list):
        return {'mls': mls_number, 'downloaded': 0, 'errors': 0, 'skipped': 0, 'local_paths': []}

    downloaded = 0
    errors = 0
    skipped = 0
    total_bytes = 0
    local_paths = []

    for i, url in enumerate(urls):
        if not url or not isinstance(url, str):
            continue

        # Already a local path (previously converted)
        if url.startswith('/api/'):
            local_paths.append(url)
            skipped += 1
            continue

        ext = get_ext_from_url(url)

        if i == 0:
            # Primary photo: {mls_number}.jpg
            filename = f"{mls_number}{ext}"
        else:
            # Gallery photos: {mls_number}_01.jpg, _02.jpg, etc.
            filename = f"{mls_number}_{i:02d}{ext}"

        filepath = PHOTOS_DIR / filename
        result = download_single(url, filepath)

        local_url = f"{LOCAL_URL_PREFIX}/{filename}"
        local_paths.append(local_url)

        if result['status'] == 'downloaded':
            downloaded += 1
            total_bytes += result.get('size', 0)
        elif result['status'] == 'skipped':
            skipped += 1
        elif result['status'] == 'error':
            errors += 1

    return {
        'mls': mls_number,
        'downloaded': downloaded,
        'errors': errors,
        'skipped': skipped,
        'bytes': total_bytes,
        'local_paths': local_paths,
    }


def update_db_only(photos_dir: Path, db_path: Path):
    """Rebuild photos column from files already on disk."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT mls_number, photos FROM listings WHERE mls_source = ? AND photos IS NOT NULL",
        [MLS_SOURCE]
    ).fetchall()

    updates = []
    for row in rows:
        mls = row['mls_number']
        try:
            urls = json.loads(row['photos'])
        except (json.JSONDecodeError, TypeError):
            continue

        if not urls:
            continue

        # Check if already localized
        if urls[0].startswith('/api/'):
            continue

        local_paths = []
        all_exist = True
        for i, url in enumerate(urls):
            if not url:
                continue
            ext = get_ext_from_url(url) if not url.startswith('/api/') else ''
            if i == 0:
                filename = f"{mls}{ext or '.jpg'}"
            else:
                filename = f"{mls}_{i:02d}{ext or '.jpg'}"

            filepath = photos_dir / filename
            if filepath.exists() and filepath.stat().st_size > 0:
                local_paths.append(f"{LOCAL_URL_PREFIX}/{filename}")
            else:
                all_exist = False
                local_paths.append(url)  # Keep CDN URL for missing files

        if local_paths:
            updates.append((json.dumps(local_paths), mls))

    if updates:
        conn.executemany(
            "UPDATE listings SET photos = ? WHERE mls_number = ?",
            updates
        )
        conn.commit()

    conn.close()
    print(f"Updated photos column for {len(updates)} listings.")


def main():
    parser = argparse.ArgumentParser(description="Download gallery photos for Canopy MLS listings")
    parser.add_argument('--max', type=int, help='Maximum listings to process')
    parser.add_argument('--workers', type=int, default=5, help='Parallel listing workers (default: 5)')
    parser.add_argument('--status', default='ACTIVE', help='Filter by listing status (default: ACTIVE, use ALL for all)')
    parser.add_argument('--update-db-only', action='store_true', help='Only update DB paths for already-downloaded files')
    args = parser.parse_args()

    load_env()
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

    if args.update_db_only:
        update_db_only(PHOTOS_DIR, DB_PATH)
        return

    # Get listings with gallery photos
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    if args.status == 'ALL':
        query = """
            SELECT mls_number, photos FROM listings
            WHERE mls_source = ? AND photos IS NOT NULL
            ORDER BY status, list_price DESC
        """
        rows = conn.execute(query, [MLS_SOURCE]).fetchall()
    else:
        query = """
            SELECT mls_number, photos FROM listings
            WHERE mls_source = ? AND photos IS NOT NULL AND UPPER(status) = UPPER(?)
            ORDER BY list_price DESC
        """
        rows = conn.execute(query, [MLS_SOURCE, args.status]).fetchall()
    conn.close()

    # Filter to listings that still have CDN URLs
    to_process = []
    for row in rows:
        try:
            urls = json.loads(row['photos'])
            if urls and isinstance(urls, list) and any(
                isinstance(u, str) and 'mlsgrid.com' in u for u in urls
            ):
                to_process.append((row['mls_number'], row['photos']))
        except (json.JSONDecodeError, TypeError):
            continue

    if args.max:
        to_process = to_process[:args.max]

    total_photos = sum(
        len(json.loads(p)) for _, p in to_process
        if p
    )

    print(f"MLS Source:             {MLS_SOURCE}")
    print(f"Status filter:          {args.status}")
    print(f"Listings with galleries: {len(rows)}")
    print(f"Needing download:       {len(to_process)}")
    print(f"Total gallery photos:   {total_photos:,}")
    print(f"Workers:                {args.workers}")
    print()

    if not to_process:
        print("Nothing to download.")
        return

    start = time.time()
    total_downloaded = 0
    total_errors = 0
    total_skipped = 0
    total_bytes = 0
    db_updates = []

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(download_listing_gallery, mls, photos): mls
            for mls, photos in to_process
        }

        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            total_downloaded += result['downloaded']
            total_errors += result['errors']
            total_skipped += result['skipped']
            total_bytes += result.get('bytes', 0)

            # Queue DB update with local paths
            if result['local_paths']:
                db_updates.append((json.dumps(result['local_paths']), result['mls']))

            # Batch DB update every 200 listings
            if len(db_updates) >= 200:
                conn = sqlite3.connect(str(DB_PATH))
                conn.executemany(
                    "UPDATE listings SET photos = ? WHERE mls_number = ?",
                    db_updates
                )
                conn.commit()
                conn.close()
                db_updates = []

            if i % 100 == 0 or i == len(to_process):
                elapsed = time.time() - start
                rate = total_downloaded / elapsed if elapsed > 0 else 0
                mb = total_bytes / (1024 * 1024)
                print(f"  Listings: {i}/{len(to_process)} | Photos: {total_downloaded:,} downloaded, {total_skipped:,} skipped, {total_errors:,} errors ({rate:.0f} photos/sec, {mb:.1f} MB)")

    # Final DB update
    if db_updates:
        conn = sqlite3.connect(str(DB_PATH))
        conn.executemany(
            "UPDATE listings SET photos = ? WHERE mls_number = ?",
            db_updates
        )
        conn.commit()
        conn.close()

    elapsed = time.time() - start
    mb = total_bytes / (1024 * 1024)

    print()
    print("=" * 60)
    print("CANOPY MLS GALLERY PHOTO DOWNLOAD SUMMARY")
    print("=" * 60)
    print(f"  Listings processed: {len(to_process):,}")
    print(f"  Photos downloaded:  {total_downloaded:,}")
    print(f"  Photos skipped:     {total_skipped:,}")
    print(f"  Errors:             {total_errors:,}")
    print(f"  Total size:         {mb:.1f} MB")
    print(f"  Duration:           {elapsed:.1f}s")
    if total_downloaded:
        print(f"  Avg size:           {total_bytes / total_downloaded / 1024:.0f} KB")
        print(f"  Rate:               {total_downloaded / elapsed:.1f} photos/sec")
    print("=" * 60)


if __name__ == '__main__':
    sys.exit(main() or 0)
