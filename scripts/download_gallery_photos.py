#!/usr/bin/env python3
"""
Download full photo galleries for listings in WNC zones (1+2).

Downloads all photos from the `photos` JSON array (not just the primary).
Files are stored as: data/photos/{source}/{mls_number}_{index:02d}.{ext}

The primary photo (index 00) is skipped if already downloaded by the
primary-photo downloaders. Only gallery photos (index 01+) are new.

After downloading, updates the `photos_local` column in the DB with a
JSON array of local filenames so the API can serve them without CDN tokens.

Usage:
    python3 scripts/download_gallery_photos.py                  # dry-run
    python3 scripts/download_gallery_photos.py --apply          # download
    python3 scripts/download_gallery_photos.py --apply --max 50 # limit
    python3 scripts/download_gallery_photos.py --apply --zone 1 # zone 1 only
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
DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'

PHOTOS_DIRS = {
    'CanopyMLS': PROJECT_ROOT / 'data' / 'photos' / 'mlsgrid',
    'NavicaMLS': PROJECT_ROOT / 'data' / 'photos' / 'navica',
    'MountainLakesMLS': PROJECT_ROOT / 'data' / 'photos' / 'navica',
}

# Map source names to URL path segment for serving
SOURCE_NAMES = {
    'CanopyMLS': 'mlsgrid',
    'NavicaMLS': 'navica',
    'MountainLakesMLS': 'navica',
}


def load_env():
    env_path = PROJECT_ROOT / '.env'
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip().strip('"\''))


def detect_ext(url: str) -> str:
    """Detect image extension from URL path."""
    parsed = urlparse(url)
    path_lower = parsed.path.lower()
    if path_lower.endswith('.png'):
        return '.png'
    elif path_lower.endswith('.webp'):
        return '.webp'
    return '.jpg'


def file_exists(dest_dir: Path, mls_number: str, index: int) -> Path | None:
    """Check if a gallery photo already exists (any extension)."""
    prefix = f"{mls_number}_{index:02d}"
    for ext in ('.jpg', '.jpeg', '.png', '.webp'):
        fp = dest_dir / f"{prefix}{ext}"
        if fp.exists() and fp.stat().st_size > 0:
            return fp
    return None


def primary_exists(dest_dir: Path, mls_number: str) -> Path | None:
    """Check if the primary photo already exists (no index suffix)."""
    for ext in ('.jpg', '.jpeg', '.png', '.webp'):
        fp = dest_dir / f"{mls_number}{ext}"
        if fp.exists() and fp.stat().st_size > 0:
            return fp
    return None


def download_one(mls_number: str, url: str, index: int, dest_dir: Path) -> dict:
    """Download a single gallery photo."""
    ext = detect_ext(url)
    filename = f"{mls_number}_{index:02d}{ext}"
    filepath = dest_dir / filename

    # Skip if already downloaded
    existing = file_exists(dest_dir, mls_number, index)
    if existing:
        return {
            'mls': mls_number, 'index': index,
            'status': 'skipped', 'path': existing.name,
        }

    try:
        resp = requests.get(url, timeout=30, stream=True)
        resp.raise_for_status()

        content_type = resp.headers.get('Content-Type', '')
        if 'image' not in content_type and content_type:
            return {
                'mls': mls_number, 'index': index,
                'status': 'error', 'error': f'Not an image: {content_type}',
            }

        with open(filepath, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        size = filepath.stat().st_size
        if size == 0:
            filepath.unlink()
            return {
                'mls': mls_number, 'index': index,
                'status': 'error', 'error': 'Empty file',
            }

        return {
            'mls': mls_number, 'index': index,
            'status': 'downloaded', 'size': size, 'path': filename,
        }

    except requests.RequestException as e:
        if filepath.exists():
            filepath.unlink()
        return {
            'mls': mls_number, 'index': index,
            'status': 'error', 'error': str(e),
        }


def build_local_photos_list(dest_dir: Path, mls_number: str, photo_count: int) -> list[str]:
    """Build a list of local filenames for all gallery photos of a listing."""
    local = []
    # Index 00 = primary photo (stored without index suffix by primary downloader)
    primary = primary_exists(dest_dir, mls_number)
    if primary:
        local.append(primary.name)
    else:
        # Check if index 00 exists with suffix
        p00 = file_exists(dest_dir, mls_number, 0)
        local.append(p00.name if p00 else None)

    # Index 01+ = gallery photos
    for i in range(1, photo_count):
        fp = file_exists(dest_dir, mls_number, i)
        local.append(fp.name if fp else None)

    return local


def main():
    parser = argparse.ArgumentParser(description="Download gallery photos for WNC listings")
    parser.add_argument('--apply', action='store_true', help='Actually download (default is dry-run)')
    parser.add_argument('--max', type=int, help='Max listings to process')
    parser.add_argument('--workers', type=int, default=10, help='Parallel workers (default: 10)')
    parser.add_argument('--zone', default='1,2', help='Zones to download for (default: 1,2)')
    parser.add_argument('--min-photos', type=int, default=2, help='Min photos to qualify (default: 2)')
    parser.add_argument('--db', type=str, default=str(DB_PATH), help='Database path')
    args = parser.parse_args()

    load_env()

    # Parse zones
    zones = [int(z.strip()) for z in args.zone.split(',') if z.strip().isdigit()]
    if not zones:
        print("Error: no valid zones specified")
        return 1

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    # Ensure photos_local column exists
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(listings)").fetchall()}
    if 'photos_local' not in existing_cols:
        print("Adding 'photos_local' column to listings table...")
        if args.apply:
            conn.execute("ALTER TABLE listings ADD COLUMN photos_local TEXT")
            conn.commit()
            print("  Column added.")
        else:
            print("  [dry-run] Would add column.")

    # Get listings with gallery photos in target zones
    placeholders = ','.join(['?'] * len(zones))
    query = f"""
        SELECT mls_number, mls_source, photos, photo_count
        FROM listings
        WHERE zone IN ({placeholders})
        AND UPPER(status) = 'ACTIVE'
        AND photos IS NOT NULL
        AND photo_count >= ?
        ORDER BY list_price DESC
    """
    rows = conn.execute(query, zones + [args.min_photos]).fetchall()
    conn.close()

    if args.max:
        rows = rows[:args.max]

    # Build download queue: (mls_number, url, index, dest_dir)
    queue = []
    listings_info = {}  # mls_number -> (mls_source, photo_count)

    for row in rows:
        mls = row['mls_number']
        source = row['mls_source']
        dest_dir = PHOTOS_DIRS.get(source)
        if not dest_dir:
            continue

        try:
            photos = json.loads(row['photos'])
        except (json.JSONDecodeError, TypeError):
            continue

        if not photos or len(photos) < 2:
            continue

        listings_info[mls] = (source, len(photos))

        # Skip index 0 (primary photo already downloaded separately)
        for i, url in enumerate(photos[1:], start=1):
            if url and isinstance(url, str):
                queue.append((mls, url, i, dest_dir))

    # Check how many are already downloaded
    already = 0
    to_download = []
    for mls, url, idx, dest_dir in queue:
        if file_exists(dest_dir, mls, idx):
            already += 1
        else:
            to_download.append((mls, url, idx, dest_dir))

    print(f"Zones:                {args.zone}")
    print(f"Listings with 2+ photos: {len(listings_info):,}")
    print(f"Total gallery photos: {len(queue):,}")
    print(f"Already downloaded:   {already:,}")
    print(f"To download:          {len(to_download):,}")
    print(f"Workers:              {args.workers}")
    print()

    if not args.apply:
        print("[dry-run] No downloads. Use --apply to download.")
        return

    # Ensure directories exist
    for d in PHOTOS_DIRS.values():
        d.mkdir(parents=True, exist_ok=True)

    if not to_download:
        print("Nothing to download. Updating DB...")
    else:
        start = time.time()
        downloaded = 0
        errors = 0
        total_bytes = 0

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(download_one, mls, url, idx, dest_dir): (mls, idx)
                for mls, url, idx, dest_dir in to_download
            }

            for i, future in enumerate(as_completed(futures), 1):
                result = future.result()

                if result['status'] == 'downloaded':
                    downloaded += 1
                    total_bytes += result.get('size', 0)
                elif result['status'] == 'error':
                    errors += 1
                    if errors <= 20:
                        print(f"  Error {result['mls']}[{result['index']}]: {result['error']}")

                if i % 500 == 0 or i == len(to_download):
                    elapsed = time.time() - start
                    rate = i / elapsed if elapsed > 0 else 0
                    mb = total_bytes / (1024 * 1024)
                    print(f"  Progress: {i:,}/{len(to_download):,} ({rate:.0f}/sec, {mb:.1f} MB downloaded)")

        elapsed = time.time() - start
        mb = total_bytes / (1024 * 1024)
        print()
        print(f"  Downloaded: {downloaded:,} ({mb:.1f} MB)")
        print(f"  Errors:     {errors:,}")
        print(f"  Duration:   {elapsed:.1f}s")
        if downloaded > 0:
            print(f"  Rate:       {downloaded / elapsed:.1f} photos/sec")
        print()

    # Update photos_local in DB for all processed listings
    print("Updating photos_local in database...")
    conn = sqlite3.connect(args.db)
    updates = []

    for mls, (source, count) in listings_info.items():
        dest_dir = PHOTOS_DIRS.get(source)
        if not dest_dir:
            continue
        local_files = build_local_photos_list(dest_dir, mls, count)
        # Only store if we have at least the primary photo
        if local_files and local_files[0]:
            source_name = SOURCE_NAMES.get(source, 'mlsgrid')
            # Convert filenames to API-servable paths
            api_paths = []
            for fname in local_files:
                if fname:
                    api_paths.append(f"/api/public/photos/{source_name}/{fname}")
                else:
                    api_paths.append(None)
            updates.append((json.dumps(api_paths), mls))

    if updates:
        conn.executemany(
            "UPDATE listings SET photos_local = ? WHERE mls_number = ?",
            updates
        )
        conn.commit()
        print(f"  Updated photos_local for {len(updates):,} listings.")
    else:
        print("  No updates needed.")

    conn.close()
    print("Done.")


if __name__ == '__main__':
    sys.exit(main() or 0)
