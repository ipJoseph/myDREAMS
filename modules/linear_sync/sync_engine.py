"""Bidirectional sync engine for Linear ↔ FUB."""

import logging
import re
from datetime import datetime
from typing import Optional

from .config import config
from .db import db
from .linear_client import linear_client
from .fub_client import fub_client
from .models import (
    LinearIssue,
    FUBTask,
    FUBPerson,
    FUBDeal,
    ProcessGroup,
    get_team_for_stage,
    get_priority_for_type,
)

logger = logging.getLogger(__name__)


class SyncEngine:
    """Bidirectional sync between Linear and FUB."""

    def __init__(self):
        self.linear = linear_client
        self.fub = fub_client
        self.db = db

    # =========================================================================
    # TEAM & STATE RESOLUTION
    # =========================================================================

    def get_team_id_for_process(self, process: ProcessGroup) -> Optional[str]:
        """Get Linear team ID for a process group."""
        team_key = process.value.upper()
        team_config = self.db.get_team_config(team_key)
        if team_config:
            return team_config['team_id']

        # Fallback to config
        if process == ProcessGroup.DEVELOP:
            return config.DEVELOP_TEAM_ID
        elif process == ProcessGroup.TRANSACT:
            return config.TRANSACT_TEAM_ID
        else:
            return config.GENERAL_TEAM_ID

    def get_initial_state_for_team(self, team_id: str) -> Optional[str]:
        """Get the initial state ID for a team."""
        # Try cached config first
        for tc in self.db.get_all_team_configs():
            if tc['team_id'] == team_id and tc.get('default_state_id'):
                return tc['default_state_id']

        # Fetch from API
        state = self.linear.get_initial_state(team_id)
        return state.id if state else None

    def get_completed_state_for_team(self, team_id: str) -> Optional[str]:
        """Get the completed state ID for a team."""
        # Try cached config first
        for tc in self.db.get_all_team_configs():
            if tc['team_id'] == team_id and tc.get('completed_state_id'):
                return tc['completed_state_id']

        # Fetch from API
        state = self.linear.get_completed_state(team_id)
        return state.id if state else None

    # =========================================================================
    # PERSON LABEL MANAGEMENT
    # =========================================================================

    def get_or_create_person_label(self, person: FUBPerson) -> str:
        """Get or create a Linear label for a FUB person."""
        # Check cache first
        cached = self.db.get_person_label(person.id)
        if cached:
            return cached['linear_label_id']

        # Create label name (Last, First or just name)
        if person.last_name and person.first_name:
            label_name = f"{person.last_name}, {person.first_name}"
        else:
            label_name = person.name

        # Get or create in Linear (workspace-wide label)
        label = self.linear.get_or_create_label(label_name, color='#5E6AD2')

        # Cache mapping
        self.db.set_person_label(
            fub_person_id=person.id,
            fub_person_name=person.name,
            linear_label_id=label.id,
            linear_label_name=label.name,
        )

        return label.id

    def find_person_from_label(self, label_name: str) -> Optional[FUBPerson]:
        """Find FUB person from Linear label name."""
        # Check local cache first
        all_labels = self.db.get_all_person_labels()
        for pl in all_labels:
            if pl['linear_label_name'].lower() == label_name.lower():
                return self.fub.get_person(pl['fub_person_id'])

        # Try searching FUB
        return self.fub.find_person_by_name(label_name)

    # =========================================================================
    # FUB → LINEAR SYNC
    # =========================================================================

    def sync_fub_to_linear(self, fub_task: FUBTask) -> Optional[LinearIssue]:
        """Sync a FUB task to Linear."""
        # Check if already mapped
        mapping = self.db.get_mapping_by_fub(fub_task.id)

        if mapping:
            # Check if we need to update
            if mapping.get('fub_updated_at') == fub_task.updated:
                logger.debug(f"FUB task {fub_task.id} unchanged, skipping")
                return None

            return self._update_linear_from_fub(fub_task, mapping)
        else:
            return self._create_linear_from_fub(fub_task)

    def _create_linear_from_fub(self, fub_task: FUBTask) -> Optional[LinearIssue]:
        """Create a new Linear issue from FUB task."""
        logger.info(f"Creating Linear issue from FUB task {fub_task.id}: {fub_task.name}")

        # Get person for context
        person = self.fub.get_person(fub_task.person_id)
        if not person:
            logger.warning(f"Person {fub_task.person_id} not found for task {fub_task.id}")
            return None

        # Determine team based on deal stage
        deals = self.fub.get_deals_for_person(fub_task.person_id)
        process = ProcessGroup.DEVELOP  # Default
        deal = None

        if deals:
            deal = deals[0]
            self.db.cache_deal(deal)
            process = get_team_for_stage(deal.stage_name)

        team_id = self.get_team_id_for_process(process)
        if not team_id:
            logger.error(f"No team configured for process {process}")
            return None

        # Get or create person label
        person_label_id = self.get_or_create_person_label(person)

        # Prepare label IDs
        label_ids = [person_label_id]

        # Add FUB-synced label if configured
        if config.FUB_SYNCED_LABEL_ID:
            label_ids.append(config.FUB_SYNCED_LABEL_ID)

        # Map priority
        priority = get_priority_for_type(fub_task.type)

        # Get initial state
        state_id = self.get_initial_state_for_team(team_id)

        # Determine project (only in TRANSACT for deals)
        project_id = None
        if process == ProcessGroup.TRANSACT and deal:
            project_name = f"{person.name} - {deal.property_address or deal.name or 'Deal'}"
            project = self.linear.get_or_create_project(project_name, team_id)
            project_id = project.id

        # Build description
        description_parts = []
        if fub_task.note:
            description_parts.append(fub_task.note)
        description_parts.append(f"\n---\n*Synced from FUB*\nPerson: {person.name}\nTask Type: {fub_task.type}")
        if deal:
            description_parts.append(f"Deal: {deal.name or 'N/A'}\nStage: {deal.stage_name}")

        description = '\n'.join(description_parts)

        # Create issue
        issue = self.linear.create_issue(
            title=fub_task.name,
            team_id=team_id,
            description=description,
            priority=priority,
            state_id=state_id,
            project_id=project_id,
            label_ids=label_ids,
            due_date=fub_task.due_date,
        )

        # Create mapping
        self.db.create_mapping(
            linear_issue_id=issue.id,
            linear_identifier=issue.identifier,
            fub_task_id=fub_task.id,
            fub_person_id=fub_task.person_id,
            fub_deal_id=deal.id if deal else None,
            linear_team_id=team_id,
            linear_project_id=project_id,
            person_label_id=person_label_id,
            origin='fub',
            linear_updated_at=issue.updated_at,
            fub_updated_at=fub_task.updated,
        )

        # Log sync
        self.db.log_sync(
            direction='fub_to_linear',
            action='create',
            linear_issue_id=issue.id,
            fub_task_id=fub_task.id,
            fub_person_id=fub_task.person_id,
            fub_deal_id=deal.id if deal else None,
            details={'issue_identifier': issue.identifier, 'title': issue.title},
        )

        logger.info(f"Created Linear issue {issue.identifier} from FUB task {fub_task.id}")
        return issue

    def _update_linear_from_fub(self, fub_task: FUBTask, mapping: dict) -> Optional[LinearIssue]:
        """Update existing Linear issue from FUB task."""
        logger.info(f"Updating Linear issue from FUB task {fub_task.id}")

        linear_issue_id = mapping['linear_issue_id']

        # Check if completed
        if fub_task.is_completed:
            return self._complete_linear_from_fub(fub_task, mapping)

        # Update issue
        issue = self.linear.update_issue(
            issue_id=linear_issue_id,
            title=fub_task.name,
            due_date=fub_task.due_date,
        )

        # Update mapping
        self.db.update_mapping(
            mapping_id=mapping['id'],
            linear_updated_at=issue.updated_at,
            fub_updated_at=fub_task.updated,
        )

        # Log sync
        self.db.log_sync(
            direction='fub_to_linear',
            action='update',
            linear_issue_id=issue.id,
            fub_task_id=fub_task.id,
            fub_person_id=fub_task.person_id,
        )

        return issue

    def _complete_linear_from_fub(self, fub_task: FUBTask, mapping: dict) -> Optional[LinearIssue]:
        """Complete Linear issue when FUB task is completed."""
        logger.info(f"Completing Linear issue from FUB task {fub_task.id}")

        linear_issue_id = mapping['linear_issue_id']

        # Complete the issue
        issue = self.linear.complete_issue(linear_issue_id)

        # Update mapping
        self.db.update_mapping(
            mapping_id=mapping['id'],
            linear_updated_at=issue.updated_at,
            fub_updated_at=fub_task.updated,
        )

        # Log sync
        self.db.log_sync(
            direction='fub_to_linear',
            action='complete',
            linear_issue_id=issue.id,
            fub_task_id=fub_task.id,
            fub_person_id=fub_task.person_id,
        )

        return issue

    # =========================================================================
    # LINEAR → FUB SYNC
    # =========================================================================

    def sync_linear_to_fub(self, issue: LinearIssue) -> Optional[FUBTask]:
        """Sync a Linear issue to FUB."""
        # Check if already mapped
        mapping = self.db.get_mapping_by_linear(issue.id)

        if mapping:
            # Check if we need to update
            if mapping.get('linear_updated_at') == issue.updated_at:
                logger.debug(f"Linear issue {issue.identifier} unchanged, skipping")
                return None

            return self._update_fub_from_linear(issue, mapping)
        else:
            return self._create_fub_from_linear(issue)

    def _create_fub_from_linear(self, issue: LinearIssue) -> Optional[FUBTask]:
        """Create a new FUB task from Linear issue."""
        logger.info(f"Creating FUB task from Linear issue {issue.identifier}: {issue.title}")

        # Find person from labels
        person = None
        person_label_id = None

        for i, label_name in enumerate(issue.label_names):
            # Skip system labels
            if label_name.lower() in ('fub-synced', 'call', 'showing', 'offer', 'document', 'meeting', 'follow-up'):
                continue

            # Try to find person
            found = self.find_person_from_label(label_name)
            if found:
                person = found
                person_label_id = issue.label_ids[i] if i < len(issue.label_ids) else None
                break

        if not person:
            # Try to extract person name from title [Name]
            match = re.search(r'\[([^\]]+)\]$', issue.title)
            if match:
                person_name = match.group(1)
                person = self.fub.find_person_by_name(person_name)

        if not person:
            logger.warning(f"Could not find person for Linear issue {issue.identifier}")
            return None

        # Determine task type from labels or priority
        task_type = 'Todo'
        for label_name in issue.label_names:
            label_lower = label_name.lower()
            if label_lower in ('call', 'showing', 'offer', 'email', 'text', 'meeting', 'follow-up'):
                task_type = label_name.title()
                break

        # Create FUB task (assignedUserId required by FUB API)
        import os
        assigned_user_id = int(os.getenv('FUB_MY_USER_ID', '8'))

        # Append Linear reference to task name since FUB doesn't support notes on create
        task_name = f"{issue.title} [{issue.identifier}]"

        task = self.fub.create_task(
            person_id=person.id,
            name=task_name,
            task_type=task_type,
            due_date=issue.due_date,
            assigned_user_id=assigned_user_id,
        )

        # Get deal if any
        deals = self.fub.get_deals_for_person(person.id)
        deal = deals[0] if deals else None

        # Create mapping
        self.db.create_mapping(
            linear_issue_id=issue.id,
            linear_identifier=issue.identifier,
            fub_task_id=task.id,
            fub_person_id=person.id,
            fub_deal_id=deal.id if deal else None,
            linear_team_id=issue.team_id,
            linear_project_id=issue.project_id,
            person_label_id=person_label_id,
            origin='linear',
            linear_updated_at=issue.updated_at,
            fub_updated_at=task.updated,
        )

        # Log sync
        self.db.log_sync(
            direction='linear_to_fub',
            action='create',
            linear_issue_id=issue.id,
            fub_task_id=task.id,
            fub_person_id=person.id,
            details={'issue_identifier': issue.identifier, 'title': issue.title},
        )

        logger.info(f"Created FUB task {task.id} from Linear issue {issue.identifier}")
        return task

    def _update_fub_from_linear(self, issue: LinearIssue, mapping: dict) -> Optional[FUBTask]:
        """Update existing FUB task from Linear issue."""
        logger.info(f"Updating FUB task from Linear issue {issue.identifier}")

        fub_task_id = mapping['fub_task_id']

        # Check if completed
        if issue.is_completed or issue.is_canceled:
            return self._complete_fub_from_linear(issue, mapping)

        # Update task
        task = self.fub.update_task(
            task_id=fub_task_id,
            name=issue.title,
            due_date=issue.due_date,
        )

        # Update mapping
        self.db.update_mapping(
            mapping_id=mapping['id'],
            linear_updated_at=issue.updated_at,
            fub_updated_at=task.updated,
        )

        # Log sync
        self.db.log_sync(
            direction='linear_to_fub',
            action='update',
            linear_issue_id=issue.id,
            fub_task_id=task.id,
            fub_person_id=mapping['fub_person_id'],
        )

        return task

    def _complete_fub_from_linear(self, issue: LinearIssue, mapping: dict) -> Optional[FUBTask]:
        """Complete FUB task when Linear issue is completed."""
        logger.info(f"Completing FUB task from Linear issue {issue.identifier}")

        fub_task_id = mapping['fub_task_id']

        # Complete the task
        task = self.fub.complete_task(fub_task_id)

        # Update mapping
        self.db.update_mapping(
            mapping_id=mapping['id'],
            linear_updated_at=issue.updated_at,
            fub_updated_at=task.updated,
        )

        # Log sync
        self.db.log_sync(
            direction='linear_to_fub',
            action='complete',
            linear_issue_id=issue.id,
            fub_task_id=task.id,
            fub_person_id=mapping['fub_person_id'],
        )

        return task

    # =========================================================================
    # POLLING METHODS
    # =========================================================================

    def poll_fub_changes(self, limit: int = 100) -> int:
        """Poll FUB for task changes and sync to Linear."""
        logger.debug("Polling FUB for task changes")

        # Get incomplete tasks
        tasks = self.fub.get_tasks(include_completed=False, limit=limit)

        synced = 0
        for task in tasks:
            try:
                result = self.sync_fub_to_linear(task)
                if result:
                    synced += 1
            except Exception as e:
                logger.error(f"Error syncing FUB task {task.id}: {e}")
                self.db.log_sync(
                    direction='fub_to_linear',
                    action='error',
                    fub_task_id=task.id,
                    details={'error': str(e)},
                    status='error',
                )

        # Also check recently completed tasks for completion sync
        self._sync_completed_fub_tasks()

        logger.debug(f"Synced {synced} tasks from FUB to Linear")
        return synced

    def _sync_completed_fub_tasks(self):
        """Check mapped FUB tasks that may have been completed."""
        # Get all mappings where origin is FUB
        mappings = self.db.get_all_mappings()

        for mapping in mappings:
            if mapping['origin'] != 'fub':
                continue

            try:
                task = self.fub.get_task(mapping['fub_task_id'])
                if task and task.is_completed:
                    # Check if Linear issue is already completed
                    issue = self.linear.get_issue(mapping['linear_issue_id'])
                    if issue and not issue.is_completed:
                        self._complete_linear_from_fub(task, mapping)
            except Exception as e:
                logger.error(f"Error checking completed FUB task {mapping['fub_task_id']}: {e}")

    def poll_linear_changes(self, limit: int = 100) -> int:
        """Poll Linear for issue changes and sync to FUB."""
        logger.debug("Polling Linear for issue changes")

        # Get last poll time
        last_poll = self.db.get_state('linear_last_poll')
        since = last_poll if last_poll else None

        # Get issues updated since last poll
        issues = []
        team_configs = self.db.get_all_team_configs()

        for tc in team_configs:
            team_issues = self.linear.get_issues_updated_since(
                since=since,
                team_id=tc['team_id'],
            ) if since else self.linear.get_issues(team_id=tc['team_id'], limit=limit)
            issues.extend(team_issues)

        synced = 0
        for issue in issues:
            # Skip issues that came from FUB (to avoid loops)
            mapping = self.db.get_mapping_by_linear(issue.id)
            if mapping and mapping['origin'] == 'fub':
                # Still check for completion sync
                if issue.is_completed:
                    self._sync_completion_to_fub(issue, mapping)
                continue

            try:
                result = self.sync_linear_to_fub(issue)
                if result:
                    synced += 1
            except Exception as e:
                logger.error(f"Error syncing Linear issue {issue.identifier}: {e}")
                self.db.log_sync(
                    direction='linear_to_fub',
                    action='error',
                    linear_issue_id=issue.id,
                    details={'error': str(e)},
                    status='error',
                )

        # Update last poll time
        self.db.set_state('linear_last_poll', datetime.now().isoformat())

        logger.debug(f"Synced {synced} issues from Linear to FUB")
        return synced

    def _sync_completion_to_fub(self, issue: LinearIssue, mapping: dict):
        """Sync completion status to FUB for FUB-originated issues."""
        if issue.is_completed or issue.is_canceled:
            try:
                task = self.fub.get_task(mapping['fub_task_id'])
                if task and not task.is_completed:
                    self._complete_fub_from_linear(issue, mapping)
            except Exception as e:
                logger.error(f"Error syncing completion to FUB: {e}")

    # =========================================================================
    # FULL SYNC
    # =========================================================================

    def sync_all_fub_tasks(self) -> int:
        """Sync all incomplete FUB tasks to Linear."""
        logger.info("Starting full sync of FUB tasks to Linear")

        tasks = self.fub.get_tasks(include_completed=False, limit=500)
        synced = 0

        for task in tasks:
            try:
                result = self.sync_fub_to_linear(task)
                if result:
                    synced += 1
            except Exception as e:
                logger.error(f"Error syncing FUB task {task.id}: {e}")

        logger.info(f"Full sync complete: {synced} tasks synced")
        return synced


# Module-level singleton
sync_engine = SyncEngine()
