"""
Photo hygiene cron job.

Fills missing photos for all active listings across all MLS sources.
Runs independently from the sync engine — a stalled photo download
never blocks listing sync.

Usage:
    # Fill missing primary photos (fast, ~10 min)
    python3 -m apps.photos.cron

    # Fill primary + gallery (slower, ~2 hours)
    python3 -m apps.photos.cron --gallery

    # Dry run (report only)
    python3 -m apps.photos.cron --dry-run

    # Limit to N listings
    python3 -m apps.photos.cron --limit 100

    # Specific MLS source
    python3 -m apps.photos.cron --source CanopyMLS

Crontab entry (see deploy/prd-crontab.txt):
    0 4 * * * cd /opt/mydreams && DATABASE_URL=... python3 -m apps.photos.cron >> data/logs/photo-hygiene.log 2>&1
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from apps.photos.manager import run_photo_fill, HygieneReport
from apps.photos import storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("photos.cron")

# MLS sources to process
MLS_SOURCES = ["CanopyMLS", "NavicaMLS", "MountainLakesMLS"]


def main():
    parser = argparse.ArgumentParser(description="Photo hygiene: fill missing photos")
    parser.add_argument("--gallery", action="store_true",
                        help="Download full galleries (slower)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report gaps only, don't download")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit to N listings per source")
    parser.add_argument("--source", type=str, default=None,
                        help="Process only this MLS source")
    args = parser.parse_args()

    primary_only = not args.gallery
    sources = [args.source] if args.source else MLS_SOURCES

    logger.info("=" * 60)
    logger.info(f"PHOTO HYGIENE CRON — {datetime.now().isoformat()}")
    logger.info(f"Mode: {'primary only' if primary_only else 'primary + gallery'}")
    logger.info(f"Sources: {sources}")
    if args.limit:
        logger.info(f"Limit: {args.limit} per source")
    logger.info("=" * 60)

    if args.dry_run:
        # Just count missing photos per source
        from src.core.pg_adapter import get_db
        conn = get_db()
        for source in sources:
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM listings "
                    "WHERE UPPER(status) = ? AND mls_source = ? "
                    "AND (gallery_status IS NULL OR gallery_status != 'ready')",
                    ["ACTIVE", source],
                ).fetchone()
                count = row[0] if row else 0

                # Also check disk directly
                disk_missing = 0
                rows = conn.execute(
                    "SELECT mls_number FROM listings "
                    "WHERE UPPER(status) = ? AND mls_source = ?",
                    ["ACTIVE", source],
                ).fetchall()
                for r in rows:
                    mls = r[0] if isinstance(r, (list, tuple)) else r["mls_number"]
                    if not storage.primary_exists(source, mls):
                        disk_missing += 1

                logger.info(f"  {source}: DB says {count} missing, disk check says {disk_missing} missing")
            except Exception as e:
                logger.error(f"  {source}: error checking — {e}")
        conn.close()
        return

    total = HygieneReport()
    for source in sources:
        logger.info(f"\n--- Processing {source} ---")
        report = run_photo_fill(
            mls_source=source,
            status="ACTIVE",
            primary_only=primary_only,
            limit=args.limit,
        )
        total.total_checked += report.total_checked
        total.already_ok += report.already_ok
        total.downloaded += report.downloaded
        total.failed += report.failed

    logger.info("=" * 60)
    logger.info("PHOTO HYGIENE SUMMARY")
    logger.info(f"  Checked:     {total.total_checked}")
    logger.info(f"  Already OK:  {total.already_ok}")
    logger.info(f"  Downloaded:  {total.downloaded}")
    logger.info(f"  Failed:      {total.failed}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
