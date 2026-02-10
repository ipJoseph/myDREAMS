"""
Automation Rules Registry

Each rule module exports an `evaluate()` function that checks a condition
and returns a list of RuleFiring namedtuples.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class RuleFiring:
    """Represents a single rule firing for a contact."""
    contact_id: str
    contact_name: str
    fub_id: Optional[int]
    action_type: str       # 'email_agent', 'fub_task', 'fub_note'
    action_detail: str     # JSON-serializable detail string


# Rule registry - maps rule_name to (module, cooldown_setting_key)
RULE_REGISTRY = {
    'activity_burst': {
        'module': 'apps.automation.rules.activity_burst',
        'enabled_key': 'rule_activity_burst_enabled',
        'cooldown_key': 'rule_activity_burst_cooldown_hours',
        'description': 'Alerts when a contact has 3+ events in 24 hours',
    },
    'going_cold': {
        'module': 'apps.automation.rules.going_cold',
        'enabled_key': 'rule_going_cold_enabled',
        'cooldown_key': 'rule_going_cold_cooldown_hours',
        'description': 'Creates follow-up task when previously active contacts go silent',
    },
    'hot_lead': {
        'module': 'apps.automation.rules.hot_lead',
        'enabled_key': 'rule_hot_lead_enabled',
        'cooldown_key': 'rule_hot_lead_cooldown_hours',
        'description': 'Alerts when heat score crosses threshold',
    },
    'warming_lead': {
        'module': 'apps.automation.rules.warming_lead',
        'enabled_key': 'rule_warming_lead_enabled',
        'cooldown_key': 'rule_warming_lead_cooldown_hours',
        'description': 'Alerts when a lead is trending warmer with significant delta',
    },
    'new_lead': {
        'module': 'apps.automation.rules.new_lead',
        'enabled_key': 'rule_new_lead_enabled',
        'cooldown_key': None,  # Once ever — uses very long cooldown
        'description': 'Creates call task for newly created leads',
    },
}
