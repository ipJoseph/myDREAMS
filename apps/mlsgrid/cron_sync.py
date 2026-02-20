#!/usr/bin/env python3
"""
MLS Grid (Canopy MLS) Automated Sync (Cron Job)

Designed to be run via crontab for automated MLS data syncing.
Performs incremental sync by default, with full sync for nightly rebuilds.

Recommended crontab entries:
    # Incremental sync every 15 minutes during business hours
    */15 8-20 * * * cd /home/bigeug/myDREAMS && python3 -m apps.mlsgrid.cron_sync

    # Full active listings sync nightly at 2:30 AM (offset from Navica at 2:00)
    30 2 * * * cd /home/bigeug/myDREAMS && python3 -m apps.mlsgrid.cron_sync --nightly

    # Sync agents weekly on Sunday at 4 AM
    0 4 * * 0 cd /home/bigeug/myDREAMS && python3 -m apps.mlsgrid.cron_sync --sync-members
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from apps.mlsgrid.sync_engine import MLSGridSyncEngine, print_stats


def setup_logging(log_dir: Path = None):
    """Set up logging for cron execution."""
    if log_dir is None:
        log_dir = PROJECT_ROOT / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / 'mlsgrid_sync.log'

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
    """Standard incremental sync (every 15 min)."""
    logger = logging.getLogger('mlsgrid.cron')
    logger.info("Starting incremental sync (Canopy MLS via MLS Grid)...")

    engine = MLSGridSyncEngine()
    stats = engine.run_incremental_sync()

    logger.info(
        f"Incremental sync complete: "
        f"{stats['fetched']} fetched, "
        f"{stats['created']} created, "
        f"{stats['updated']} updated, "
        f"{stats['errors']} errors"
    )
    return stats


def run_nightly():
    """Nightly full sync of active and pending listings."""
    logger = logging.getLogger('mlsgrid.cron')
    logger.info("Starting nightly full sync (Canopy MLS)...")

    engine = MLSGridSyncEngine()

    # Sync active listings
    logger.info("Phase 1: Active listings")
    active_stats = engine.run_full_sync(status='Active')

    # Sync pending listings
    logger.info("Phase 2: Pending listings")
    engine.client.reset_stats()
    pending_stats = engine.run_full_sync(status='Pending')

    total = {
        'fetched': active_stats['fetched'] + pending_stats['fetched'],
        'created': active_stats['created'] + pending_stats['created'],
        'updated': active_stats['updated'] + pending_stats['updated'],
        'errors': active_stats['errors'] + pending_stats['errors'],
    }

    logger.info(
        f"Nightly sync complete: "
        f"{total['fetched']} fetched, "
        f"{total['created']} created, "
        f"{total['updated']} updated"
    )
    return total


def run_sync_members():
    """Sync agent/member records."""
    logger = logging.getLogger('mlsgrid.cron')
    logger.info("Starting member sync (Canopy MLS)...")

    engine = MLSGridSyncEngine()
    stats = engine.sync_members()

    logger.info(f"Members synced: {stats['fetched']} fetched")
    return stats


def main():
    parser = argparse.ArgumentParser(description="MLS Grid (Canopy MLS) cron sync")
    parser.add_argument('--nightly', action='store_true',
                        help='Run nightly full sync')
    parser.add_argument('--sync-members', action='store_true',
                        help='Sync agents/members')

    args = parser.parse_args()

    load_env()
    setup_logging()

    try:
        if args.nightly:
            run_nightly()
        elif args.sync_members:
            run_sync_members()
        else:
            # Default: incremental sync
            run_incremental()
    except Exception as e:
        logging.getLogger('mlsgrid.cron').error(f"Sync failed: {e}", exc_info=True)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
