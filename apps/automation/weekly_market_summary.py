"""
Weekly Market Summary

Generates and sends a weekly market report every Monday morning.
Compares current week statistics to the previous week.

Cron: 30 6 * * 1 (Monday 6:30 AM)
"""

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from statistics import median

from apps.automation import config
from apps.automation.config import get_db_setting
from apps.automation.email_service import send_template_email

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL))
logger = logging.getLogger(__name__)


def get_db_connection():
    """Get database connection."""
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def capture_market_snapshot(snapshot_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Capture current market state and store in market_snapshots table.

    Args:
        snapshot_date: Date to capture (YYYY-MM-DD). Defaults to today.

    Returns:
        Dictionary with overall and per-county statistics
    """
    if snapshot_date is None:
        snapshot_date = datetime.now().strftime('%Y-%m-%d')

    conn = get_db_connection()
    results = {'overall': None, 'by_county': {}}

    try:
        # Calculate date range for "new listings" (last 7 days)
        week_ago = (datetime.strptime(snapshot_date, '%Y-%m-%d') - timedelta(days=7)).strftime('%Y-%m-%d')

        # Overall statistics (from listings table)
        overall = conn.execute('''
            SELECT
                COUNT(*) FILTER (WHERE LOWER(status) = 'active') as total_active,
                COUNT(*) FILTER (WHERE LOWER(status) = 'active' AND captured_at >= ?) as new_listings,
                AVG(list_price) FILTER (WHERE LOWER(status) = 'active') as avg_price,
                AVG(days_on_market) FILTER (WHERE LOWER(status) = 'active') as avg_dom,
                COUNT(*) FILTER (WHERE LOWER(status) = 'pending') as pending_count,
                COUNT(*) FILTER (WHERE LOWER(status) = 'sold' AND updated_at >= ?) as sold_count
            FROM listings
            WHERE county IN ({})
        '''.format(','.join(['?' for _ in config.TRACKED_COUNTIES])),
            [week_ago, week_ago] + config.TRACKED_COUNTIES
        ).fetchone()

        # Get all active prices for median calculation
        prices = conn.execute('''
            SELECT list_price as price FROM listings
            WHERE LOWER(status) = 'active' AND list_price IS NOT NULL
            AND county IN ({})
        '''.format(','.join(['?' for _ in config.TRACKED_COUNTIES])),
            config.TRACKED_COUNTIES
        ).fetchall()

        median_price = median([p['price'] for p in prices]) if prices else None

        # Price reductions not tracked until Navica change detection is active
        price_reduced = 0

        # Store overall snapshot
        conn.execute('''
            INSERT INTO market_snapshots
            (snapshot_date, county, total_active, new_listings, avg_price, median_price,
             avg_dom, pending_count, sold_count, price_reduced_count)
            VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(snapshot_date, county) DO UPDATE SET
            total_active = excluded.total_active,
            new_listings = excluded.new_listings,
            avg_price = excluded.avg_price,
            median_price = excluded.median_price,
            avg_dom = excluded.avg_dom,
            pending_count = excluded.pending_count,
            sold_count = excluded.sold_count,
            price_reduced_count = excluded.price_reduced_count
        ''', [
            snapshot_date,
            overall['total_active'] or 0,
            overall['new_listings'] or 0,
            int(overall['avg_price']) if overall['avg_price'] else None,
            int(median_price) if median_price else None,
            round(overall['avg_dom'], 1) if overall['avg_dom'] else None,
            overall['pending_count'] or 0,
            overall['sold_count'] or 0,
            price_reduced
        ])

        results['overall'] = {
            'snapshot_date': snapshot_date,
            'total_active': overall['total_active'] or 0,
            'new_listings': overall['new_listings'] or 0,
            'avg_price': int(overall['avg_price']) if overall['avg_price'] else 0,
            'median_price': int(median_price) if median_price else 0,
            'avg_dom': round(overall['avg_dom'], 1) if overall['avg_dom'] else 0,
            'pending_count': overall['pending_count'] or 0,
            'sold_count': overall['sold_count'] or 0,
            'price_reduced_count': price_reduced
        }

        # Per-county statistics
        for county in config.TRACKED_COUNTIES:
            county_stats = conn.execute('''
                SELECT
                    COUNT(*) FILTER (WHERE LOWER(status) = 'active') as total_active,
                    COUNT(*) FILTER (WHERE LOWER(status) = 'active' AND captured_at >= ?) as new_listings,
                    AVG(list_price) FILTER (WHERE LOWER(status) = 'active') as avg_price,
                    AVG(days_on_market) FILTER (WHERE LOWER(status) = 'active') as avg_dom,
                    COUNT(*) FILTER (WHERE LOWER(status) = 'pending') as pending_count
                FROM listings
                WHERE county = ?
            ''', [week_ago, county]).fetchone()

            if county_stats['total_active'] and county_stats['total_active'] > 0:
                # Store county snapshot
                conn.execute('''
                    INSERT INTO market_snapshots
                    (snapshot_date, county, total_active, new_listings, avg_price, avg_dom, pending_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(snapshot_date, county) DO UPDATE SET
                    total_active = excluded.total_active,
                    new_listings = excluded.new_listings,
                    avg_price = excluded.avg_price,
                    avg_dom = excluded.avg_dom,
                    pending_count = excluded.pending_count
                ''', [
                    snapshot_date, county,
                    county_stats['total_active'],
                    county_stats['new_listings'] or 0,
                    int(county_stats['avg_price']) if county_stats['avg_price'] else None,
                    round(county_stats['avg_dom'], 1) if county_stats['avg_dom'] else None,
                    county_stats['pending_count'] or 0
                ])

                results['by_county'][county] = {
                    'total_active': county_stats['total_active'],
                    'new_listings': county_stats['new_listings'] or 0,
                    'avg_price': int(county_stats['avg_price']) if county_stats['avg_price'] else 0,
                    'avg_dom': round(county_stats['avg_dom'], 1) if county_stats['avg_dom'] else 0,
                    'pending_count': county_stats['pending_count'] or 0
                }

        conn.commit()
        logger.info(f"Captured market snapshot for {snapshot_date}")

    finally:
        conn.close()

    return results


def get_previous_snapshot(current_date: str) -> Optional[Dict[str, Any]]:
    """Get the snapshot from the previous week."""
    prev_date = (datetime.strptime(current_date, '%Y-%m-%d') - timedelta(days=7)).strftime('%Y-%m-%d')

    conn = get_db_connection()
    try:
        # Get overall snapshot
        overall = conn.execute('''
            SELECT * FROM market_snapshots
            WHERE snapshot_date = ? AND county IS NULL
        ''', [prev_date]).fetchone()

        if not overall:
            return None

        result = {
            'overall': dict(overall),
            'by_county': {}
        }

        # Get county snapshots
        counties = conn.execute('''
            SELECT * FROM market_snapshots
            WHERE snapshot_date = ? AND county IS NOT NULL
        ''', [prev_date]).fetchall()

        for county in counties:
            result['by_county'][county['county']] = dict(county)

        return result

    finally:
        conn.close()


def generate_weekly_summary() -> Dict[str, Any]:
    """
    Generate weekly summary by comparing current snapshot to previous week.

    Returns:
        Dictionary with all data needed for the email template
    """
    today = datetime.now().strftime('%Y-%m-%d')

    # Capture current state
    current = capture_market_snapshot(today)

    # Get previous week's snapshot
    previous = get_previous_snapshot(today)

    # Calculate deltas
    metrics = current['overall'].copy()

    if previous and previous['overall']:
        prev = previous['overall']
        metrics['active_delta'] = metrics['total_active'] - (prev.get('total_active') or 0)
        metrics['new_delta'] = metrics['new_listings'] - (prev.get('new_listings') or 0)

        if prev.get('avg_price') and metrics['avg_price']:
            metrics['price_delta_pct'] = ((metrics['avg_price'] - prev['avg_price']) / prev['avg_price']) * 100
        else:
            metrics['price_delta_pct'] = 0

        if prev.get('avg_dom') is not None and metrics['avg_dom']:
            metrics['dom_delta'] = round(metrics['avg_dom'] - prev['avg_dom'], 1)
        else:
            metrics['dom_delta'] = 0
    else:
        metrics['active_delta'] = 0
        metrics['new_delta'] = 0
        metrics['price_delta_pct'] = 0
        metrics['dom_delta'] = 0

    # Rename for template
    metrics['price_reduced'] = metrics.get('price_reduced_count', 0)
    metrics['back_on_market'] = 0  # Would need status tracking to calculate

    # Build county breakdown
    county_breakdown = []
    for county_name, county_data in current['by_county'].items():
        county_breakdown.append({
            'name': county_name,
            'active': county_data['total_active'],
            'new': county_data['new_listings'],
            'avg_price': county_data['avg_price'],
            'avg_dom': county_data['avg_dom']
        })

    # Sort by active listings descending
    county_breakdown.sort(key=lambda x: x['active'], reverse=True)

    # Generate key insights
    key_insights = []

    if metrics['active_delta'] > 0:
        key_insights.append(f"Inventory up: {metrics['active_delta']} more active listings than last week")
    elif metrics['active_delta'] < 0:
        key_insights.append(f"Inventory down: {abs(metrics['active_delta'])} fewer listings than last week")

    if metrics['price_delta_pct'] > 2:
        key_insights.append(f"Prices rising: Average price up {metrics['price_delta_pct']:.1f}% from last week")
    elif metrics['price_delta_pct'] < -2:
        key_insights.append(f"Prices softening: Average price down {abs(metrics['price_delta_pct']):.1f}% from last week")

    if metrics['pending_count'] > 0:
        key_insights.append(f"{metrics['pending_count']} properties went under contract this week")

    if metrics['price_reduced'] > 5:
        key_insights.append(f"{metrics['price_reduced']} price reductions - possible buying opportunities")

    if not key_insights:
        key_insights.append("Market conditions remain stable week-over-week")

    # Get notable listings (new this week with interesting attributes)
    conn = get_db_connection()
    try:
        week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        notable = conn.execute('''
            SELECT address, city, list_price as price, beds, baths, acreage, views
            FROM listings
            WHERE LOWER(status) = 'active'
            AND captured_at >= ?
            AND county IN ({})
            ORDER BY list_price DESC
            LIMIT 5
        '''.format(','.join(['?' for _ in config.TRACKED_COUNTIES])),
            [week_ago] + config.TRACKED_COUNTIES
        ).fetchall()

        notable_listings = []
        for prop in notable:
            note_parts = []
            if prop['acreage'] and prop['acreage'] > 5:
                note_parts.append(f"{prop['acreage']} acres")
            if prop['views']:
                note_parts.append(prop['views'])

            notable_listings.append({
                'address': f"{prop['address']}, {prop['city']}",
                'price': prop['price'],
                'beds': prop['beds'],
                'baths': prop['baths'],
                'note': ', '.join(note_parts) if note_parts else 'New listing'
            })
    finally:
        conn.close()

    return {
        'report_date': datetime.now().strftime('%B %d, %Y'),
        'metrics': metrics,
        'county_breakdown': county_breakdown,
        'key_insights': key_insights,
        'notable_listings': notable_listings,
        'agent_name': config.AGENT_NAME,
        'agent_email': config.AGENT_EMAIL,
        'agent_phone': config.AGENT_PHONE,
        'brokerage_name': config.BROKERAGE_NAME
    }


def send_weekly_summary() -> bool:
    """
    Generate and send the weekly market summary email.

    Returns:
        True if sent successfully, False otherwise
    """
    logger.info("Generating weekly market summary...")

    # Check if alerts are enabled
    if not get_db_setting('alerts_global_enabled', True):
        logger.info("Global alerts are disabled - exiting")
        return True  # Return True so cron doesn't error

    if not get_db_setting('weekly_summary_enabled', True):
        logger.info("Weekly summary is disabled - exiting")
        return True

    try:
        summary_data = generate_weekly_summary()

        subject = f"Weekly Market Summary - {summary_data['report_date']}"

        success = send_template_email(
            to=config.WEEKLY_SUMMARY_RECIPIENT,
            subject=subject,
            template_name='weekly_summary.html',
            context=summary_data,
            from_name='DREAMS Market Reports'
        )

        if success:
            logger.info(f"Weekly summary sent to {config.WEEKLY_SUMMARY_RECIPIENT}")
        else:
            logger.error("Failed to send weekly summary email")

        return success

    except Exception as e:
        logger.error(f"Error generating weekly summary: {e}")
        return False


def main():
    """Entry point for cron job."""
    import sys

    # Check if we should just capture snapshot (daily)
    if len(sys.argv) > 1 and sys.argv[1] == '--snapshot-only':
        capture_market_snapshot()
        logger.info("Snapshot captured (no email sent)")
        return

    # Full weekly summary
    success = send_weekly_summary()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
