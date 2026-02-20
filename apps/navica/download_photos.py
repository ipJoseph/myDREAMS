"""
Download primary photos for Navica MLS listings.

Downloads the primary photo for each listing that has a photo URL
but no local file yet. Uses concurrent downloads for speed.

Usage:
    python3 -m apps.navica.download_photos
    python3 -m apps.navica.download_photos --max 50  # limit count
    python3 -m apps.navica.download_photos --workers 10  # parallel downloads
"""

import argparse
import os
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'
PHOTOS_DIR = PROJECT_ROOT / 'data' / 'photos' / 'navica'


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
    # Determine file extension from URL
    ext = '.jpg'
    if '.png' in url.lower():
        ext = '.png'
    elif '.webp' in url.lower():
        ext = '.webp'

    filename = f"{mls_number}{ext}"
    filepath = dest_dir / filename

    # Skip if already downloaded
    if filepath.exists() and filepath.stat().st_size > 0:
        return {'mls': mls_number, 'status': 'skipped', 'size': filepath.stat().st_size}

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
        return {'mls': mls_number, 'status': 'downloaded', 'size': size, 'path': str(filepath)}

    except requests.RequestException as e:
        return {'mls': mls_number, 'status': 'error', 'error': str(e)}


def update_db_photo_path(db_path: Path, mls_number: str, local_path: str):
    """Update listing with local photo path."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE listings SET photo_local_path = ? WHERE mls_number = ?",
        [local_path, mls_number]
    )
    conn.commit()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Download primary photos for Navica listings")
    parser.add_argument('--max', type=int, help='Maximum photos to download')
    parser.add_argument('--workers', type=int, default=5, help='Parallel download workers (default: 5)')
    parser.add_argument('--status', default='ACTIVE', help='Filter by listing status (default: ACTIVE, use ALL for all)')
    args = parser.parse_args()

    load_env()
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

    # Get listings needing photos
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    if args.status == 'ALL':
        query = """
            SELECT mls_number, primary_photo FROM listings
            WHERE mls_source = 'NavicaMLS' AND primary_photo IS NOT NULL
            ORDER BY status, list_price DESC
        """
        rows = conn.execute(query).fetchall()
    else:
        query = """
            SELECT mls_number, primary_photo FROM listings
            WHERE mls_source = 'NavicaMLS' AND primary_photo IS NOT NULL AND status = ?
            ORDER BY list_price DESC
        """
        rows = conn.execute(query, [args.status]).fetchall()
    conn.close()

    if args.max:
        rows = rows[:args.max]

    # Check what's already downloaded
    existing = {f.stem for f in PHOTOS_DIR.iterdir() if f.is_file() and f.stat().st_size > 0}
    to_download = [(r['mls_number'], r['primary_photo']) for r in rows if r['mls_number'] not in existing]

    print(f"Listings with photos: {len(rows)}")
    print(f"Already downloaded:   {len(existing)}")
    print(f"To download:          {len(to_download)}")
    print(f"Workers:              {args.workers}")
    print()

    if not to_download:
        print("Nothing to download.")
        return

    start = time.time()
    downloaded = 0
    errors = 0
    total_bytes = 0

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
            elif result['status'] == 'error':
                errors += 1
                if errors <= 10:
                    print(f"  Error {result['mls']}: {result['error']}")

            if i % 100 == 0 or i == len(to_download):
                elapsed = time.time() - start
                rate = i / elapsed if elapsed > 0 else 0
                mb = total_bytes / (1024 * 1024)
                print(f"  Progress: {i}/{len(to_download)} ({rate:.0f}/sec, {mb:.1f} MB downloaded)")

    elapsed = time.time() - start
    mb = total_bytes / (1024 * 1024)

    print()
    print("=" * 50)
    print("PHOTO DOWNLOAD SUMMARY")
    print("=" * 50)
    print(f"  Downloaded:  {downloaded}")
    print(f"  Errors:      {errors}")
    print(f"  Skipped:     {len(existing)}")
    print(f"  Total size:  {mb:.1f} MB")
    print(f"  Duration:    {elapsed:.1f}s")
    if downloaded:
        print(f"  Avg size:    {total_bytes / downloaded / 1024:.0f} KB")
        print(f"  Rate:        {downloaded / elapsed:.1f} photos/sec")
    print("=" * 50)


if __name__ == '__main__':
    sys.exit(main() or 0)
