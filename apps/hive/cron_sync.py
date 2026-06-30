"""
Hive (SourceRE) Automated Sync — Mountain Lakes Board of REALTORS®

Designed to run via crontab. Replaces the Navica nav26 entries.

Recommended crontab additions (after removing nav26 from navica cron):

    # Hive incremental every 30 min during business hours
    15,45 12-23 * * * cd /opt/mydreams && $PY -m apps.hive.cron_sync >> /opt/mydreams/data/logs/hive-sync.log 2>&1
    15,45 0-1 * * * cd /opt/mydreams && $PY -m apps.hive.cron_sync >> /opt/mydreams/data/logs/hive-sync.log 2>&1

    # Hive nightly full sync at 2:30 AM UTC
    30 2 * * * cd /opt/mydreams && $PY -m apps.hive.cron_sync --nightly >> /opt/mydreams/data/logs/hive-sync.log 2>&1

    # Hive agent sync daily at 6 AM
    15 6 * * * cd /opt/mydreams && $PY -m apps.hive.cron_sync --sync-members >> /opt/mydreams/data/logs/hive-sync.log 2>&1
"""

import argparse
import fcntl
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from apps.hive.sync_engine import HiveSyncEngine, load_env, print_stats

LOCK_FILE = PROJECT_ROOT / 'data' / '.hive_sync.lock'


def setup_logging():
    log_dir = PROJECT_ROOT / 'data' / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_dir / 'hive_sync.log'),
            logging.StreamHandler(sys.stdout),
        ],
    )


def run_incremental():
    logger = logging.getLogger('hive.cron')
    logger.info("Starting incremental sync (Mountain Lakes via Hive)...")
    engine = HiveSyncEngine()
    stats = engine.run_incremental_sync()
    logger.info(
        f"Incremental complete: {stats['fetched']} fetched, "
        f"{stats['created']} created, {stats['updated']} updated, "
        f"{stats['deleted']} deleted, {stats['errors']} errors, "
        f"{stats.get('photos_downloaded', 0)} photos"
    )
    return stats


def run_nightly():
    """Nightly full sync — Active + Pending + Coming Soon."""
    logger = logging.getLogger('hive.cron')

    engine = HiveSyncEngine()
    total = {'fetched': 0, 'created': 0, 'updated': 0, 'deleted': 0, 'errors': 0, 'photos_downloaded': 0}

    for status in ('Active', 'Pending', 'Coming Soon'):
        logger.info(f"Nightly phase: {status}")
        stats = engine.run_full_sync(status=status)
        for k in total:
            total[k] += stats.get(k, 0)

    logger.info(
        f"Nightly complete: {total['fetched']} fetched, "
        f"{total['created']} created, {total['updated']} updated, "
        f"{total['deleted']} deleted, {total['errors']} errors, "
        f"{total['photos_downloaded']} photos"
    )
    return total


def run_sync_members():
    logger = logging.getLogger('hive.cron')
    logger.info("Starting member sync (Mountain Lakes via Hive)...")
    engine = HiveSyncEngine()
    stats = engine.sync_members()
    logger.info(f"Members: {stats['fetched']} fetched, {stats['created']} created, {stats['updated']} updated")
    return stats


def main():
    parser = argparse.ArgumentParser(description="Hive (Mountain Lakes) cron sync")
    parser.add_argument('--nightly', action='store_true', help='Full sync of Active + Pending')
    parser.add_argument('--sync-members', action='store_true', help='Sync agent records')
    args = parser.parse_args()

    load_env()
    setup_logging()

    logger = logging.getLogger('hive.cron')

    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = open(LOCK_FILE, 'w')
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.info("Another Hive sync is already running, skipping.")
        lock_fd.close()
        return 0

    try:
        if args.nightly:
            run_nightly()
        elif args.sync_members:
            run_sync_members()
        else:
            run_incremental()
    except Exception as e:
        logger.error(f"Sync failed: {e}", exc_info=True)
        return 1
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
