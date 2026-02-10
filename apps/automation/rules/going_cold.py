"""
Going Cold Rule

Fires when a previously active contact (heat > threshold at some point)
has had no activity for N+ days.
Actions: FUB task "Follow Up - Going Cold"
"""

import logging
from typing import List

from apps.automation.rules import RuleFiring

logger = logging.getLogger(__name__)

RULE_NAME = 'going_cold'


def evaluate(db, settings: dict) -> List[RuleFiring]:
    """
    Find contacts who were active but have gone cold.

    Settings used:
        rule_going_cold_days (int): Days of inactivity threshold (default 14)
        rule_going_cold_min_heat (int): Must have had heat above this (default 30)
    """
    days = settings.get('rule_going_cold_days', 14)
    min_heat = settings.get('rule_going_cold_min_heat', 30)
    firings = []

    with db._get_connection() as conn:
        # Find contacts whose score_trend is 'cooling' or who have been inactive
        # AND who previously had a heat_score above the threshold
        rows = conn.execute('''
            SELECT
                l.id as contact_id,
                l.first_name || ' ' || COALESCE(l.last_name, '') as contact_name,
                l.fub_id,
                l.days_since_activity,
                l.heat_score
            FROM leads l
            WHERE l.stage NOT IN ('trash', 'past_client')
              AND l.days_since_activity >= ?
              AND l.id IN (
                  SELECT contact_id FROM contact_scoring_history
                  WHERE heat_score >= ?
              )
            ORDER BY l.days_since_activity DESC
        ''', (days, min_heat)).fetchall()

    for row in rows:
        name = row['contact_name'].strip()
        fub_id = row['fub_id']

        if fub_id:
            firings.append(RuleFiring(
                contact_id=row['contact_id'],
                contact_name=name,
                fub_id=int(fub_id),
                action_type='fub_task',
                action_detail='Follow Up - Going Cold',
            ))

    logger.info(f"[{RULE_NAME}] Found {len(firings)} contacts going cold ({days}+ days inactive)")
    return firings
