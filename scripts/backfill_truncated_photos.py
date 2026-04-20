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
import time
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument(
        "--sleep",
        type=float,
        default=0.2,
        help="seconds between API requests (throttle)",
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

    logger.info("Found %d truncated CanopyMLS listings to refresh", len(rows))
    if not rows:
        return 0

    client = MLSGridClient.from_env()
    fixed = 0
    unchanged = 0
    errors = 0

    for i, row in enumerate(rows, 1):
        mls = row["mls_number"]
        try:
            media = client.fetch_media_for_listing(mls)
        except Exception as e:
            logger.warning("[%d/%d] %s fetch failed: %s", i, len(rows), mls, e)
            errors += 1
            continue

        primary, all_photos, photo_count = extract_photos(media)

        if not all_photos:
            logger.info("[%d/%d] %s returned 0 Media; skipping", i, len(rows), mls)
            unchanged += 1
            time.sleep(args.sleep)
            continue

        if args.dry_run:
            logger.info(
                "[%d/%d] %s would refresh to %d photos", i, len(rows), mls, len(all_photos)
            )
            fixed += 1
            continue

        conn2 = get_db()
        try:
            conn2.execute(
                """UPDATE listings
                   SET photos = ?, primary_photo = ?, photo_count = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                [json.dumps(all_photos), primary, photo_count, row["id"]],
            )
            conn2.commit()
            fixed += 1
            if i % 50 == 0 or i == len(rows):
                logger.info(
                    "[%d/%d] %s -> %d photos (fixed=%d unchanged=%d errors=%d)",
                    i, len(rows), mls, len(all_photos), fixed, unchanged, errors,
                )
        finally:
            try:
                conn2.close()
            except Exception:
                pass

        time.sleep(args.sleep)

    logger.info(
        "Backfill complete: fixed=%d unchanged=%d errors=%d total=%d",
        fixed, unchanged, errors, len(rows),
    )
    return 0 if errors < len(rows) * 0.05 else 1


if __name__ == "__main__":
    sys.exit(main())
