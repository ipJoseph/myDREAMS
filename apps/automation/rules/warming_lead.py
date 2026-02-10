"""
Warming Lead Rule

Fires when a contact's score_trend is "warming" AND their heat_delta
exceeds the minimum threshold.
Actions: Email agent
"""

import logging
from typing import List

from apps.automation.rules import RuleFiring

logger = logging.getLogger(__name__)

RULE_NAME = 'warming_lead'


def evaluate(db, settings: dict) -> List[RuleFiring]:
    """
    Find contacts whose trend is warming with significant heat delta.

    Settings used:
        rule_warming_lead_min_delta (int): Minimum heat_delta (default 15)
    """
    min_delta = settings.get('rule_warming_lead_min_delta', 15)
    firings = []

    with db._get_connection() as conn:
        # Get the latest scoring history for warming leads
        rows = conn.execute('''
            SELECT
                l.id as contact_id,
                l.first_name || ' ' || COALESCE(l.last_name, '') as contact_name,
                l.fub_id,
                l.heat_score,
                h.heat_delta
            FROM leads l
            JOIN (
                SELECT contact_id, heat_delta, trend_direction,
                       ROW_NUMBER() OVER (PARTITION BY contact_id ORDER BY recorded_at DESC) as rn
                FROM contact_scoring_history
            ) h ON l.id = h.contact_id AND h.rn = 1
            WHERE l.score_trend = 'warming'
              AND h.heat_delta >= ?
              AND l.stage NOT IN ('trash', 'past_client')
            ORDER BY h.heat_delta DESC
        ''', (min_delta,)).fetchall()

    for row in rows:
        name = row['contact_name'].strip()
        delta = row['heat_delta']

        firings.append(RuleFiring(
            contact_id=row['contact_id'],
            contact_name=name,
            fub_id=int(row['fub_id']) if row['fub_id'] else None,
            action_type='email_agent',
            action_detail=f'{name} is warming up — heat delta +{delta:.0f} (score: {row["heat_score"]:.0f})',
        ))

    logger.info(f"[{RULE_NAME}] Found {len(firings)} warming contacts with delta >= {min_delta}")
    return firings
