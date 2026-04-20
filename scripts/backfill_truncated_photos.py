"""One-off backfill: re-fetch Media for listings whose `photos` JSON was
truncated to a single entry (incident 2026-04-20).

Selection:
  listings.status = 'ACTIVE'
  AND photo_count > 1
  AND (photos IS NULL OR json_array_length(photos::json) <= 1)

For each, we call MLSGridClient.fetch_media_for_listing(mls_number),
rebuild the photos array + primary_photo from the Media response, and
UPDATE the row. One API request per listing, so scope matters — only
run this for rows you know are genuinely truncated.

Usage:
    /opt/mydreams/venv/bin/python3 scripts/backfill_truncated_photos.py [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("backfill_truncated_photos")


def _process_one(row, client, extract_photos_fn, get_db_fn, dry_run):
    """Fetch fresh Media for one listing and UPDATE the DB. Thread-safe:
    each call acquires its own connection from the pg_adapter pool."""
    mls = row["mls_number"]
    try:
        media = client.fetch_media_for_listing(mls)
    except Exception as e:
        return ("error", mls, str(e)[:120])

    primary, all_photos, photo_count = extract_photos_fn(media)

    if not all_photos:
        return ("unchanged", mls, 0)

    if dry_run:
        return ("fixed", mls, len(all_photos))

    conn = get_db_fn()
    try:
        conn.execute(
            """UPDATE listings
               SET photos = ?, primary_photo = ?, photo_count = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            [json.dumps(all_photos), primary, photo_count, row["id"]],
        )
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return ("fixed", mls, len(all_photos))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument(
        "--workers",
        type=int,
        default=5,
        help="Concurrent worker threads. Keep conservative to stay under MLS Grid rate limits.",
    )
    args = ap.parse_args()

    from apps.mlsgrid.client import MLSGridClient
    from apps.navica.field_mapper import extract_photos
    from src.core.pg_adapter import get_db

    conn = get_db()
    rows = conn.execute(
        """
        SELECT id, mls_source, mls_number, photo_count
        FROM listings
        WHERE status = 'ACTIVE'
          AND mls_source = 'CanopyMLS'
          AND photo_count > 1
          AND (photos IS NULL OR json_array_length(photos::json) <= 1)
        ORDER BY photo_count DESC
        """
    ).fetchall()

    rows = [dict(r) for r in rows]
    if args.limit:
        rows = rows[: args.limit]

    logger.info(
        "Found %d truncated CanopyMLS listings; running with %d workers",
        len(rows), args.workers,
    )
    if not rows:
        return 0

    client = MLSGridClient.from_env()
    fixed = 0
    unchanged = 0
    errors = 0
    started = time.time()

    # Single client instance is safe to share: the underlying requests.Session
    # is thread-safe for GETs (no mutation of its own state between calls).
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(_process_one, row, client, extract_photos, get_db, args.dry_run): row
            for row in rows
        }
        for i, fut in enumerate(as_completed(futures), 1):
            try:
                status, mls, detail = fut.result()
            except Exception as e:
                errors += 1
                logger.warning("[%d/%d] worker crashed: %s", i, len(rows), e)
                continue

            if status == "fixed":
                fixed += 1
            elif status == "unchanged":
                unchanged += 1
            elif status == "error":
                errors += 1
                logger.warning("[%d/%d] %s fetch failed: %s", i, len(rows), mls, detail)

            if i % 100 == 0 or i == len(rows):
                elapsed = time.time() - started
                rate = i / elapsed if elapsed > 0 else 0
                remaining = (len(rows) - i) / rate if rate else 0
                logger.info(
                    "[%d/%d] fixed=%d unchanged=%d errors=%d rate=%.1f/s ETA=%.0fs",
                    i, len(rows), fixed, unchanged, errors, rate, remaining,
                )

    elapsed = time.time() - started
    logger.info(
        "Backfill complete in %.0fs: fixed=%d unchanged=%d errors=%d total=%d",
        elapsed, fixed, unchanged, errors, len(rows),
    )
    return 0 if errors < len(rows) * 0.05 else 1


if __name__ == "__main__":
    sys.exit(main())
