"""
Rules Engine

Evaluates automation rules against lead data and dispatches actions.
Handles cooldown checks, action dispatch (email, FUB tasks), and logging.
"""

import json
import importlib
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from apps.automation.rules import RULE_REGISTRY, RuleFiring

logger = logging.getLogger(__name__)


class RuleEngine:
    """
    Evaluates rules and dispatches actions.

    Usage:
        engine = RuleEngine(db)
        results = engine.evaluate_all()
        # or
        results = engine.evaluate_rule('activity_burst')
    """

    def __init__(self, db, fub_client=None, dry_run: bool = False):
        """
        Args:
            db: DREAMSDatabase instance
            fub_client: FUBClient instance (optional — actions that need FUB will be skipped if None)
            dry_run: If True, log what would happen without executing actions
        """
        self.db = db
        self.fub_client = fub_client
        self.dry_run = dry_run
        self._settings_cache = None

    def _get_settings(self) -> Dict[str, Any]:
        """Load all automation settings from the database."""
        if self._settings_cache is None:
            settings = {}
            all_settings = self.db.get_all_settings(category='automation')
            for s in all_settings:
                settings[s['key']] = s['converted_value']
            # Also check alerts category for global enabled
            for s in self.db.get_all_settings():
                settings[s['key']] = s['converted_value']
            self._settings_cache = settings
        return self._settings_cache

    def evaluate_all(self) -> Dict[str, Any]:
        """
        Evaluate all enabled rules.

        Returns:
            Summary dict with per-rule results and totals.
        """
        settings = self._get_settings()

        # Global kill switch
        if not settings.get('rules_engine_enabled', True):
            logger.info("Rules engine is disabled globally")
            return {'status': 'disabled', 'rules': {}}

        results = {}
        total_firings = 0
        total_actions = 0

        for rule_name, rule_config in RULE_REGISTRY.items():
            # Check per-rule enabled flag
            enabled_key = rule_config['enabled_key']
            if not settings.get(enabled_key, True):
                logger.info(f"[{rule_name}] Skipped — disabled")
                results[rule_name] = {'status': 'disabled', 'firings': 0, 'actions': 0}
                continue

            result = self.evaluate_rule(rule_name)
            results[rule_name] = result
            total_firings += result.get('firings', 0)
            total_actions += result.get('actions', 0)

        return {
            'status': 'completed',
            'dry_run': self.dry_run,
            'total_firings': total_firings,
            'total_actions': total_actions,
            'rules': results,
            'timestamp': datetime.now().isoformat(),
        }

    def evaluate_rule(self, rule_name: str) -> Dict[str, Any]:
        """
        Evaluate a single rule.

        Returns:
            Dict with status, firings count, actions count, and details.
        """
        if rule_name not in RULE_REGISTRY:
            logger.error(f"Unknown rule: {rule_name}")
            return {'status': 'error', 'error': f'Unknown rule: {rule_name}'}

        rule_config = RULE_REGISTRY[rule_name]
        settings = self._get_settings()

        try:
            # Import the rule module
            module = importlib.import_module(rule_config['module'])
            evaluate_fn = module.evaluate

            # Run the rule's evaluate function
            raw_firings: List[RuleFiring] = evaluate_fn(self.db, settings)

            # Filter by cooldowns
            firings = []
            skipped_cooldown = 0
            for firing in raw_firings:
                if self.db.check_automation_cooldown(rule_name, firing.contact_id):
                    skipped_cooldown += 1
                    continue
                firings.append(firing)

            # Dispatch actions
            actions_taken = 0
            action_details = []

            for firing in firings:
                success = self._dispatch_action(rule_name, firing, settings)
                if success:
                    actions_taken += 1
                    action_details.append({
                        'contact': firing.contact_name,
                        'action': firing.action_type,
                        'detail': firing.action_detail,
                    })

            logger.info(
                f"[{rule_name}] {len(raw_firings)} matches, "
                f"{skipped_cooldown} cooldown skips, "
                f"{actions_taken} actions taken"
            )

            return {
                'status': 'completed',
                'firings': len(firings),
                'actions': actions_taken,
                'skipped_cooldown': skipped_cooldown,
                'details': action_details,
            }

        except Exception as e:
            logger.error(f"[{rule_name}] Error evaluating rule: {e}", exc_info=True)
            return {'status': 'error', 'error': str(e)}

    def _dispatch_action(self, rule_name: str, firing: RuleFiring, settings: dict) -> bool:
        """
        Dispatch a single action and log it.

        Returns True if the action succeeded (or dry_run).
        """
        # Calculate cooldown
        cooldown_key = RULE_REGISTRY[rule_name].get('cooldown_key')
        if cooldown_key:
            cooldown_hours = settings.get(cooldown_key, 48)
        else:
            # new_lead: "once ever" = 10 year cooldown
            cooldown_hours = 87600
        cooldown_until = (datetime.now() + timedelta(hours=cooldown_hours)).isoformat()

        if self.dry_run:
            logger.info(
                f"  [DRY RUN] {rule_name} → {firing.action_type}: "
                f"{firing.contact_name} — {firing.action_detail}"
            )
            return True

        success = False

        try:
            if firing.action_type == 'email_agent':
                success = self._send_agent_email(rule_name, firing, settings)
            elif firing.action_type == 'fub_task':
                success = self._create_fub_task(rule_name, firing, settings)
            elif firing.action_type == 'fub_note':
                success = self._create_fub_note(rule_name, firing, settings)
            else:
                logger.warning(f"Unknown action type: {firing.action_type}")
                success = False
        except Exception as e:
            logger.error(f"Action dispatch error: {e}", exc_info=True)
            success = False

        # Log the firing regardless of success
        self.db.log_automation_firing(
            rule_name=rule_name,
            contact_id=firing.contact_id,
            contact_name=firing.contact_name,
            action_type=firing.action_type,
            action_detail=firing.action_detail,
            cooldown_until=cooldown_until,
            success=success,
        )

        return success

    def _send_agent_email(self, rule_name: str, firing: RuleFiring, settings: dict) -> bool:
        """Send an alert email to the agent. Returns True on success."""
        agent_email = settings.get('rules_agent_email', '') or os.getenv('AGENT_EMAIL', '')
        if not agent_email:
            logger.warning(f"No agent email configured — skipping email for {firing.contact_name}")
            return False

        # Collect email into the batch — actual sending happens in _send_batch_email
        # For now, send individual emails per firing
        try:
            from apps.automation.email_service import send_template_email
            from apps.automation import config

            subject = f"[DREAMS] {rule_name.replace('_', ' ').title()}: {firing.contact_name}"

            context = {
                'rule_name': rule_name,
                'rule_display': rule_name.replace('_', ' ').title(),
                'contact_name': firing.contact_name,
                'contact_id': firing.contact_id,
                'action_detail': firing.action_detail,
                'fired_at': datetime.now().strftime('%B %d, %Y at %I:%M %p'),
                'agent_name': config.AGENT_NAME,
                'dashboard_url': os.getenv('DASHBOARD_URL', 'https://app.wncmountain.homes'),
            }

            return send_template_email(
                to=agent_email,
                subject=subject,
                template_name='rule_alert.html',
                context=context,
            )
        except Exception as e:
            logger.error(f"Failed to send agent email: {e}")
            return False

    def _create_fub_task(self, rule_name: str, firing: RuleFiring, settings: dict) -> bool:
        """Create a task in FUB. Returns True on success."""
        if not self.fub_client:
            logger.warning("No FUB client available — skipping task creation")
            return False

        if not firing.fub_id:
            logger.warning(f"No FUB ID for {firing.contact_name} — skipping task")
            return False

        try:
            # Determine task type based on action detail
            task_name = firing.action_detail
            task_type = 'Call' if 'Call' in task_name else 'Follow Up'

            # Set priority: new_lead gets priority 1 (high)
            priority = 1 if rule_name == 'new_lead' else None

            result = self.fub_client.create_task(
                person_id=firing.fub_id,
                name=task_name,
                task_type=task_type,
                priority=priority,
            )

            if result:
                logger.info(f"Created FUB task for {firing.contact_name}: {task_name}")
                try:
                    from src.core.fub_audit import log_fub_write
                    log_fub_write(module='rules_engine', operation='create_task',
                                  endpoint='tasks', http_method='POST',
                                  fub_person_id=firing.fub_id,
                                  payload_summary=f'{task_type}: {task_name}')
                except Exception:
                    pass
                return True
            else:
                logger.warning(f"FUB task creation returned None for {firing.contact_name}")
                return False
        except Exception as e:
            logger.error(f"Failed to create FUB task: {e}")
            return False

    def _create_fub_note(self, rule_name: str, firing: RuleFiring, settings: dict) -> bool:
        """Create a note in FUB. Returns True on success."""
        if not self.fub_client:
            logger.warning("No FUB client available — skipping note creation")
            return False

        if not firing.fub_id:
            logger.warning(f"No FUB ID for {firing.contact_name} — skipping note")
            return False

        try:
            body = f"[DREAMS Automation] {rule_name.replace('_', ' ').title()}\n\n{firing.action_detail}"
            result = self.fub_client.create_note(
                person_id=firing.fub_id,
                body=body,
            )

            if result:
                logger.info(f"Created FUB note for {firing.contact_name}")
                try:
                    from src.core.fub_audit import log_fub_write
                    log_fub_write(module='rules_engine', operation='create_note',
                                  endpoint='notes', http_method='POST',
                                  fub_person_id=firing.fub_id,
                                  payload_summary=f'[Automation] {rule_name}')
                except Exception:
                    pass
                return True
            else:
                return False
        except Exception as e:
            logger.error(f"Failed to create FUB note: {e}")
            return False
