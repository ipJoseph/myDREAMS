#!/usr/bin/env python3
"""
Navica MLS Automated Sync (Cron Job)

Syncs both Carolina Smokies (nav27) and Mountain Lakes (nav26) datasets.
Performs incremental sync by default, with full sync options for
nightly rebuilds. Runs cross-listing detection after each sync.

Recommended crontab entries:
    # Incremental sync every 15 minutes during business hours
    */15 8-20 * * * cd /opt/mydreams && /opt/mydreams/venv/bin/python -m apps.navica.cron_sync

    # Full active listings sync nightly at 2 AM
    0 2 * * * cd /opt/mydreams && /opt/mydreams/venv/bin/python -m apps.navica.cron_sync --nightly

    # Sync sold data weekly (Sunday 3 AM) via BBO feed
    0 3 * * 0 cd /opt/mydreams && /opt/mydreams/venv/bin/python -m apps.navica.cron_sync --weekly-sold

    # Sync agents and open houses daily at 6 AM
    0 6 * * * cd /opt/mydreams && /opt/mydreams/venv/bin/python -m apps.navica.cron_sync --daily-extras
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from apps.navica.sync_engine import NavicaSyncEngine, detect_cross_listings, print_stats

# All Navica datasets to sync
NAVICA_DATASETS = [
    {'dataset_code': 'nav27', 'mls_source': 'NavicaMLS'},
    {'dataset_code': 'nav26', 'mls_source': 'MountainLakesMLS'},
]


def setup_logging(log_dir: Path = None):
    """Set up logging for cron execution."""
    if log_dir is None:
        log_dir = PROJECT_ROOT / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / 'navica_sync.log'

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout),
        ],
    )


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


def run_incremental():
    """Standard incremental sync (every 15 min) for all datasets."""
    logger = logging.getLogger('navica.cron')

    for ds in NAVICA_DATASETS:
        label = ds['mls_source']
        logger.info(f"Starting incremental sync for {label} ({ds['dataset_code']})...")

        engine = NavicaSyncEngine(feed='idx', **ds)
        stats = engine.run_incremental_sync()

        logger.info(
            f"{label} incremental: "
            f"{stats['fetched']} fetched, "
            f"{stats['created']} created, "
            f"{stats['updated']} updated, "
            f"{stats['errors']} errors"
        )

    # Cross-listing detection after all datasets are synced
    pairs = detect_cross_listings()
    if pairs:
        logger.info(f"Cross-listing: {pairs} properties found in both MLSs")


def run_nightly():
    """Nightly full sync of active and pending listings for all datasets."""
    logger = logging.getLogger('navica.cron')

    for ds in NAVICA_DATASETS:
        label = ds['mls_source']
        logger.info(f"Starting nightly full sync for {label} ({ds['dataset_code']})...")

        engine = NavicaSyncEngine(feed='idx', **ds)

        logger.info(f"{label} Phase 1: Active listings")
        active_stats = engine.run_full_sync(status='Active')

        logger.info(f"{label} Phase 2: Pending listings")
        engine.client.reset_stats()
        pending_stats = engine.run_full_sync(status='Pending')

        total_fetched = active_stats['fetched'] + pending_stats['fetched']
        total_created = active_stats['created'] + pending_stats['created']
        total_updated = active_stats['updated'] + pending_stats['updated']

        logger.info(
            f"{label} nightly complete: "
            f"{total_fetched} fetched, "
            f"{total_created} created, "
            f"{total_updated} updated"
        )

    # Cross-listing detection after all datasets are synced
    pairs = detect_cross_listings()
    if pairs:
        logger.info(f"Cross-listing: {pairs} properties found in both MLSs")


def run_weekly_sold():
    """Weekly sync of sold listings via BBO feed for all datasets."""
    logger = logging.getLogger('navica.cron')

    for ds in NAVICA_DATASETS:
        label = ds['mls_source']
        logger.info(f"Starting weekly sold sync for {label} ({ds['dataset_code']}) (BBO feed)...")

        engine = NavicaSyncEngine(feed='bbo', **ds)
        stats = engine.run_full_sync(status='Closed')

        logger.info(
            f"{label} sold sync: "
            f"{stats['fetched']} fetched, "
            f"{stats['created']} created, "
            f"{stats['updated']} updated"
        )


def run_daily_extras():
    """Daily sync of agents and open houses for all datasets."""
    logger = logging.getLogger('navica.cron')

    for ds in NAVICA_DATASETS:
        label = ds['mls_source']
        logger.info(f"Starting daily extras for {label} ({ds['dataset_code']})...")

        engine = NavicaSyncEngine(feed='idx', **ds)

        member_stats = engine.sync_members()
        logger.info(f"{label} members: {member_stats['fetched']} fetched")

        oh_stats = engine.sync_open_houses()
        logger.info(f"{label} open houses: {oh_stats['fetched']} fetched")


def main():
    parser = argparse.ArgumentParser(description="Navica MLS cron sync (all datasets)")
    parser.add_argument('--nightly', action='store_true',
                        help='Run nightly full sync')
    parser.add_argument('--weekly-sold', action='store_true',
                        help='Run weekly sold data sync (BBO)')
    parser.add_argument('--daily-extras', action='store_true',
                        help='Sync agents and open houses')

    args = parser.parse_args()

    load_env()
    setup_logging()

    try:
        if args.nightly:
            run_nightly()
        elif args.weekly_sold:
            run_weekly_sold()
        elif args.daily_extras:
            run_daily_extras()
        else:
            # Default: incremental sync
            run_incremental()
    except Exception as e:
        logging.getLogger('navica.cron').error(f"Sync failed: {e}", exc_info=True)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
