"""
Dashboard integration for Task Sync.

Provides functions to fetch and format task data for the dashboard.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from .config import config
from .db import db
from .todoist_client import todoist_client
from .fub_client import fub_client

logger = logging.getLogger(__name__)


def get_todoist_tasks_for_dashboard(limit: int = 10) -> list[dict]:
    """
    Get active Todoist tasks formatted for dashboard display.

    Returns tasks with FUB person context where available.
    """
    try:
        # Fetch active tasks from Todoist
        todoist_tasks = todoist_client.get_tasks()

        # Filter to non-completed and sort by due date
        active_tasks = [t for t in todoist_tasks if not t.is_completed]

        # Sort: overdue first, then by due date, then by priority
        def sort_key(task):
            if task.due_date:
                try:
                    due = datetime.fromisoformat(task.due_date.replace('Z', '+00:00'))
                    return (0, due, -task.priority)
                except:
                    pass
            return (1, datetime.max, -task.priority)

        active_tasks.sort(key=sort_key)

        # Enrich with FUB data from mappings
        result = []
        for task in active_tasks[:limit]:
            mapping = db.get_mapping_by_todoist_id(task.id)

            task_data = {
                'todoist_id': task.id,
                'content': task.content,
                'description': task.description,
                'due_date': task.due_date,
                'due_datetime': task.due_datetime,
                'priority': task.priority,
                'labels': task.labels,
                'project_id': task.project_id,
                'is_overdue': False,
                # FUB context (from mapping)
                'fub_task_id': None,
                'fub_person_id': None,
                'fub_deal_id': None,
                'person_name': None,
                'deal_stage': None,
            }

            # Check if overdue
            if task.due_date:
                try:
                    due = datetime.fromisoformat(task.due_date)
                    if due.date() < datetime.now().date():
                        task_data['is_overdue'] = True
                except:
                    pass

            # Add FUB context if mapped
            if mapping:
                task_data['fub_task_id'] = mapping.get('fub_task_id')
                task_data['fub_person_id'] = mapping.get('fub_person_id')
                task_data['fub_deal_id'] = mapping.get('fub_deal_id')

                # Try to get person name from cache
                if mapping.get('fub_deal_id'):
                    deal = db.get_cached_deal(mapping['fub_deal_id'])
                    if deal:
                        task_data['person_name'] = deal.get('person_name')
                        task_data['deal_stage'] = deal.get('stage_name')

            # Extract person name from task content if not found
            # Format is "Task Name [Person Name]"
            if not task_data['person_name'] and ' [' in task.content and task.content.endswith(']'):
                try:
                    name_part = task.content.rsplit(' [', 1)[1].rstrip(']')
                    if name_part:
                        task_data['person_name'] = name_part
                except:
                    pass

            result.append(task_data)

        return result

    except Exception as e:
        logger.error(f"Failed to fetch Todoist tasks for dashboard: {e}")
        return []


def get_task_stats() -> dict:
    """
    Get task statistics for dashboard summary.

    Returns counts of tasks by status.
    """
    try:
        todoist_tasks = todoist_client.get_tasks()
        active = [t for t in todoist_tasks if not t.is_completed]

        now = datetime.now().date()
        overdue = 0
        due_today = 0
        due_this_week = 0

        for task in active:
            if task.due_date:
                try:
                    due = datetime.fromisoformat(task.due_date).date()
                    if due < now:
                        overdue += 1
                    elif due == now:
                        due_today += 1
                    elif due <= now + timedelta(days=7):
                        due_this_week += 1
                except:
                    pass

        return {
            'total_active': len(active),
            'overdue': overdue,
            'due_today': due_today,
            'due_this_week': due_this_week,
        }

    except Exception as e:
        logger.error(f"Failed to get task stats: {e}")
        return {
            'total_active': 0,
            'overdue': 0,
            'due_today': 0,
            'due_this_week': 0,
        }


def get_grouped_tasks(limit: int = 15) -> dict:
    """
    Get tasks grouped by urgency for dashboard display.

    Returns dict with 'overdue', 'today', and 'upcoming' lists.
    """
    tasks = get_todoist_tasks_for_dashboard(limit=limit)
    now = datetime.now().date()

    grouped = {
        'overdue': [],
        'today': [],
        'upcoming': [],
    }

    for task in tasks:
        if task['is_overdue']:
            grouped['overdue'].append(task)
        elif task.get('due_date'):
            try:
                due = datetime.fromisoformat(task['due_date']).date()
                if due == now:
                    grouped['today'].append(task)
                else:
                    grouped['upcoming'].append(task)
            except:
                grouped['upcoming'].append(task)
        else:
            grouped['upcoming'].append(task)

    return grouped


def get_tasks_by_project(limit: int = 20) -> dict:
    """
    Get tasks grouped by Todoist project for dashboard display.

    Returns dict with:
    - 'projects': list of {id, name, color, tasks: [...]}
    - 'total_count': total number of tasks
    - 'overdue_count': number of overdue tasks
    """
    try:
        # Fetch all projects
        projects_raw = todoist_client.get_projects()
        project_map = {p['id']: p for p in projects_raw}

        # Fetch tasks
        tasks = get_todoist_tasks_for_dashboard(limit=limit)

        # Group by project
        projects_with_tasks = {}
        overdue_count = 0

        for task in tasks:
            project_id = task.get('project_id')
            if not project_id:
                project_id = 'inbox'

            if project_id not in projects_with_tasks:
                project_info = project_map.get(project_id, {})
                projects_with_tasks[project_id] = {
                    'id': project_id,
                    'name': project_info.get('name', 'Inbox'),
                    'color': project_info.get('color', 'grey'),
                    'tasks': [],
                }

            projects_with_tasks[project_id]['tasks'].append(task)

            if task.get('is_overdue'):
                overdue_count += 1

        # Sort projects by task count (most tasks first), then by name
        sorted_projects = sorted(
            projects_with_tasks.values(),
            key=lambda p: (-len(p['tasks']), p['name'])
        )

        return {
            'projects': sorted_projects,
            'total_count': len(tasks),
            'overdue_count': overdue_count,
        }

    except Exception as e:
        logger.error(f"Failed to get tasks by project: {e}")
        return {
            'projects': [],
            'total_count': 0,
            'overdue_count': 0,
        }


def enrich_task_with_deal(fub_task_id: int, person_id: int) -> Optional[dict]:
    """
    Fetch and cache deal information for a task.

    Called during sync to populate deal context.
    """
    try:
        # Get deals for this person
        deals = fub_client.get_deals(person_id=person_id)

        if not deals:
            return None

        # Use the most recent active deal
        active_deal = deals[0]  # Already sorted by updated desc

        # Get person info for caching
        person = fub_client.get_person(person_id)
        person_name = f"{person.get('firstName', '')} {person.get('lastName', '')}".strip()

        # Cache the deal with person info
        deal_data = {
            'id': active_deal.id,
            'person_id': active_deal.person_id,
            'pipeline_id': active_deal.pipeline_id,
            'stage_id': active_deal.stage_id,
            'stage_name': active_deal.stage_name,
            'deal_name': active_deal.name,
            'deal_value': active_deal.deal_value,
            'property_address': active_deal.property_address,
            'property_city': active_deal.property_city,
            'property_state': active_deal.property_state,
            'property_zip': active_deal.property_zip,
            'person_name': person_name,
            'person_email': person.get('emails', [{}])[0].get('value') if person.get('emails') else None,
            'person_phone': person.get('phones', [{}])[0].get('value') if person.get('phones') else None,
            'updated': active_deal.updated,
        }

        db.cache_deal(deal_data)

        return deal_data

    except Exception as e:
        logger.error(f"Failed to enrich task with deal: {e}")
        return None
