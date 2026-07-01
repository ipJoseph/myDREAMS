"""
Hive (SourceRE) Photo Downloader — Mountain Lakes Board of REALTORS®

Downloads CDN photos from cdn.sourceredb.com for listings where
gallery_status IS NULL (just synced, photos not yet local).

Photos are stored to the same 'navica' subdirectory as old nav26 data
(storage.SOURCE_DIRS maps 'mountainlakesmls' -> 'navica'). Primary:
  {mls_number}.jpg
Gallery:
  {mls_number}_01.jpg, {mls_number}_02.jpg, ...

The CDN rate limit is separate from the OData API limit (3 req/s).
Use --max-rps 2.0 as a safe default.

Usage:
    # Full initial download (all pending ML listings):
    python -m apps.hive.download_photos

    # Limit RPS and batch size:
    python -m apps.hive.download_photos --max-rps 2.0 --limit 100

    # Quick preview (no writes):
    python -m apps.hive.download_photos --dry-run
"""

import argparse
import fcntl
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

LOCK_FILE = REPO_ROOT / 'data' / '.hive_photos.lock'

import os
from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

from apps.photos import downloader as photo_dl, storage
from apps.photos.downloader import detect_extension

logger = logging.getLogger(__name__)

MLS_SOURCE = 'MountainLakesMLS'


def _get_db():
    from src.core.pg_adapter import get_db
    return get_db()


def fetch_pending_listings(conn, limit: Optional[int] = None, only_primary: bool = False) -> List[dict]:
    """Return ML listings where photos need downloading."""
    where_clause = """
        WHERE mls_source = 'MountainLakesMLS'
          AND status = 'ACTIVE'
          AND (gallery_status IS NULL OR gallery_status = 'pending')
          AND photos IS NOT NULL
    """
    order = "ORDER BY list_date DESC NULLS LAST"
    sql = f"SELECT mls_number, primary_photo, photos, photo_count FROM listings {where_clause} {order}"
    if limit:
        sql += f" LIMIT {limit}"

    cursor = conn.execute(sql)
    rows = cursor.fetchall()
    return [dict(r) for r in rows]


def download_listing_photos(
    conn,
    row: dict,
    max_rps: float,
    last_request_time: list,
    dry_run: bool = False,
) -> Tuple[int, int]:
    """Download all photos for one listing. Returns (downloaded, errors)."""
    mls_number = row['mls_number']
    photos_raw = row.get('photos')
    if not photos_raw:
        return 0, 0

    # Parse CDN URLs from the photos JSON field
    try:
        if isinstance(photos_raw, list):
            cdn_urls = photos_raw
        else:
            cdn_urls = json.loads(photos_raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"{mls_number}: could not parse photos JSON")
        return 0, 1

    if not cdn_urls:
        return 0, 0

    source_dir = storage.get_source_dir(MLS_SOURCE)

    local_paths = []
    errors = 0
    gap = 1.0 / max_rps if max_rps > 0 else 0.0

    for idx, cdn_url in enumerate(cdn_urls):
        ext = detect_extension(cdn_url)
        if idx == 0:
            filename = storage.primary_filename(mls_number, ext)
        else:
            filename = storage.gallery_filename(mls_number, idx, ext)

        dest = source_dir / filename

        if dest.exists() and dest.stat().st_size > 200:
            # Already downloaded — just record the serving URL
            key = (MLS_SOURCE or '').lower().replace(' ', '')
            source_name = storage.SOURCE_DIRS.get(key, key)
            local_paths.append(f"/api/public/photos/{source_name}/{filename}")
            continue

        if dry_run:
            local_paths.append(f"[dry-run] {filename}")
            continue

        # Rate-limit against CDN
        elapsed = time.time() - last_request_time[0]
        if elapsed < gap:
            time.sleep(gap - elapsed)
        last_request_time[0] = time.time()

        data = photo_dl.download_photo(cdn_url)
        if data:
            try:
                storage.save_atomic(source_dir, filename, data)
            except OSError as exc:
                logger.error(f"  DISK ERROR saving {filename}: {exc}")
                errors += 1
                continue
            key = (MLS_SOURCE or '').lower().replace(' ', '')
            source_name = storage.SOURCE_DIRS.get(key, key)
            local_paths.append(f"/api/public/photos/{source_name}/{filename}")
            logger.debug(f"  {filename} ({len(data):,} bytes)")
        else:
            errors += 1
            logger.debug(f"  FAILED: {cdn_url[:80]}")

    if not dry_run and local_paths:
        primary_local = local_paths[0] if local_paths else None
        ok = len(local_paths)
        total = len(cdn_urls)
        is_complete = ok >= max(1, total - 1)
        gallery_status = 'ready' if is_complete else 'pending'

        conn.execute(
            """UPDATE listings SET
               primary_photo = ?,
               photos = ?,
               photo_verified_at = CURRENT_TIMESTAMP,
               gallery_status = ?,
               gallery_priority = 0
               WHERE mls_source = 'MountainLakesMLS' AND mls_number = ?""",
            [
                primary_local,
                json.dumps(local_paths),
                gallery_status,
                mls_number,
            ],
        )
        conn.commit()

    downloaded = len(local_paths) - errors
    return downloaded, errors


def run(max_rps: float = 2.0, limit: Optional[int] = None, dry_run: bool = False):
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_fh = open(LOCK_FILE, 'w')
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.info("Another hive photo download is already running; exiting.")
        lock_fh.close()
        return

    try:
        conn = _get_db()
        try:
            pending = fetch_pending_listings(conn, limit=limit)
            total_listings = len(pending)
            logger.info(f"Found {total_listings} pending Hive/ML listings")

            if not pending:
                logger.info("All caught up.")
                return

            total_dl = 0
            total_err = 0
            last_request_time = [0.0]

            for i, row in enumerate(pending, 1):
                mls_number = row['mls_number']
                photo_count = row.get('photo_count') or 0
                logger.info(f"[{i}/{total_listings}] {mls_number} ({photo_count} photos)")

                dl, err = download_listing_photos(
                    conn, row, max_rps=max_rps,
                    last_request_time=last_request_time,
                    dry_run=dry_run,
                )
                total_dl += dl
                total_err += err

                if i % 50 == 0:
                    dl_stats = photo_dl.stats()
                    logger.info(
                        f"Progress: {i}/{total_listings} listings | "
                        f"{total_dl} photos downloaded | {total_err} errors | "
                        f"dl-stats={dl_stats}"
                    )

        finally:
            conn.close()

        dl_stats = photo_dl.stats()
        logger.info(
            f"Done: {total_listings} listings processed | "
            f"{total_dl} photos downloaded | {total_err} errors | "
            f"downloader stats: {dl_stats}"
        )
    finally:
        fcntl.flock(lock_fh, fcntl.LOCK_UN)
        lock_fh.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Hive photo downloader")
    parser.add_argument('--max-rps', type=float, default=2.0,
                        help='Max CDN requests per second (default 2.0)')
    parser.add_argument('--limit', type=int,
                        help='Max listings to process (default all pending)')
    parser.add_argument('--dry-run', action='store_true',
                        help='List what would be downloaded without writing')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    run(max_rps=args.max_rps, limit=args.limit, dry_run=args.dry_run)
