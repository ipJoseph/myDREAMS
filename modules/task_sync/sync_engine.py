"""
Sync Engine - Core bidirectional sync logic.

Handles:
- Change detection
- Direction determination
- Conflict resolution (last-write-wins)
- Anti-loop protection
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from .config import config
from .db import db
from .fub_client import fub_client
from .todoist_client import todoist_client
from .models import FUBTask, TodoistTask, UnifiedTask, TaskOrigin

logger = logging.getLogger(__name__)


class SyncEngine:
    """Bidirectional task sync engine."""

    def __init__(self):
        self.fub = fub_client
        self.todoist = todoist_client

    # ==========================================================================
    # FUB → Todoist
    # ==========================================================================

    def sync_fub_task_to_todoist(self, fub_task: FUBTask) -> Optional[str]:
        """
        Sync a FUB task to Todoist.

        Returns Todoist task ID if created/updated, None if skipped.
        """
        mapping = db.get_mapping_by_fub_id(fub_task.id)

        if mapping:
            # Existing mapping - check if FUB changed
            return self._update_todoist_from_fub(fub_task, mapping)
        else:
            # New task - create in Todoist
            return self._create_todoist_from_fub(fub_task)

    def _create_todoist_from_fub(self, fub_task: FUBTask) -> str:
        """Create a new Todoist task from FUB task."""
        # Import setup here to avoid circular imports
        from .setup import get_project_for_stage, get_default_project

        # Get person info for context
        person = self.fub.get_person(fub_task.person_id)
        person_name = f"{person.get('firstName', '')} {person.get('lastName', '')}".strip() or 'Unknown'

        # Try to get deal for enrichment and project routing
        deal_id = None
        deal_stage = None
        todoist_project_id = None
        pipeline_id = None
        stage_id = None

        try:
            deals = self.fub.get_deals(person_id=fub_task.person_id)
            if deals:
                deal = deals[0]  # Most recent deal
                deal_id = deal.id
                deal_stage = deal.stage_name
                pipeline_id = deal.pipeline_id
                stage_id = deal.stage_id

                # Look up Todoist project for this deal's stage
                if pipeline_id and stage_id:
                    todoist_project_id = get_project_for_stage(pipeline_id, stage_id)
                    if todoist_project_id:
                        logger.debug(f"Routing task to project for stage {deal_stage}")

                # Cache the deal for dashboard use
                deal_data = {
                    'id': deal.id,
                    'person_id': deal.person_id,
                    'pipeline_id': deal.pipeline_id,
                    'stage_id': deal.stage_id,
                    'stage_name': deal.stage_name,
                    'deal_name': deal.name,
                    'deal_value': deal.deal_value,
                    'property_address': deal.property_address,
                    'property_city': deal.property_city,
                    'property_state': deal.property_state,
                    'property_zip': deal.property_zip,
                    'person_name': person_name,
                    'person_email': person.get('emails', [{}])[0].get('value') if person.get('emails') else None,
                    'person_phone': person.get('phones', [{}])[0].get('value') if person.get('phones') else None,
                    'updated': deal.updated,
                }
                db.cache_deal(deal_data)
                logger.debug(f"Cached deal {deal_id} for person {fub_task.person_id}")
        except Exception as e:
            logger.warning(f"Failed to fetch deal for person {fub_task.person_id}: {e}")

        # Fall back to default project if no stage mapping
        if not todoist_project_id:
            todoist_project_id = get_default_project()

        # Map FUB task type to Todoist priority
        priority_map = {
            'Call': 4,
            'Showing': 4,
            'Appointment': 4,
            'Follow Up': 2,
            'Email': 2,
            'Text': 2,
            'Other': 1,
        }
        priority = priority_map.get(fub_task.type, 2)

        # Create Todoist task in the appropriate project
        todoist_task = self.todoist.create_task(
            content=f"{fub_task.name} [{person_name}]",
            description=self._build_todoist_description(fub_task, person_name, deal_stage),
            project_id=todoist_project_id,
            due_date=fub_task.due_date,
            priority=priority,
        )

        # Create mapping with deal context
        db.create_mapping(
            fub_task_id=fub_task.id,
            todoist_task_id=todoist_task.id,
            fub_person_id=fub_task.person_id,
            fub_deal_id=deal_id,
            todoist_project_id=todoist_project_id,
            origin='fub',
        )

        # Update mapping with timestamps
        mapping = db.get_mapping_by_fub_id(fub_task.id)
        db.update_mapping(
            mapping['id'],
            fub_updated_at=fub_task.updated,
            todoist_updated_at=todoist_task.created_at,
            last_synced_at=datetime.now().isoformat(),
        )

        # Log sync
        db.log_sync(
            direction='fub_to_todoist',
            action='create',
            fub_task_id=fub_task.id,
            todoist_task_id=todoist_task.id,
            details=json.dumps({'name': fub_task.name, 'person': person_name}),
        )

        logger.info(f"Created Todoist task {todoist_task.id} from FUB task {fub_task.id}")
        return todoist_task.id

    def _update_todoist_from_fub(self, fub_task: FUBTask, mapping: dict) -> Optional[str]:
        """Update existing Todoist task from FUB changes."""
        todoist_task_id = mapping['todoist_task_id']

        # Anti-loop: check if this is our own echo
        if mapping.get('fub_updated_at') == fub_task.updated:
            logger.debug(f"Skipping FUB task {fub_task.id} - no change since last sync")
            return None

        # Get current Todoist task
        try:
            todoist_task = self.todoist.get_task(todoist_task_id)
        except Exception as e:
            logger.error(f"Failed to get Todoist task {todoist_task_id}: {e}")
            return None

        # Build updates
        person_name = self.fub.get_person_name(fub_task.person_id)
        updates = {}

        # Check what changed
        new_content = f"{fub_task.name} [{person_name}]"
        if todoist_task.content != new_content:
            updates['content'] = new_content

        new_description = self._build_todoist_description(fub_task, person_name)
        if todoist_task.description != new_description:
            updates['description'] = new_description

        if fub_task.due_date and todoist_task.due_date != fub_task.due_date:
            updates['due_date'] = fub_task.due_date

        # Handle completion status
        if fub_task.is_completed and not todoist_task.is_completed:
            self.todoist.close_task(todoist_task_id)
            db.log_sync(
                direction='fub_to_todoist',
                action='complete',
                fub_task_id=fub_task.id,
                todoist_task_id=todoist_task_id,
            )
        elif not fub_task.is_completed and todoist_task.is_completed:
            self.todoist.reopen_task(todoist_task_id)
            db.log_sync(
                direction='fub_to_todoist',
                action='reopen',
                fub_task_id=fub_task.id,
                todoist_task_id=todoist_task_id,
            )

        # Apply updates if any
        if updates:
            self.todoist.update_task(todoist_task_id, **updates)
            db.log_sync(
                direction='fub_to_todoist',
                action='update',
                fub_task_id=fub_task.id,
                todoist_task_id=todoist_task_id,
                details=json.dumps(updates),
            )
            logger.info(f"Updated Todoist task {todoist_task_id} from FUB: {list(updates.keys())}")

        # Update mapping timestamps
        db.update_mapping(
            mapping['id'],
            fub_updated_at=fub_task.updated,
            last_synced_at=datetime.now().isoformat(),
        )

        return todoist_task_id if updates else None

    def _build_todoist_description(self, fub_task: FUBTask, person_name: str, deal_stage: Optional[str] = None) -> str:
        """Build Todoist task description from FUB task."""
        lines = [
            f"**Contact:** {person_name}",
            f"**Type:** {fub_task.type}",
        ]

        if deal_stage:
            lines.append(f"**Stage:** {deal_stage}")

        lines.extend([
            f"**FUB Task ID:** {fub_task.id}",
            "",
            f"[Open in FUB](https://JonTharpTeam.followupboss.com/2/people/view/{fub_task.person_id})",
        ])
        return "\n".join(lines)

    # ==========================================================================
    # Todoist → FUB
    # ==========================================================================

    def sync_todoist_task_to_fub(self, todoist_task: TodoistTask) -> Optional[int]:
        """
        Sync a Todoist task to FUB.

        Returns FUB task ID if created/updated, None if skipped.
        """
        mapping = db.get_mapping_by_todoist_id(todoist_task.id)

        if mapping:
            # Existing mapping - check if Todoist changed
            return self._update_fub_from_todoist(todoist_task, mapping)
        else:
            # New task from Todoist - need person context to create in FUB
            # For now, skip tasks without existing mapping
            logger.debug(f"Skipping Todoist task {todoist_task.id} - no FUB mapping (Todoist-originated tasks not yet supported)")
            return None

    def _update_fub_from_todoist(self, todoist_task: TodoistTask, mapping: dict) -> Optional[int]:
        """Update existing FUB task from Todoist changes."""
        fub_task_id = mapping['fub_task_id']

        # Get current FUB task
        try:
            fub_task = self.fub.get_task(fub_task_id)
        except Exception as e:
            logger.error(f"Failed to get FUB task {fub_task_id}: {e}")
            return None

        # Check what changed
        updates = {}

        # Extract task name (remove person suffix)
        content = todoist_task.content
        if ' [' in content:
            content = content.rsplit(' [', 1)[0]

        if fub_task.name != content:
            updates['name'] = content

        if todoist_task.due_date and fub_task.due_date != todoist_task.due_date:
            updates['due_date'] = todoist_task.due_date

        # Handle completion status
        if todoist_task.is_completed and not fub_task.is_completed:
            self.fub.complete_task(fub_task_id)
            db.log_sync(
                direction='todoist_to_fub',
                action='complete',
                fub_task_id=fub_task_id,
                todoist_task_id=todoist_task.id,
            )
        elif not todoist_task.is_completed and fub_task.is_completed:
            self.fub.uncomplete_task(fub_task_id)
            db.log_sync(
                direction='todoist_to_fub',
                action='reopen',
                fub_task_id=fub_task_id,
                todoist_task_id=todoist_task.id,
            )

        # Apply updates if any
        if updates:
            self.fub.update_task(fub_task_id, **updates)
            db.log_sync(
                direction='todoist_to_fub',
                action='update',
                fub_task_id=fub_task_id,
                todoist_task_id=todoist_task.id,
                details=json.dumps(updates),
            )
            logger.info(f"Updated FUB task {fub_task_id} from Todoist: {list(updates.keys())}")

        # Update mapping timestamps
        db.update_mapping(
            mapping['id'],
            todoist_updated_at=todoist_task.created_at,
            last_synced_at=datetime.now().isoformat(),
        )

        return fub_task_id if updates else None

    # ==========================================================================
    # Polling & Sync Cycles
    # ==========================================================================

    def poll_fub_changes(self) -> list[int]:
        """
        Poll FUB for changed tasks and sync to Todoist.

        Returns list of FUB task IDs that were synced.
        """
        # Get last poll timestamp
        last_poll = db.get_state('fub_last_poll')
        if last_poll:
            updated_after = datetime.fromisoformat(last_poll)
        else:
            # First run - sync tasks from last 24 hours
            updated_after = datetime.now() - timedelta(hours=24)

        logger.info(f"Polling FUB for changes since {updated_after}")

        # Get changed tasks
        try:
            tasks = self.fub.get_tasks(updated_after=updated_after)
        except Exception as e:
            logger.error(f"Failed to poll FUB: {e}")
            return []

        synced = []
        for task in tasks:
            try:
                result = self.sync_fub_task_to_todoist(task)
                if result:
                    synced.append(task.id)
            except Exception as e:
                logger.error(f"Failed to sync FUB task {task.id}: {e}")
                db.log_sync(
                    direction='fub_to_todoist',
                    action='error',
                    fub_task_id=task.id,
                    details=str(e),
                    status='error',
                )

        # Update last poll timestamp
        db.set_state('fub_last_poll', datetime.now().isoformat())

        logger.info(f"FUB poll complete: {len(tasks)} tasks checked, {len(synced)} synced")
        return synced

    def sync_mapped_task(self, fub_task_id: int) -> dict:
        """
        Sync a specific mapped task (by FUB ID).

        Returns dict with sync results.
        """
        mapping = db.get_mapping_by_fub_id(fub_task_id)
        if not mapping:
            return {'error': f'No mapping found for FUB task {fub_task_id}'}

        # Get both tasks
        fub_task = self.fub.get_task(fub_task_id)
        todoist_task = self.todoist.get_task(mapping['todoist_task_id'])

        result = {
            'fub_task_id': fub_task_id,
            'todoist_task_id': mapping['todoist_task_id'],
            'fub_updated': fub_task.updated,
            'mapping_fub_updated': mapping.get('fub_updated_at'),
            'changes': [],
        }

        # Check if FUB has changes
        if fub_task.updated != mapping.get('fub_updated_at'):
            synced = self._update_todoist_from_fub(fub_task, mapping)
            if synced:
                result['changes'].append('fub_to_todoist')

        return result


# Module-level instance
sync_engine = SyncEngine()
