#!/usr/bin/env python3
"""
MLS Grid (Canopy MLS) Automated Sync (Cron Job)

Designed to be run via crontab for automated MLS data syncing.
Performs incremental sync by default; nightly runs reconciliation checks
instead of a full sync (which caused rate limit violations).

Modes:
    (default)       Incremental sync: fetch only changed records (1 API request)
    --nightly       Reconciliation: count check + completeness audit (1-4 API requests)
    --reconcile     Run all reconciliation tiers (daily + weekly + monthly)
    --full-sync     Manual full sync (use only when reconciliation flags issues)
    --sync-members  Sync agent/member records

Recommended crontab entries (see deploy/prd-crontab.txt):
    # Incremental sync every 30 min during business hours
    */30 12-23 * * * cd /opt/mydreams && python3 -m apps.mlsgrid.cron_sync

    # Nightly reconciliation at 2 AM UTC
    0 2 * * * cd /opt/mydreams && python3 -m apps.mlsgrid.cron_sync --nightly
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

from apps.mlsgrid.sync_engine import MLSGridSyncEngine, print_stats
from apps.mlsgrid.reconciliation import (
    run_daily_count_check,
    run_weekly_status_check,
    run_monthly_completeness_audit,
)

LOCK_FILE = PROJECT_ROOT / 'data' / '.mlsgrid_sync.lock'


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
    """Nightly reconciliation check (replaces old full sync).

    The old nightly full sync pulled 27,000+ records across 55+ pages,
    causing rate limit violations. This replacement uses 1 API request
    to verify our data matches MLS Grid, plus a local completeness audit.

    A full sync should only be run manually when reconciliation flags
    a real problem, after a suspension clears, or when onboarding new data.
    """
    logger = logging.getLogger('mlsgrid.cron')
    logger.info("Starting nightly reconciliation (Canopy MLS)...")

    # Daily count check (1 API request)
    daily_result = run_daily_count_check()
    logger.info(f"Daily check: {daily_result['status']} "
                f"(API: {daily_result['api_active_count']}, DB: {daily_result['db_active_count']}, "
                f"drift: {daily_result['drift_pct']}%)")

    # Monthly completeness audit (0 API requests, runs nightly for freshness)
    monthly_result = run_monthly_completeness_audit()
    logger.info(f"Completeness audit: {monthly_result['status']}")

    # Check if today is Sunday (weekday 6) for weekly status check
    from datetime import datetime
    if datetime.now().weekday() == 6:
        logger.info("Sunday: running weekly status distribution check")
        weekly_result = run_weekly_status_check()
        logger.info(f"Weekly check: {weekly_result['status']}")

    overall = 'alert' if daily_result['status'] == 'alert' or monthly_result['status'] == 'alert' else daily_result['status']

    if overall == 'alert':
        logger.warning(
            "RECONCILIATION ALERT: Data drift detected. "
            "Consider running a targeted sync: "
            "python3 -m apps.mlsgrid.sync_engine --full --status Active"
        )

    return {'status': overall, 'daily': daily_result}


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
    parser.add_argument('--reconcile', action='store_true',
                        help='Run all reconciliation checks (daily + weekly + monthly)')
    parser.add_argument('--full-sync', action='store_true',
                        help='Run full sync (manual only, use after reconciliation flags issues)')
    parser.add_argument('--status', default=None,
                        help='Status filter for --full-sync (Active, Pending, etc.)')

    args = parser.parse_args()

    load_env()
    setup_logging()

    logger = logging.getLogger('mlsgrid.cron')

    # Acquire exclusive lock to prevent overlapping sync runs
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = open(LOCK_FILE, 'w')
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.info("Another sync is already running, skipping this run.")
        lock_fd.close()
        return 0

    try:
        if args.reconcile:
            from apps.mlsgrid.reconciliation import run_all_checks
            results = run_all_checks()
            logger.info(f"Reconciliation complete: {results['overall_status']} "
                        f"({results['total_api_requests']} API requests used)")
        elif args.full_sync:
            engine = MLSGridSyncEngine()
            status = args.status or 'Active'
            logger.info(f"Manual full sync: status={status}")
            engine.run_full_sync(status=status)
        elif args.nightly:
            run_nightly()
        elif args.sync_members:
            run_sync_members()
        else:
            # Default: incremental sync
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
