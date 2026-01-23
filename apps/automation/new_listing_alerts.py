"""
New Listing Alerts

Daily digest emails to buyers when matching properties hit the market.
Uses contact_requirements for matching criteria.

Cron: 0 8 * * * (Daily 8:00 AM)
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

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


def get_new_listings(hours: int = 24) -> List[Dict[str, Any]]:
    """
    Get properties added in the last N hours.

    Args:
        hours: Look back period in hours

    Returns:
        List of new property dictionaries
    """
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    conn = get_db_connection()

    try:
        listings = conn.execute('''
            SELECT
                id, mls_number, address, city, state, zip, county,
                price, beds, baths, sqft, acreage,
                property_type, status, views, water_features,
                photo_urls, zillow_url, redfin_url, idx_url,
                created_at
            FROM properties
            WHERE status = 'active'
            AND created_at >= ?
            AND county IN ({})
        '''.format(','.join(['?' for _ in config.TRACKED_COUNTIES])),
            [cutoff] + config.TRACKED_COUNTIES
        ).fetchall()

        results = []
        for listing in listings:
            prop = dict(listing)

            # Parse photo_urls JSON
            if prop.get('photo_urls'):
                try:
                    photos = json.loads(prop['photo_urls'])
                    prop['photo_url'] = photos[0] if photos else None
                except json.JSONDecodeError:
                    prop['photo_url'] = None
            else:
                prop['photo_url'] = None

            # Determine best listing URL
            prop['listing_url'] = prop.get('idx_url') or prop.get('zillow_url') or prop.get('redfin_url')

            results.append(prop)

        logger.info(f"Found {len(results)} new listings in last {hours} hours")
        return results

    finally:
        conn.close()


def get_active_buyers() -> List[Dict[str, Any]]:
    """
    Get all active buyer contacts with their requirements.

    Returns:
        List of buyer dictionaries with consolidated requirements
    """
    conn = get_db_connection()

    try:
        buyers = conn.execute('''
            SELECT
                l.id,
                l.first_name,
                l.last_name,
                l.email,
                l.heat_score,
                cr.price_min,
                cr.price_max,
                cr.beds_min,
                cr.baths_min,
                cr.sqft_min,
                cr.acreage_min,
                cr.counties,
                cr.cities,
                cr.property_types,
                cr.must_have_features,
                cr.views_required,
                cr.water_features,
                cr.overall_confidence
            FROM leads l
            LEFT JOIN contact_requirements cr ON cr.contact_id = l.id
            LEFT JOIN contact_workflow cw ON cw.contact_id = l.id
            WHERE l.type = 'buyer'
            AND l.email IS NOT NULL
            AND l.email != ''
            AND COALESCE(cw.workflow_status, 'active') = 'active'
            AND COALESCE(cw.current_stage, l.stage) NOT IN ('closed', 'lost')
        ''').fetchall()

        results = []
        for buyer in buyers:
            b = dict(buyer)

            # Parse JSON fields
            for field in ['counties', 'cities', 'property_types', 'must_have_features', 'views_required', 'water_features']:
                if b.get(field):
                    try:
                        b[field] = json.loads(b[field])
                    except json.JSONDecodeError:
                        b[field] = []
                else:
                    b[field] = []

            results.append(b)

        logger.info(f"Found {len(results)} active buyers with requirements")
        return results

    finally:
        conn.close()


def calculate_match_score(property: Dict[str, Any], buyer: Dict[str, Any]) -> Tuple[int, List[str]]:
    """
    Calculate how well a property matches a buyer's requirements.

    Args:
        property: Property dictionary
        buyer: Buyer dictionary with requirements

    Returns:
        Tuple of (match_score, list of matching criteria)
    """
    score = 0
    max_score = 0
    matching_criteria = []

    # Price match (30 points)
    max_score += 30
    if buyer.get('price_min') or buyer.get('price_max'):
        price = property.get('price', 0)
        price_min = buyer.get('price_min') or 0
        price_max = buyer.get('price_max') or float('inf')

        if price_min <= price <= price_max:
            score += 30
            matching_criteria.append('Price in range')
        elif price < price_min * 0.9:
            score += 15  # Under budget is okay
            matching_criteria.append('Under budget')
        elif price <= price_max * 1.1:
            score += 10  # Slightly over is acceptable
    else:
        score += 15  # No price requirement, give partial credit

    # Beds match (20 points)
    max_score += 20
    if buyer.get('beds_min'):
        if property.get('beds', 0) >= buyer['beds_min']:
            score += 20
            matching_criteria.append(f"{property['beds']}+ beds")
        elif property.get('beds', 0) == buyer['beds_min'] - 1:
            score += 10  # One less bed might work
    else:
        score += 10  # No requirement

    # Baths match (10 points)
    max_score += 10
    if buyer.get('baths_min'):
        if property.get('baths', 0) >= buyer['baths_min']:
            score += 10
            matching_criteria.append(f"{property['baths']}+ baths")
    else:
        score += 5

    # Location match (20 points)
    max_score += 20
    property_county = property.get('county', '').lower()
    property_city = property.get('city', '').lower()

    buyer_counties = [c.lower() for c in buyer.get('counties', [])]
    buyer_cities = [c.lower() for c in buyer.get('cities', [])]

    if buyer_counties or buyer_cities:
        if property_county in buyer_counties:
            score += 20
            matching_criteria.append(f"{property.get('county')} county")
        elif property_city in buyer_cities:
            score += 20
            matching_criteria.append(f"{property.get('city')}")
        elif not buyer_counties and not buyer_cities:
            score += 10  # No location requirement
    else:
        score += 10

    # Size match (10 points)
    max_score += 10
    if buyer.get('sqft_min'):
        if property.get('sqft', 0) >= buyer['sqft_min']:
            score += 10
            matching_criteria.append(f"{property['sqft']:,} sqft")
    else:
        score += 5

    # Acreage match (10 points)
    max_score += 10
    if buyer.get('acreage_min'):
        if property.get('acreage', 0) >= buyer['acreage_min']:
            score += 10
            matching_criteria.append(f"{property['acreage']} acres")
    else:
        score += 5

    # Views bonus (optional but nice)
    buyer_views = buyer.get('views_required', [])
    property_views = property.get('views', '') or ''
    if buyer_views and property_views:
        for view in buyer_views:
            if view.lower() in property_views.lower():
                matching_criteria.append(f"{view} views")
                break

    # Water features bonus
    buyer_water = buyer.get('water_features', [])
    property_water = property.get('water_features', '') or ''
    if buyer_water and property_water:
        for water in buyer_water:
            if water.lower() in property_water.lower():
                matching_criteria.append(f"{water}")
                break

    # Normalize to 0-100
    final_score = int((score / max_score) * 100) if max_score > 0 else 0

    return final_score, matching_criteria


def check_already_alerted(contact_id: str, property_id: str) -> bool:
    """Check if we've already sent an alert for this property to this contact."""
    conn = get_db_connection()

    try:
        existing = conn.execute('''
            SELECT id FROM alert_log
            WHERE alert_type = 'new_listing'
            AND contact_id = ?
            AND property_id = ?
        ''', [contact_id, property_id]).fetchone()

        return existing is not None

    finally:
        conn.close()


def log_alert(alert_type: str, contact_id: str, property_id: str, email_to: str,
              status: str = 'sent', error_message: str = None) -> None:
    """Log an alert to prevent future duplicates."""
    conn = get_db_connection()

    try:
        conn.execute('''
            INSERT INTO alert_log (alert_type, contact_id, property_id, email_to, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(alert_type, contact_id, property_id) DO UPDATE SET
            sent_at = CURRENT_TIMESTAMP,
            status = excluded.status,
            error_message = excluded.error_message
        ''', [alert_type, contact_id, property_id, email_to, status, error_message])
        conn.commit()
    finally:
        conn.close()


def match_listings_to_buyers(listings: List[Dict], buyers: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Match new listings to buyers based on requirements.

    Returns:
        Dictionary mapping contact_id to list of matching properties
    """
    matches = {}

    # Get threshold from database settings
    match_threshold = get_db_setting('new_listing_match_threshold', 60)
    logger.info(f"Using match threshold: {match_threshold}")

    for buyer in buyers:
        buyer_matches = []

        for listing in listings:
            # Skip if already alerted
            if check_already_alerted(buyer['id'], listing['id']):
                continue

            score, criteria = calculate_match_score(listing, buyer)

            if score >= match_threshold:
                match = listing.copy()
                match['match_score'] = score
                match['matching_features'] = ', '.join(criteria)
                match['is_price_drop'] = False  # Could enhance to detect
                buyer_matches.append(match)

        if buyer_matches:
            # Sort by match score descending
            buyer_matches.sort(key=lambda x: x['match_score'], reverse=True)
            matches[buyer['id']] = {
                'buyer': buyer,
                'properties': buyer_matches
            }

    return matches


def build_criteria_summary(buyer: Dict) -> str:
    """Build a human-readable summary of buyer's criteria."""
    parts = []

    if buyer.get('price_min') or buyer.get('price_max'):
        price_min = buyer.get('price_min', 0)
        price_max = buyer.get('price_max')
        if price_max:
            parts.append(f"${price_min:,}-${price_max:,}")
        else:
            parts.append(f"${price_min:,}+")

    if buyer.get('beds_min'):
        parts.append(f"{buyer['beds_min']}+ beds")

    if buyer.get('counties'):
        parts.append(', '.join(buyer['counties'][:2]))

    return ' | '.join(parts) if parts else 'Open criteria'


def send_listing_alerts() -> Dict[str, int]:
    """
    Main function to send new listing alerts to matching buyers.

    Returns:
        Dictionary with counts of emails sent, skipped, failed
    """
    logger.info("Starting new listing alerts...")

    stats = {'sent': 0, 'skipped': 0, 'failed': 0, 'properties_matched': 0}

    # Check if alerts are enabled
    if not get_db_setting('alerts_global_enabled', True):
        logger.info("Global alerts are disabled - exiting")
        return stats

    if not get_db_setting('new_listing_alerts_enabled', True):
        logger.info("New listing alerts are disabled - exiting")
        return stats

    # Get lookback hours from settings
    lookback_hours = get_db_setting('alert_lookback_hours', 24)
    logger.info(f"Looking back {lookback_hours} hours for new listings")

    # Get new listings
    listings = get_new_listings(lookback_hours)

    if not listings:
        logger.info("No new listings found")
        return stats

    # Get active buyers
    buyers = get_active_buyers()

    if not buyers:
        logger.info("No active buyers found")
        return stats

    # Match listings to buyers
    matches = match_listings_to_buyers(listings, buyers)

    logger.info(f"Found matches for {len(matches)} buyers")

    # Send emails to each buyer with matches
    for contact_id, match_data in matches.items():
        buyer = match_data['buyer']
        properties = match_data['properties']

        if not buyer.get('email'):
            stats['skipped'] += 1
            continue

        # Get max properties per alert from settings
        max_properties = get_db_setting('max_properties_per_alert', 10)

        # Prepare template context
        context = {
            'contact_name': f"{buyer['first_name']}",
            'property_count': len(properties),
            'properties': properties[:max_properties],  # Limit per settings
            'criteria_summary': build_criteria_summary(buyer),
            'alert_date': datetime.now().strftime('%B %d, %Y'),
            'agent_name': config.AGENT_NAME,
            'agent_email': config.AGENT_EMAIL,
            'agent_phone': config.AGENT_PHONE,
            'agent_headshot': config.AGENT_HEADSHOT_URL,
            'brokerage_name': config.BROKERAGE_NAME
        }

        # Build subject line
        if len(properties) == 1:
            subject = f"New Listing Alert: {properties[0]['address']}"
        else:
            subject = f"New Listings: {len(properties)} properties match your criteria"

        # Send email
        success = send_template_email(
            to=buyer['email'],
            subject=subject,
            template_name='listing_alert.html',
            context=context,
            from_name=config.AGENT_NAME
        )

        if success:
            stats['sent'] += 1
            stats['properties_matched'] += len(properties)

            # Log all alerts to prevent duplicates
            for prop in properties:
                log_alert('new_listing', contact_id, prop['id'], buyer['email'])

            logger.info(f"Sent {len(properties)} listing alerts to {buyer['email']}")
        else:
            stats['failed'] += 1

            # Log as failed
            for prop in properties:
                log_alert('new_listing', contact_id, prop['id'], buyer['email'],
                         status='failed', error_message='Email send failed')

            logger.error(f"Failed to send alerts to {buyer['email']}")

    logger.info(f"Listing alerts complete: {stats}")
    return stats


def main():
    """Entry point for cron job."""
    import sys

    stats = send_listing_alerts()

    # Exit with error if all sends failed
    if stats['failed'] > 0 and stats['sent'] == 0:
        sys.exit(1)

    sys.exit(0)


if __name__ == '__main__':
    main()
