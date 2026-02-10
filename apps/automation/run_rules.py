#!/usr/bin/env python3
"""
Automation Rules Runner

CLI entry point for running the automation rules engine.
Intended to be called by cron after FUB sync, or independently.

Usage:
    python -m apps.automation.run_rules                    # Run all rules
    python -m apps.automation.run_rules --dry-run          # Preview what would fire
    python -m apps.automation.run_rules --rule hot_lead    # Run single rule
    python -m apps.automation.run_rules --rule hot_lead --dry-run
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.database import DREAMSDatabase
from apps.automation.rules_engine import RuleEngine
from apps.automation.rules import RULE_REGISTRY


def get_fub_client():
    """Lazy-load FUB client (same pattern as new_listing_alerts.py)."""
    api_key = os.getenv('FUB_API_KEY')
    if not api_key:
        return None
    try:
        from fub_core import FUBClient
        return FUBClient(api_key=api_key, logger=logging.getLogger('fub_core'))
    except ImportError:
        logging.getLogger(__name__).warning("fub_core not available — FUB actions will be skipped")
        return None


def main():
    parser = argparse.ArgumentParser(description='Run DREAMS automation rules')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview what would fire without executing actions')
    parser.add_argument('--rule', type=str, default=None,
                        help=f'Run a single rule: {", ".join(RULE_REGISTRY.keys())}')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable debug logging')
    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    logger = logging.getLogger('rules_engine')

    # Banner
    mode = 'DRY RUN' if args.dry_run else 'LIVE'
    logger.info(f"=== DREAMS Rules Engine ({mode}) — {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")

    # Initialize
    db_path = os.getenv('DREAMS_DB_PATH', str(PROJECT_ROOT / 'data' / 'dreams.db'))
    db = DREAMSDatabase(db_path)
    fub_client = get_fub_client() if not args.dry_run else None

    engine = RuleEngine(db=db, fub_client=fub_client, dry_run=args.dry_run)

    # Run
    if args.rule:
        if args.rule not in RULE_REGISTRY:
            logger.error(f"Unknown rule: {args.rule}. Available: {', '.join(RULE_REGISTRY.keys())}")
            sys.exit(1)
        results = engine.evaluate_rule(args.rule)
        results = {'status': 'completed', 'rules': {args.rule: results}}
    else:
        results = engine.evaluate_all()

    # Summary
    logger.info("=== Results ===")
    for rule_name, rule_result in results.get('rules', {}).items():
        status = rule_result.get('status', 'unknown')
        if status == 'disabled':
            logger.info(f"  {rule_name}: disabled")
        elif status == 'error':
            logger.error(f"  {rule_name}: ERROR — {rule_result.get('error')}")
        else:
            firings = rule_result.get('firings', 0)
            actions = rule_result.get('actions', 0)
            skipped = rule_result.get('skipped_cooldown', 0)
            logger.info(f"  {rule_name}: {firings} fired, {actions} actions, {skipped} cooldown skips")

            # Show details in verbose/dry-run mode
            if (args.dry_run or args.verbose) and rule_result.get('details'):
                for detail in rule_result['details']:
                    logger.info(f"    → {detail['contact']}: {detail['action']} — {detail['detail']}")

    total = results.get('total_firings', sum(
        r.get('firings', 0) for r in results.get('rules', {}).values()
    ))
    logger.info(f"=== Done: {total} total firings ===")

    return results


if __name__ == '__main__':
    main()
