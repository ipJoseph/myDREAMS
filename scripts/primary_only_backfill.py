"""Primary-photo-only backfill for CanopyMLS pending listings.

Companion to gallery_backfill_strict.py. While the strict script downloads
full galleries (~25 photos × ~17 sec each), this one downloads ONLY the
primary photo for each pending listing so it appears on the public grid
within minutes instead of hours. The full gallery worker still runs and
fills in remaining photos later.

Per-listing cost: 2 MLS Grid requests (1 metadata + 1 photo) vs. ~26 for
the full backfill. At max-rps 1.8, that's roughly 1.1 sec/listing — a
1,200-listing backlog clears in ~22 minutes instead of ~6 hours.

This script DOES NOT touch gallery_status. The full gallery worker still
needs to run to set status='ready' once all photos are local. Until then
the listing renders with primary_photo only via the existing fallback in
public.py get_listing (line ~298).

Usage:
    /opt/mydreams/venv/bin/python3 scripts/primary_only_backfill.py
    /opt/mydreams/venv/bin/python3 scripts/primary_only_backfill.py --max-rps 1.8 --limit 200
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from scripts.gallery_backfill_strict import MLSGridThrottle, _file_looks_valid  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("primary_only_backfill")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-rps", type=float, default=1.8)
    ap.add_argument("--daily-budget", type=int, default=20000)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    from apps.mlsgrid.client import MLSGridClient
    from apps.navica.field_mapper import extract_photos
    from apps.photos import storage
    from apps.photos.downloader import download_photo, detect_extension
    from src.core.pg_adapter import get_db

    photos_dir = storage.get_source_dir("CanopyMLS")
    photos_dir.mkdir(parents=True, exist_ok=True)

    throttle = MLSGridThrottle(args.max_rps, args.daily_budget)
    client = MLSGridClient.from_env()

    conn = get_db()
    rows = conn.execute(
        """
        SELECT id, mls_number, list_date
        FROM listings
        WHERE status = 'ACTIVE'
          AND mls_source = 'CanopyMLS'
          AND gallery_status = 'pending'
          AND (primary_photo IS NULL OR primary_photo = '')
        ORDER BY list_date DESC NULLS LAST
        """
    ).fetchall()
    rows = [dict(r) for r in rows]
    if args.limit:
        rows = rows[: args.limit]

    logger.info("Processing %d pending listings (max_rps=%.2f)", len(rows), args.max_rps)
    if not rows:
        return 0

    started = time.time()
    downloaded = errors = skipped = 0

    for i, row in enumerate(rows, 1):
        mls = row["mls_number"]
        try:
            throttle.acquire()
            media = client.fetch_media_for_listing(mls)
        except Exception as e:
            logger.warning("%s: fetch_media failed: %s", mls, str(e)[:100])
            errors += 1
            continue

        primary_url, all_urls, photo_count = extract_photos(media)
        if not primary_url:
            errors += 1
            continue

        ext = detect_extension(primary_url)
        filename = f"{mls}{ext}"
        filepath = photos_dir / filename

        if filepath.exists() and _file_looks_valid(filepath):
            skipped += 1
        else:
            throttle.acquire()
            data = download_photo(primary_url)
            if not data:
                errors += 1
                continue
            storage.save_atomic(photos_dir, filename, data)
            downloaded += 1

        local_url = f"/api/public/photos/mlsgrid/{filename}"
        c = get_db()
        try:
            c.execute(
                "UPDATE listings SET primary_photo = ?, photo_count = ? WHERE id = ?",
                [local_url, photo_count, row["id"]],
            )
            c.commit()
        finally:
            c.close()

        if i % 25 == 0 or i == len(rows):
            elapsed = time.time() - started
            rate = i / elapsed if elapsed else 0
            eta = (len(rows) - i) / rate if rate else 0
            logger.info(
                "[%d/%d] %s/%s downloaded=%d skipped=%d errors=%d rate=%.2f list/s ETA=%.0fs",
                i, len(rows), row.get("list_date"), mls,
                downloaded, skipped, errors, rate, eta,
            )

    elapsed = time.time() - started
    logger.info(
        "Done. %d downloaded, %d skipped, %d errors in %.1fs (%.2f list/s)",
        downloaded, skipped, errors, elapsed, len(rows) / elapsed if elapsed else 0,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
