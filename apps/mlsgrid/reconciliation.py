#!/usr/bin/env python3
"""
MLS Grid Data Reconciliation

Tiered checks to verify our local database stays in sync with MLS Grid
without the cost/risk of a nightly full sync.

Tiers:
  1. Daily count check     - 1 API request, compares total Active counts
  2. Weekly status check   - 3-4 API requests, compares counts by status
  3. Monthly completeness  - 0 API requests, audits local data quality

Replaces the old nightly full sync which pulled 27,000+ records (55+ pages)
and caused rate limit violations.

Usage:
    python3 -m apps.mlsgrid.reconciliation --daily
    python3 -m apps.mlsgrid.reconciliation --weekly
    python3 -m apps.mlsgrid.reconciliation --monthly
    python3 -m apps.mlsgrid.reconciliation --all
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from apps.mlsgrid.client import MLSGridClient, CANOPY_SYSTEM_NAME

logger = logging.getLogger(__name__)

DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'
RECONCILIATION_LOG = PROJECT_ROOT / 'data' / 'reconciliation_history.json'

MLS_SOURCE = 'CanopyMLS'

# Thresholds
DAILY_DRIFT_WARN_PCT = 2.0     # Warn if counts differ by more than 2%
DAILY_DRIFT_ALERT_PCT = 5.0    # Alert if counts differ by more than 5%
STALE_LISTING_DAYS = 7         # Flag Active listings not updated in 7 days
MISSING_FIELD_WARN_PCT = 5.0   # Warn if >5% of listings are missing a critical field


def _get_connection():
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _save_result(check_type: str, result: dict):
    """Append reconciliation result to history log."""
    history = []
    if RECONCILIATION_LOG.exists():
        try:
            history = json.loads(RECONCILIATION_LOG.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    result['type'] = check_type
    result['timestamp'] = datetime.now(timezone.utc).isoformat()
    history.append(result)

    # Keep last 90 days
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    history = [h for h in history if h.get('timestamp', '') > cutoff]

    try:
        RECONCILIATION_LOG.write_text(json.dumps(history, indent=2))
    except OSError as e:
        logger.warning(f"Could not save reconciliation history: {e}")


def run_daily_count_check(client: MLSGridClient = None) -> dict:
    """
    Daily: Compare Active listing count between MLS Grid and our DB.

    Uses $top=1 with $count=true to get the total without downloading data.
    Costs 1 API request.
    """
    logger.info("=== Daily Count Check ===")

    if client is None:
        client = MLSGridClient.from_env()

    # Get count from MLS Grid (1 API request)
    # OData $count gives total matching records without returning all data
    filter_str = (
        f"OriginatingSystemName eq '{CANOPY_SYSTEM_NAME}' "
        f"and StandardStatus eq 'Active' "
        f"and MlgCanView eq true"
    )
    data = client.get("/Property", {
        "$filter": filter_str,
        "$top": "1",
        "$count": "true",
    })

    api_count = data.get('@odata.count', len(data.get('value', [])))

    # Get count from our DB
    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM listings "
            "WHERE mls_source = ? AND UPPER(status) = 'ACTIVE'",
            (MLS_SOURCE,)
        ).fetchone()
        db_count = row['cnt']
    finally:
        conn.close()

    # Calculate drift
    if api_count > 0:
        drift_pct = abs(api_count - db_count) / api_count * 100
    else:
        drift_pct = 0 if db_count == 0 else 100

    drift_direction = "over" if db_count > api_count else "under"

    result = {
        'api_active_count': api_count,
        'db_active_count': db_count,
        'difference': db_count - api_count,
        'drift_pct': round(drift_pct, 2),
        'drift_direction': drift_direction,
        'status': 'ok',
        'api_requests_used': 1,
    }

    if drift_pct >= DAILY_DRIFT_ALERT_PCT:
        result['status'] = 'alert'
        logger.warning(
            f"ALERT: Active count drift {drift_pct:.1f}% "
            f"(API: {api_count}, DB: {db_count}, {drift_direction} by {abs(db_count - api_count)})"
        )
    elif drift_pct >= DAILY_DRIFT_WARN_PCT:
        result['status'] = 'warning'
        logger.warning(
            f"WARNING: Active count drift {drift_pct:.1f}% "
            f"(API: {api_count}, DB: {db_count}, {drift_direction} by {abs(db_count - api_count)})"
        )
    else:
        logger.info(
            f"OK: Active counts match within tolerance "
            f"(API: {api_count}, DB: {db_count}, drift: {drift_pct:.1f}%)"
        )

    _save_result('daily', result)
    return result


def run_weekly_status_check(client: MLSGridClient = None) -> dict:
    """
    Weekly: Compare listing counts by status bucket.

    Checks Active, Pending, and recently Closed (last 30 days).
    Costs 3 API requests.
    """
    logger.info("=== Weekly Status Distribution Check ===")

    if client is None:
        client = MLSGridClient.from_env()

    statuses_to_check = ['Active', 'Pending']
    results = {'buckets': {}, 'status': 'ok', 'api_requests_used': 0}

    for status in statuses_to_check:
        filter_str = (
            f"OriginatingSystemName eq '{CANOPY_SYSTEM_NAME}' "
            f"and StandardStatus eq '{status}' "
            f"and MlgCanView eq true"
        )
        data = client.get("/Property", {
            "$filter": filter_str,
            "$top": "1",
            "$count": "true",
        })
        results['api_requests_used'] += 1

        api_count = data.get('@odata.count', len(data.get('value', [])))

        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM listings "
                "WHERE mls_source = ? AND UPPER(status) = UPPER(?)",
                (MLS_SOURCE, status)
            ).fetchone()
            db_count = row['cnt']
        finally:
            conn.close()

        drift_pct = abs(api_count - db_count) / max(api_count, 1) * 100

        bucket = {
            'api_count': api_count,
            'db_count': db_count,
            'difference': db_count - api_count,
            'drift_pct': round(drift_pct, 2),
        }
        results['buckets'][status] = bucket

        if drift_pct >= DAILY_DRIFT_ALERT_PCT:
            results['status'] = 'alert'
            logger.warning(
                f"ALERT: {status} drift {drift_pct:.1f}% "
                f"(API: {api_count}, DB: {db_count})"
            )
        elif drift_pct >= DAILY_DRIFT_WARN_PCT:
            if results['status'] != 'alert':
                results['status'] = 'warning'
            logger.warning(
                f"WARNING: {status} drift {drift_pct:.1f}% "
                f"(API: {api_count}, DB: {db_count})"
            )
        else:
            logger.info(f"OK: {status} (API: {api_count}, DB: {db_count}, drift: {drift_pct:.1f}%)")

    # Also check recently Closed (last 30 days) to catch missed status transitions
    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%S.00Z')
    filter_str = (
        f"OriginatingSystemName eq '{CANOPY_SYSTEM_NAME}' "
        f"and StandardStatus eq 'Closed' "
        f"and CloseDate gt {thirty_days_ago} "
        f"and MlgCanView eq true"
    )
    data = client.get("/Property", {
        "$filter": filter_str,
        "$top": "1",
        "$count": "true",
    })
    results['api_requests_used'] += 1

    api_closed = data.get('@odata.count', len(data.get('value', [])))

    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM listings "
            "WHERE mls_source = ? AND UPPER(status) IN ('CLOSED', 'SOLD') "
            "AND close_date >= date('now', '-30 days')",
            (MLS_SOURCE,)
        ).fetchone()
        db_closed = row['cnt']
    finally:
        conn.close()

    results['buckets']['Closed_30d'] = {
        'api_count': api_closed,
        'db_count': db_closed,
        'difference': db_closed - api_closed,
    }
    logger.info(f"Closed (30d): API: {api_closed}, DB: {db_closed}")

    _save_result('weekly', results)
    return results


def run_monthly_completeness_audit() -> dict:
    """
    Monthly: Audit local data quality (no API calls).

    Checks:
    - Listings missing critical fields (photos, coordinates, price, address)
    - Stale listings (Active in DB but not updated in 7+ days)
    - Total listing counts by status
    """
    logger.info("=== Monthly Completeness Audit ===")

    conn = _get_connection()
    results = {'status': 'ok', 'api_requests_used': 0, 'checks': {}}

    try:
        # Total counts by status
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM listings "
            "WHERE mls_source = ? GROUP BY status ORDER BY cnt DESC",
            (MLS_SOURCE,)
        ).fetchall()
        status_counts = {row['status']: row['cnt'] for row in rows}
        total = sum(status_counts.values())
        results['checks']['status_distribution'] = status_counts
        results['checks']['total_listings'] = total
        logger.info(f"Total listings: {total}")
        for status, cnt in status_counts.items():
            logger.info(f"  {status}: {cnt}")

        # Active listings count for percentage calculations
        # Status may be stored as 'Active' or 'ACTIVE'
        active_count = status_counts.get('Active', 0) or status_counts.get('ACTIVE', 0)
        if active_count == 0:
            logger.warning("No Active listings found in DB")
            results['status'] = 'alert'
            results['checks']['stale'] = {'count': 0}
            results['checks']['missing_fields'] = {}
            _save_result('monthly', results)
            return results

        # Stale listings: Active but last_synced > 7 days ago
        stale_cutoff = (datetime.now(timezone.utc) - timedelta(days=STALE_LISTING_DAYS)).isoformat()
        stale_row = conn.execute(
            "SELECT COUNT(*) as cnt FROM listings "
            "WHERE mls_source = ? AND UPPER(status) = 'ACTIVE' "
            "AND (updated_at < ? OR updated_at IS NULL)",
            (MLS_SOURCE, stale_cutoff)
        ).fetchone()
        stale_count = stale_row['cnt']
        stale_pct = stale_count / max(active_count, 1) * 100
        results['checks']['stale'] = {
            'count': stale_count,
            'pct': round(stale_pct, 2),
            'threshold_days': STALE_LISTING_DAYS,
        }

        if stale_count > 0:
            logger.warning(
                f"Stale listings: {stale_count} Active listings not updated "
                f"in {STALE_LISTING_DAYS}+ days ({stale_pct:.1f}%)"
            )
            if stale_pct > 10:
                results['status'] = 'alert'
            elif stale_pct > 2:
                if results['status'] != 'alert':
                    results['status'] = 'warning'
        else:
            logger.info("No stale listings found")

        # Missing critical fields
        critical_fields = {
            'list_price': 'Price',
            'address': 'Address',
            'city': 'City',
            'latitude': 'Coordinates',
            'primary_photo': 'Primary Photo URL',
            'photo_local_path': 'Local Photo',
        }

        missing_fields = {}
        for field, label in critical_fields.items():
            row = conn.execute(
                f"SELECT COUNT(*) as cnt FROM listings "
                f"WHERE mls_source = ? AND UPPER(status) = 'ACTIVE' "
                f"AND ({field} IS NULL OR {field} = '')",
                (MLS_SOURCE,)
            ).fetchone()
            missing = row['cnt']
            if missing > 0:
                pct = missing / active_count * 100
                missing_fields[label] = {
                    'count': missing,
                    'pct': round(pct, 2),
                }
                if pct > MISSING_FIELD_WARN_PCT:
                    logger.warning(f"Missing {label}: {missing} listings ({pct:.1f}%)")
                    if results['status'] != 'alert':
                        results['status'] = 'warning'
                else:
                    logger.info(f"Missing {label}: {missing} listings ({pct:.1f}%)")

        results['checks']['missing_fields'] = missing_fields

        # Listings with no mls_number (should never happen)
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM listings "
            "WHERE mls_source = ? AND (mls_number IS NULL OR mls_number = '')",
            (MLS_SOURCE,)
        ).fetchone()
        if row['cnt'] > 0:
            logger.warning(f"Listings with no MLS number: {row['cnt']}")
            results['status'] = 'alert'
        results['checks']['missing_mls_number'] = row['cnt']

    finally:
        conn.close()

    _save_result('monthly', results)
    return results


def run_all_checks(client: MLSGridClient = None) -> dict:
    """Run all reconciliation tiers."""
    if client is None:
        client = MLSGridClient.from_env()

    daily = run_daily_count_check(client)
    weekly = run_weekly_status_check(client)
    monthly = run_monthly_completeness_audit()

    overall_status = 'ok'
    for r in [daily, weekly, monthly]:
        if r['status'] == 'alert':
            overall_status = 'alert'
            break
        if r['status'] == 'warning' and overall_status != 'alert':
            overall_status = 'warning'

    return {
        'daily': daily,
        'weekly': weekly,
        'monthly': monthly,
        'overall_status': overall_status,
        'total_api_requests': daily['api_requests_used'] + weekly['api_requests_used'],
    }


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


def main():
    parser = argparse.ArgumentParser(description="MLS Grid Data Reconciliation")
    parser.add_argument('--daily', action='store_true', help='Run daily count check (1 API request)')
    parser.add_argument('--weekly', action='store_true', help='Run weekly status check (3 API requests)')
    parser.add_argument('--monthly', action='store_true', help='Run monthly completeness audit (0 API requests)')
    parser.add_argument('--all', action='store_true', help='Run all checks')

    args = parser.parse_args()

    load_env()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    if args.all:
        results = run_all_checks()
    elif args.daily:
        results = run_daily_count_check()
    elif args.weekly:
        results = run_weekly_status_check()
    elif args.monthly:
        results = run_monthly_completeness_audit()
    else:
        parser.print_help()
        return 1

    print(json.dumps(results, indent=2))
    return 0 if results.get('status', results.get('overall_status')) == 'ok' else 1


if __name__ == '__main__':
    sys.exit(main())
