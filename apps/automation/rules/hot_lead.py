"""
Hot Lead Rule

Fires when a contact's heat_score crosses the threshold (default 70).
Actions: Email agent + FUB task "Call - Hot Lead"
"""

import logging
from typing import List

from apps.automation.rules import RuleFiring

logger = logging.getLogger(__name__)

RULE_NAME = 'hot_lead'


def evaluate(db, settings: dict) -> List[RuleFiring]:
    """
    Find contacts whose heat_score is at or above the threshold.

    Settings used:
        rule_hot_lead_threshold (int): Heat score threshold (default 70)
    """
    threshold = settings.get('rule_hot_lead_threshold', 70)
    firings = []

    with db._get_connection() as conn:
        rows = conn.execute('''
            SELECT
                l.id as contact_id,
                l.first_name || ' ' || COALESCE(l.last_name, '') as contact_name,
                l.fub_id,
                l.heat_score,
                l.priority_score
            FROM leads l
            WHERE l.heat_score >= ?
              AND l.stage NOT IN ('trash', 'past_client')
            ORDER BY l.heat_score DESC
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
            action_detail=f'{name} has heat score {row["heat_score"]:.0f} (threshold: {threshold})',
        ))

        # FUB task
        if fub_id:
            firings.append(RuleFiring(
                contact_id=row['contact_id'],
                contact_name=name,
                fub_id=int(fub_id),
                action_type='fub_task',
                action_detail='Call - Hot Lead',
            ))

    logger.info(f"[{RULE_NAME}] Found {len(rows)} contacts with heat >= {threshold}")
    return firings
