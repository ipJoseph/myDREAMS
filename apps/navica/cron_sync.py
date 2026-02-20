#!/usr/bin/env python3
"""
Navica MLS Automated Sync (Cron Job)

Designed to be run via crontab for automated MLS data syncing.
Performs incremental sync by default, with full sync options for
nightly rebuilds.

Recommended crontab entries:
    # Incremental sync every 15 minutes during business hours
    */15 8-20 * * * cd /home/bigeug/myDREAMS && python3 -m apps.navica.cron_sync

    # Full active listings sync nightly at 2 AM
    0 2 * * * cd /home/bigeug/myDREAMS && python3 -m apps.navica.cron_sync --nightly

    # Sync sold data weekly (Sunday 3 AM) via BBO feed
    0 3 * * 0 cd /home/bigeug/myDREAMS && python3 -m apps.navica.cron_sync --weekly-sold

    # Sync agents and open houses daily at 6 AM
    0 6 * * * cd /home/bigeug/myDREAMS && python3 -m apps.navica.cron_sync --daily-extras
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from apps.navica.sync_engine import NavicaSyncEngine, print_stats


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
    """Standard incremental sync (every 15 min)."""
    logger = logging.getLogger('navica.cron')
    logger.info("Starting incremental sync...")

    engine = NavicaSyncEngine(feed='idx')
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
    """
    Nightly full sync of active and pending listings.
    Catches any listings missed by incremental sync.
    """
    logger = logging.getLogger('navica.cron')
    logger.info("Starting nightly full sync...")

    engine = NavicaSyncEngine(feed='idx')

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


def run_weekly_sold():
    """
    Weekly sync of sold listings via BBO feed.
    Pulls closed transactions for CMA and market analysis.
    """
    logger = logging.getLogger('navica.cron')
    logger.info("Starting weekly sold data sync (BBO feed)...")

    engine = NavicaSyncEngine(feed='bbo')
    stats = engine.run_full_sync(status='Closed')

    logger.info(
        f"Weekly sold sync complete: "
        f"{stats['fetched']} fetched, "
        f"{stats['created']} created, "
        f"{stats['updated']} updated"
    )
    return stats


def run_daily_extras():
    """
    Daily sync of agents and open houses.
    """
    logger = logging.getLogger('navica.cron')
    logger.info("Starting daily extras sync (agents + open houses)...")

    engine = NavicaSyncEngine(feed='idx')

    member_stats = engine.sync_members()
    logger.info(f"Members synced: {member_stats['fetched']} fetched")

    oh_stats = engine.sync_open_houses()
    logger.info(f"Open houses synced: {oh_stats['fetched']} fetched")

    return {'members': member_stats, 'open_houses': oh_stats}


def main():
    parser = argparse.ArgumentParser(description="Navica MLS cron sync")
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
