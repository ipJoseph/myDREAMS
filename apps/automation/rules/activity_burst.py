"""
Activity Burst Rule

Fires when a contact has 3+ events in the last 24 hours.
Actions: Email agent + FUB task "Call - Activity Burst"
"""

import logging
from typing import List

from apps.automation.rules import RuleFiring

logger = logging.getLogger(__name__)

RULE_NAME = 'activity_burst'


def evaluate(db, settings: dict) -> List[RuleFiring]:
    """
    Find contacts with N+ events in the last 24 hours.

    Settings used:
        rule_activity_burst_threshold (int): Minimum events in 24h (default 3)
    """
    threshold = settings.get('rule_activity_burst_threshold', 3)
    firings = []

    with db._get_connection() as conn:
        rows = conn.execute('''
            SELECT
                l.id as contact_id,
                l.first_name || ' ' || COALESCE(l.last_name, '') as contact_name,
                l.fub_id,
                COUNT(e.id) as event_count
            FROM contact_events e
            JOIN leads l ON e.contact_id = l.id
            WHERE e.occurred_at >= datetime('now', '-1 day')
              AND l.stage NOT IN ('trash', 'past_client')
            GROUP BY e.contact_id
            HAVING COUNT(e.id) >= ?
            ORDER BY event_count DESC
        ''', (threshold,)).fetchall()

    for row in rows:
        name = row['contact_name'].strip()
        fub_id = row['fub_id']

        # Email alert
        firings.append(RuleFiring(
            contact_id=row['contact_id'],
            contact_name=name,
            fub_id=int(fub_id) if fub_id else None,
            action_type='email_agent',
            action_detail=f'{name} had {row["event_count"]} events in the last 24 hours',
        ))

        # FUB task (only if contact has fub_id)
        if fub_id:
            firings.append(RuleFiring(
                contact_id=row['contact_id'],
                contact_name=name,
                fub_id=int(fub_id),
                action_type='fub_task',
                action_detail='Call - Activity Burst',
            ))

    logger.info(f"[{RULE_NAME}] Found {len(rows)} contacts with {threshold}+ events in 24h")
    return firings
