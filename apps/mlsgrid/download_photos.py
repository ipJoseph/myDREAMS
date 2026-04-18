"""
Download primary photos for Canopy MLS (MLS Grid) listings.

Downloads the primary photo for each listing that has a photo URL
but no local file yet. Uses concurrent downloads for speed.

After downloading, updates photo_local_path in the database so the
API can serve photos locally instead of relying on expiring CDN URLs.

Usage:
    python3 -m apps.mlsgrid.download_photos
    python3 -m apps.mlsgrid.download_photos --max 100
    python3 -m apps.mlsgrid.download_photos --workers 10
    python3 -m apps.mlsgrid.download_photos --status ALL
    python3 -m apps.mlsgrid.download_photos --update-db-only  # set paths for already-downloaded files
"""

import argparse
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


def download_photo(mls_number: str, url: str, dest_dir: Path) -> dict:
    """
    Download a single photo.

    Returns dict with status info.
    """
    # Determine file extension from URL path (ignore query params)
    parsed = urlparse(url)
    path_lower = parsed.path.lower()
    if path_lower.endswith('.png'):
        ext = '.png'
    elif path_lower.endswith('.webp'):
        ext = '.webp'
    else:
        ext = '.jpg'

    filename = f"{mls_number}{ext}"
    filepath = dest_dir / filename

    # Skip if already downloaded
    if filepath.exists() and filepath.stat().st_size > 0:
        return {
            'mls': mls_number,
            'status': 'skipped',
            'size': filepath.stat().st_size,
            'path': str(filepath),
        }

    try:
        resp = requests.get(url, timeout=30, stream=True)
        resp.raise_for_status()

        # Check content type
        content_type = resp.headers.get('Content-Type', '')
        if 'image' not in content_type and content_type:
            return {'mls': mls_number, 'status': 'error', 'error': f'Not an image: {content_type}'}

        # Write to file
        with open(filepath, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        size = filepath.stat().st_size
        if size == 0:
            filepath.unlink()
            return {'mls': mls_number, 'status': 'error', 'error': 'Empty file'}

        return {'mls': mls_number, 'status': 'downloaded', 'size': size, 'path': str(filepath)}

    except requests.RequestException as e:
        # Clean up partial file
        if filepath.exists():
            filepath.unlink()
        return {'mls': mls_number, 'status': 'error', 'error': str(e)}


def batch_update_photo_paths(db_path: Path, updates: list):
    """Batch update photo_local_path for downloaded photos."""
    if not updates:
        return
    from src.core.pg_adapter import get_db
    conn = get_db(str(db_path))
    conn.executemany(
        "UPDATE listings SET photo_local_path = ? WHERE mls_number = ?",
        updates
    )
    conn.commit()
    conn.close()


def update_db_only(photos_dir: Path, db_path: Path):
    """Set photo_local_path for files already downloaded but not recorded in DB."""
    from src.core.pg_adapter import get_db
    conn = get_db(str(db_path))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT mls_number FROM listings WHERE mls_source = ? AND photo_local_path IS NULL",
        [MLS_SOURCE]
    ).fetchall()

    updates = []
    for row in rows:
        mls = row['mls_number']
        for ext in ('.jpg', '.jpeg', '.png', '.webp'):
            filepath = photos_dir / f"{mls}{ext}"
            if filepath.exists() and filepath.stat().st_size > 0:
                updates.append((str(filepath), mls))
                break

    if updates:
        conn.executemany(
            "UPDATE listings SET photo_local_path = ? WHERE mls_number = ?",
            updates
        )
        conn.commit()

    conn.close()
    print(f"Updated photo_local_path for {len(updates)} listings.")


def main():
    parser = argparse.ArgumentParser(description="Download primary photos for Canopy MLS listings")
    parser.add_argument('--max', type=int, help='Maximum photos to download')
    parser.add_argument('--workers', type=int, default=10, help='Parallel download workers (default: 10)')
    parser.add_argument('--status', default='ACTIVE', help='Filter by listing status (default: ACTIVE, use ALL for all)')
    parser.add_argument('--update-db-only', action='store_true', help='Only update DB paths for already-downloaded files')
    args = parser.parse_args()

    load_env()
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

    if args.update_db_only:
        update_db_only(PHOTOS_DIR, DB_PATH)
        return

    # Get listings needing photos
    from src.core.pg_adapter import get_db
    conn = get_db(str(DB_PATH))

    if args.status == 'ALL':
        query = """
            SELECT mls_number, primary_photo FROM listings
            WHERE mls_source = ? AND primary_photo IS NOT NULL
            ORDER BY status, list_price DESC
        """
        rows = conn.execute(query, [MLS_SOURCE]).fetchall()
    else:
        query = """
            SELECT mls_number, primary_photo FROM listings
            WHERE mls_source = ? AND primary_photo IS NOT NULL AND UPPER(status) = UPPER(?)
            ORDER BY list_price DESC
        """
        rows = conn.execute(query, [MLS_SOURCE, args.status]).fetchall()
    conn.close()

    if args.max:
        rows = rows[:args.max]

    # Check what's already downloaded
    existing = {f.stem for f in PHOTOS_DIR.iterdir() if f.is_file() and f.stat().st_size > 0}
    to_download = [(r['mls_number'], r['primary_photo']) for r in rows if r['mls_number'] not in existing]

    print(f"MLS Source:           {MLS_SOURCE}")
    print(f"Status filter:        {args.status}")
    print(f"Listings with photos: {len(rows)}")
    print(f"Already downloaded:   {len(existing)}")
    print(f"To download:          {len(to_download)}")
    print(f"Workers:              {args.workers}")
    print()

    if not to_download:
        print("Nothing to download.")
        # Still update DB paths for any previously downloaded files
        update_db_only(PHOTOS_DIR, DB_PATH)
        return

    start = time.time()
    downloaded = 0
    errors = 0
    skipped = 0
    total_bytes = 0
    db_updates = []

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(download_photo, mls, url, PHOTOS_DIR): mls
            for mls, url in to_download
        }

        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()

            if result['status'] == 'downloaded':
                downloaded += 1
                total_bytes += result.get('size', 0)
                db_updates.append((result['path'], result['mls']))
            elif result['status'] == 'skipped':
                skipped += 1
                if result.get('path'):
                    db_updates.append((result['path'], result['mls']))
            elif result['status'] == 'error':
                errors += 1
                if errors <= 10:
                    print(f"  Error {result['mls']}: {result['error']}")

            # Batch DB update every 500 photos
            if len(db_updates) >= 500:
                batch_update_photo_paths(DB_PATH, db_updates)
                db_updates = []

            if i % 200 == 0 or i == len(to_download):
                elapsed = time.time() - start
                rate = i / elapsed if elapsed > 0 else 0
                mb = total_bytes / (1024 * 1024)
                print(f"  Progress: {i}/{len(to_download)} ({rate:.0f}/sec, {mb:.1f} MB)")

    # Final DB update
    if db_updates:
        batch_update_photo_paths(DB_PATH, db_updates)

    elapsed = time.time() - start
    mb = total_bytes / (1024 * 1024)

    print()
    print("=" * 55)
    print("CANOPY MLS PHOTO DOWNLOAD SUMMARY")
    print("=" * 55)
    print(f"  Downloaded:  {downloaded:,}")
    print(f"  Errors:      {errors:,}")
    print(f"  Skipped:     {skipped + len(existing):,}")
    print(f"  Total size:  {mb:.1f} MB")
    print(f"  Duration:    {elapsed:.1f}s")
    if downloaded:
        print(f"  Avg size:    {total_bytes / downloaded / 1024:.0f} KB")
        print(f"  Rate:        {downloaded / elapsed:.1f} photos/sec")
    print("=" * 55)


if __name__ == '__main__':
    sys.exit(main() or 0)
