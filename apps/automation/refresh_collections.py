#!/usr/bin/env python3
"""
Collection Refresh Cron Job

Runs daily to:
1. Detect browsing patterns for active contacts and create smart collections
2. Refresh auto-refresh collections with new matching listings
3. Log summary for agent notification

Usage:
    python3 -m apps.automation.refresh_collections
    python3 -m apps.automation.refresh_collections --dry-run
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from apps.automation.smart_collections import (
    detect_all_patterns,
    refresh_auto_collections,
)

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='Collection Refresh Cron')
    parser.add_argument('--dry-run', action='store_true', help='Preview without changes')
    parser.add_argument('--days', type=int, default=14, help='Look-back period')
    parser.add_argument('--min-events', type=int, default=10, help='Min events threshold')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    logger.info("=== Collection Refresh Started (%s) ===", datetime.now(tz=None).isoformat())

    # Step 1: Pattern detection
    logger.info("Step 1: Detecting browsing patterns...")
    results = detect_all_patterns(
        days=args.days,
        min_events=args.min_events,
        dry_run=args.dry_run,
    )
    new_collections = [r for r in results if r.get('collection_id')]
    logger.info(
        "Pattern detection complete: %d patterns found, %d collections created",
        len(results), len(new_collections)
    )

    # Step 2: Refresh auto-refresh collections
    logger.info("Step 2: Refreshing auto-refresh collections...")
    if not args.dry_run:
        refreshed = refresh_auto_collections()
        logger.info("Refreshed %d auto-refresh collections", refreshed)
    else:
        logger.info("DRY RUN: Skipping auto-refresh")

    # Summary
    logger.info("=== Collection Refresh Complete ===")
    if new_collections:
        logger.info(
            "ACTION NEEDED: %d new smart collections awaiting agent review",
            len(new_collections)
        )


if __name__ == '__main__':
    main()
