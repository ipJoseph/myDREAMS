"""
New Lead Rule

Fires for contacts with stage='Lead' created within the last N hours.
Actions: FUB task "Call - New Lead" (priority 1)
"""

import logging
from typing import List

from apps.automation.rules import RuleFiring

logger = logging.getLogger(__name__)

RULE_NAME = 'new_lead'


def evaluate(db, settings: dict) -> List[RuleFiring]:
    """
    Find recently created leads.

    Settings used:
        rule_new_lead_hours (int): How recent is "new" in hours (default 24)
    """
    hours = settings.get('rule_new_lead_hours', 24)
    firings = []

    with db._get_connection() as conn:
        rows = conn.execute('''
            SELECT
                l.id as contact_id,
                l.first_name || ' ' || COALESCE(l.last_name, '') as contact_name,
                l.fub_id,
                l.source,
                l.created_at
            FROM leads l
            WHERE l.stage = 'Lead'
              AND l.created_at >= datetime('now', ? || ' hours')
            ORDER BY l.created_at DESC
        ''', (f'-{hours}',)).fetchall()

    for row in rows:
        name = row['contact_name'].strip()
        fub_id = row['fub_id']
        source = row['source'] or 'Unknown'

        if fub_id:
            firings.append(RuleFiring(
                contact_id=row['contact_id'],
                contact_name=name,
                fub_id=int(fub_id),
                action_type='fub_task',
                action_detail='Call - New Lead',
            ))

    logger.info(f"[{RULE_NAME}] Found {len(firings)} new leads in last {hours}h")
    return firings
