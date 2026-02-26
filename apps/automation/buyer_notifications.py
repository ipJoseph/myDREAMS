"""
Buyer Activity Notifications

Handles two types of agent notifications:
1. Immediate: Showing request alerts (called from API endpoint)
2. Daily digest: Summary of all buyer actions (run via cron)

Usage:
    # Immediate (called from user.py on showing request)
    from apps.automation.buyer_notifications import send_showing_request_alert
    send_showing_request_alert(user_id, collection_id)

    # Daily digest (cron job)
    python3 -m apps.automation.buyer_notifications
"""

import json
import logging
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from apps.automation import config
from apps.automation.email_service import send_template_email

logger = logging.getLogger(__name__)

DASHBOARD_URL = os.getenv('DASHBOARD_URL', 'https://app.wncmountain.homes')


def _get_db():
    """Get a database connection."""
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def send_showing_request_alert(user_id: str, collection_id: str) -> bool:
    """Send an immediate email to the agent when a buyer requests showings.

    Args:
        user_id: The public website user ID
        collection_id: The collection (property_packages) ID

    Returns:
        True if email sent successfully
    """
    try:
        db = _get_db()

        # Get buyer info
        user = db.execute(
            'SELECT name, email FROM users WHERE id = ?', [user_id]
        ).fetchone()

        # Get collection info
        collection = db.execute(
            'SELECT name, showing_requested_at FROM property_packages WHERE id = ?',
            [collection_id]
        ).fetchone()

        if not user or not collection:
            logger.warning(f"Missing user or collection for showing alert: user={user_id}, collection={collection_id}")
            db.close()
            return False

        # Get properties in collection
        properties = db.execute(
            '''SELECT l.address, l.city, l.state, l.list_price, l.beds, l.baths,
                      l.sqft, l.primary_photo, l.mls_number
               FROM package_properties pp
               JOIN listings l ON l.id = pp.listing_id
               WHERE pp.package_id = ?
               ORDER BY pp.display_order, pp.added_at''',
            [collection_id]
        ).fetchall()

        db.close()

        prop_list = [dict(p) for p in properties]
        buyer_name = user['name'] or user['email'] or 'Unknown Buyer'

        subject = f"Showing Request: {buyer_name} wants to see {len(prop_list)} {'property' if len(prop_list) == 1 else 'properties'}"

        recipient = os.getenv('AGENT_EMAIL', config.SMTP_USERNAME)
        if not recipient:
            logger.warning("No agent email configured for showing request alert")
            return False

        return send_template_email(
            to=recipient,
            subject=subject,
            template_name='showing_request_alert.html',
            context={
                'buyer_name': buyer_name,
                'buyer_email': user['email'],
                'collection_name': collection['name'],
                'property_count': len(prop_list),
                'properties': prop_list,
                'requested_at': collection['showing_requested_at'] or datetime.now().strftime('%B %d, %Y %I:%M %p'),
                'dashboard_url': DASHBOARD_URL,
                'agent_name': config.AGENT_NAME,
            },
        )

    except Exception as e:
        logger.error(f"Failed to send showing request alert: {e}")
        return False


def send_daily_activity_digest() -> bool:
    """Send a daily digest of all unnotified buyer actions to the agent.

    Queries buyer_activity for rows where agent_notified = 0,
    groups them by buyer, sends a single digest email, then marks
    all events as notified.

    Returns:
        True if digest was sent (or no actions to report)
    """
    try:
        db = _get_db()

        # Get unnotified activities
        activities = db.execute(
            '''SELECT ba.*, u.name as user_name, u.email as user_email
               FROM buyer_activity ba
               LEFT JOIN users u ON u.id = ba.user_id
               WHERE ba.agent_notified = 0
               ORDER BY ba.occurred_at DESC'''
        ).fetchall()

        if not activities:
            logger.info("No unnotified buyer activity to digest")
            db.close()
            return True

        activity_list = [dict(a) for a in activities]
        activity_ids = [a['id'] for a in activity_list]

        # Separate showing requests
        showing_requests = [a for a in activity_list if a['activity_type'] == 'request_showings']

        # Group by buyer name
        grouped = defaultdict(list)
        for act in activity_list:
            buyer_name = act['user_name'] or act['user_email'] or act['user_id']
            grouped[buyer_name].append(act)

        # Count unique buyers
        buyer_ids = set(a['user_id'] for a in activity_list)

        subject = f"Buyer Activity: {len(activity_list)} actions from {len(buyer_ids)} {'buyer' if len(buyer_ids) == 1 else 'buyers'}"

        recipient = os.getenv('AGENT_EMAIL', config.SMTP_USERNAME)
        if not recipient:
            logger.warning("No agent email configured for activity digest")
            db.close()
            return False

        sent = send_template_email(
            to=recipient,
            subject=subject,
            template_name='buyer_activity_digest.html',
            context={
                'date': datetime.now().strftime('%B %d, %Y'),
                'total_actions': len(activity_list),
                'buyer_count': len(buyer_ids),
                'showing_request_count': len(showing_requests),
                'showing_requests': showing_requests,
                'grouped_activities': dict(grouped),
                'dashboard_url': DASHBOARD_URL,
                'agent_name': config.AGENT_NAME,
            },
        )

        if sent:
            # Mark all activities as notified
            placeholders = ','.join(['?'] * len(activity_ids))
            db.execute(
                f'UPDATE buyer_activity SET agent_notified = 1 WHERE id IN ({placeholders})',
                activity_ids
            )
            db.commit()
            logger.info(f"Digest sent: {len(activity_list)} activities from {len(buyer_ids)} buyers")
        else:
            logger.warning("Failed to send activity digest email")

        db.close()
        return sent

    except Exception as e:
        logger.error(f"Failed to send daily activity digest: {e}")
        return False


def main():
    """Entry point for cron job."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    logger.info("Running daily buyer activity digest...")
    send_daily_activity_digest()
    logger.info("Done.")


if __name__ == '__main__':
    main()
