"""
Saved Search Email Alerts

Sends matching listings to buyers who have saved searches with alerts enabled.

Frequencies:
- daily: Sent once per day (8 AM cron)
- weekly: Sent once per week (Monday 8 AM cron)
- never: No alerts

Usage:
    # Daily alerts
    python3 -m apps.automation.saved_search_alerts --daily

    # Weekly alerts
    python3 -m apps.automation.saved_search_alerts --weekly
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from apps.automation import config
from apps.automation.email_service import send_template_email

logger = logging.getLogger(__name__)

WEBSITE_URL = os.getenv('PUBLIC_SITE_URL', 'https://wncmountain.homes')

# Allowed filter keys (whitelist to prevent SQL injection)
ALLOWED_FILTER_KEYS = {
    'status', 'city', 'county', 'min_price', 'max_price',
    'min_beds', 'min_baths', 'min_sqft', 'min_acreage',
    'max_dom', 'property_type', 'mls_source', 'q',
}


def _get_db():
    """Get a database connection."""
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def get_due_searches(frequency: str) -> list[dict]:
    """Get saved searches that are due for alerts.

    Args:
        frequency: 'daily' or 'weekly'

    Returns:
        List of saved search dicts with user info joined
    """
    db = _get_db()

    if frequency == 'daily':
        interval_hours = 23  # slight buffer so cron drift doesn't skip a day
    elif frequency == 'weekly':
        interval_hours = 167  # ~7 days minus a small buffer
    else:
        db.close()
        return []

    cutoff = (datetime.now() - timedelta(hours=interval_hours)).isoformat()

    rows = db.execute('''
        SELECT ss.*, u.name as user_name, u.email as user_email
        FROM saved_searches ss
        LEFT JOIN users u ON u.id = ss.user_id
        WHERE ss.alert_frequency = ?
          AND (ss.last_alerted_at IS NULL OR ss.last_alerted_at < ?)
    ''', [frequency, cutoff]).fetchall()

    db.close()
    return [dict(r) for r in rows]


def match_search_to_listings(filters: dict, since: str | None = None, limit: int = 20) -> list[dict]:
    """Find listings matching saved search filters.

    Builds a SQL query from the saved search filter dict, using the same
    logic as the public API's build_listing_filters().

    Args:
        filters: Dict of filter key/value pairs (from filters_json)
        since: ISO timestamp; only return listings added/updated after this time
        limit: Max listings to return

    Returns:
        List of listing dicts
    """
    conditions = ["idx_opt_in = 1"]
    params = []

    status = filters.get('status', 'ACTIVE')
    if status:
        conditions.append("UPPER(status) = UPPER(?)")
        params.append(status)

    city = filters.get('city')
    if city:
        conditions.append("LOWER(city) = LOWER(?)")
        params.append(city)

    county = filters.get('county')
    if county:
        conditions.append("LOWER(county) = LOWER(?)")
        params.append(county)

    min_price = filters.get('min_price')
    if min_price is not None:
        try:
            conditions.append("list_price >= ?")
            params.append(int(min_price))
        except (ValueError, TypeError):
            pass

    max_price = filters.get('max_price')
    if max_price is not None:
        try:
            conditions.append("list_price <= ?")
            params.append(int(max_price))
        except (ValueError, TypeError):
            pass

    min_beds = filters.get('min_beds')
    if min_beds is not None:
        try:
            conditions.append("beds >= ?")
            params.append(int(min_beds))
        except (ValueError, TypeError):
            pass

    min_baths = filters.get('min_baths')
    if min_baths is not None:
        try:
            conditions.append("baths >= ?")
            params.append(float(min_baths))
        except (ValueError, TypeError):
            pass

    min_sqft = filters.get('min_sqft')
    if min_sqft is not None:
        try:
            conditions.append("sqft >= ?")
            params.append(int(min_sqft))
        except (ValueError, TypeError):
            pass

    min_acreage = filters.get('min_acreage')
    if min_acreage is not None:
        try:
            conditions.append("acreage >= ?")
            params.append(float(min_acreage))
        except (ValueError, TypeError):
            pass

    property_type = filters.get('property_type')
    if property_type:
        conditions.append("property_type = ?")
        params.append(property_type)

    q = filters.get('q')
    if q:
        search_term = f"%{q}%"
        conditions.append(
            "(address LIKE ? OR city LIKE ? OR county LIKE ? "
            "OR subdivision LIKE ? OR public_remarks LIKE ? OR mls_number LIKE ?)"
        )
        params.extend([search_term] * 6)

    # Only include listings added or updated since last alert
    if since:
        conditions.append("(created_at > ? OR updated_at > ?)")
        params.extend([since, since])

    where = " AND ".join(conditions)
    sql = f"""
        SELECT id, address, city, state, county, list_price, beds, baths,
               sqft, acreage, primary_photo, mls_number, property_type,
               days_on_market, status
        FROM listings
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT ?
    """
    params.append(limit)

    db = _get_db()
    rows = db.execute(sql, params).fetchall()
    db.close()
    return [dict(r) for r in rows]


def send_search_alert(user_email: str, user_name: str, search: dict, listings: list[dict]) -> bool:
    """Send a saved search alert email to a buyer.

    Args:
        user_email: Buyer's email
        user_name: Buyer's display name
        search: Saved search dict
        listings: Matching listings

    Returns:
        True if sent successfully
    """
    if not user_email:
        logger.warning(f"No email for saved search {search['id']}, skipping")
        return False

    filters = {}
    try:
        filters = json.loads(search.get('filters_json') or '{}')
    except (json.JSONDecodeError, TypeError):
        pass

    # Build a human-readable filter summary
    filter_parts = []
    if filters.get('city'):
        filter_parts.append(filters['city'])
    if filters.get('county'):
        filter_parts.append(f"{filters['county']} County")
    if filters.get('min_price') or filters.get('max_price'):
        price_range = []
        if filters.get('min_price'):
            price_range.append(f"${int(filters['min_price']):,}+")
        if filters.get('max_price'):
            price_range.append(f"up to ${int(filters['max_price']):,}")
        filter_parts.append(' '.join(price_range))
    if filters.get('min_beds'):
        filter_parts.append(f"{filters['min_beds']}+ beds")

    filter_summary = ', '.join(filter_parts) if filter_parts else 'All areas'

    subject = f"{len(listings)} new {'listing' if len(listings) == 1 else 'listings'} matching \"{search['name']}\""

    return send_template_email(
        to=user_email,
        subject=subject,
        template_name='saved_search_alert.html',
        context={
            'buyer_name': user_name or 'there',
            'search_name': search['name'],
            'filter_summary': filter_summary,
            'listing_count': len(listings),
            'listings': listings,
            'website_url': WEBSITE_URL,
            'manage_url': f"{WEBSITE_URL}/account/searches",
            'agent_name': config.AGENT_NAME,
            'agent_phone': config.AGENT_PHONE,
            'agent_email': config.AGENT_EMAIL,
            'brokerage': config.BROKERAGE_NAME,
        },
    )


def process_alerts(frequency: str) -> int:
    """Process all due saved search alerts for a given frequency.

    Args:
        frequency: 'daily' or 'weekly'

    Returns:
        Number of alerts sent
    """
    searches = get_due_searches(frequency)
    if not searches:
        logger.info(f"No {frequency} saved searches due for alerts")
        return 0

    logger.info(f"Processing {len(searches)} {frequency} saved search alerts")
    sent_count = 0

    for search in searches:
        try:
            filters = {}
            try:
                filters = json.loads(search.get('filters_json') or '{}')
            except (json.JSONDecodeError, TypeError):
                pass

            # Use last_alerted_at as the "since" cutoff, or created_at as fallback
            since = search.get('last_alerted_at') or search.get('created_at')

            listings = match_search_to_listings(filters, since=since)

            if not listings:
                logger.debug(f"No new matches for search '{search['name']}' (id={search['id']})")
                # Still update last_alerted_at so we don't re-check the same window
                db = _get_db()
                db.execute(
                    'UPDATE saved_searches SET last_alerted_at = ? WHERE id = ?',
                    [datetime.now().isoformat(), search['id']]
                )
                db.commit()
                db.close()
                continue

            user_email = search.get('user_email')
            user_name = search.get('user_name')

            sent = send_search_alert(user_email, user_name, search, listings)

            if sent:
                sent_count += 1
                db = _get_db()
                db.execute(
                    'UPDATE saved_searches SET last_alerted_at = ? WHERE id = ?',
                    [datetime.now().isoformat(), search['id']]
                )
                db.commit()
                db.close()
                logger.info(f"Sent alert for '{search['name']}' to {user_email}: {len(listings)} listings")
            else:
                logger.warning(f"Failed to send alert for search '{search['name']}' to {user_email}")

        except Exception as e:
            logger.error(f"Error processing search '{search.get('name', '?')}': {e}")

    return sent_count


def main():
    """Entry point for cron job."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )

    parser = argparse.ArgumentParser(description='Send saved search email alerts')
    parser.add_argument('--daily', action='store_true', help='Process daily alerts')
    parser.add_argument('--weekly', action='store_true', help='Process weekly alerts')
    args = parser.parse_args()

    if not args.daily and not args.weekly:
        logger.error("Specify --daily or --weekly")
        sys.exit(1)

    total = 0
    if args.daily:
        logger.info("Processing daily saved search alerts...")
        total += process_alerts('daily')

    if args.weekly:
        logger.info("Processing weekly saved search alerts...")
        total += process_alerts('weekly')

    logger.info(f"Done. Sent {total} alert(s).")


if __name__ == '__main__':
    main()
