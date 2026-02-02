"""
Todoist API client for Task Sync.

Supports REST API v2 and Sync API v1.
"""

import logging
from typing import Optional

import httpx

from .config import config
from .models import TodoistTask

logger = logging.getLogger(__name__)


class TodoistClient:
    """Todoist API client."""

    REST_BASE_URL = 'https://api.todoist.com/rest/v2'
    SYNC_BASE_URL = 'https://api.todoist.com/sync/v9'

    def __init__(self):
        self.api_token = config.TODOIST_API_TOKEN

    def _get_headers(self) -> dict:
        """Get request headers."""
        return {
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json',
        }

    def _rest_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
        timeout: int = 30
    ) -> dict:
        """Make a REST API request."""
        url = f"{self.REST_BASE_URL}/{endpoint}"
        headers = self._get_headers()

        with httpx.Client(timeout=timeout) as client:
            response = client.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_data,
            )
            response.raise_for_status()

            # Some endpoints return empty response
            if response.status_code == 204 or not response.content:
                return {}

            return response.json()

    def _sync_request(self, commands: list = None, resource_types: list = None, sync_token: str = '*') -> dict:
        """Make a Sync API request."""
        url = f"{self.SYNC_BASE_URL}/sync"
        headers = self._get_headers()

        data = {'sync_token': sync_token}

        if resource_types:
            data['resource_types'] = resource_types

        if commands:
            data['commands'] = commands

        with httpx.Client(timeout=30) as client:
            response = client.post(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()

    # ==========================================================================
    # Projects
    # ==========================================================================

    def get_projects(self) -> list[dict]:
        """Get all projects."""
        return self._rest_request('GET', 'projects')

    def get_project(self, project_id: str) -> dict:
        """Get a project by ID."""
        return self._rest_request('GET', f'projects/{project_id}')

    def create_project(self, name: str, parent_id: Optional[str] = None) -> dict:
        """Create a new project."""
        data = {'name': name}
        if parent_id:
            data['parent_id'] = parent_id

        project = self._rest_request('POST', 'projects', json_data=data)
        logger.info(f"Created Todoist project {project['id']}: {name}")
        return project

    # ==========================================================================
    # Sections
    # ==========================================================================

    def get_sections(self, project_id: Optional[str] = None) -> list[dict]:
        """Get sections, optionally filtered by project."""
        params = {}
        if project_id:
            params['project_id'] = project_id
        return self._rest_request('GET', 'sections', params=params)

    def create_section(self, name: str, project_id: str) -> dict:
        """Create a new section in a project."""
        data = {
            'name': name,
            'project_id': project_id,
        }
        section = self._rest_request('POST', 'sections', json_data=data)
        logger.info(f"Created Todoist section {section['id']}: {name}")
        return section

    # ==========================================================================
    # Tasks
    # ==========================================================================

    def get_tasks(self, project_id: Optional[str] = None, section_id: Optional[str] = None) -> list[TodoistTask]:
        """Get tasks, optionally filtered."""
        params = {}
        if project_id:
            params['project_id'] = project_id
        if section_id:
            params['section_id'] = section_id

        data = self._rest_request('GET', 'tasks', params=params)
        return [TodoistTask.from_api(t) for t in data]

    def get_task(self, task_id: str) -> TodoistTask:
        """Get a single task by ID."""
        data = self._rest_request('GET', f'tasks/{task_id}')
        return TodoistTask.from_api(data)

    def create_task(
        self,
        content: str,
        project_id: Optional[str] = None,
        section_id: Optional[str] = None,
        description: str = '',
        labels: Optional[list[str]] = None,
        priority: int = 1,
        due_string: Optional[str] = None,
        due_date: Optional[str] = None,
    ) -> TodoistTask:
        """Create a new task."""
        data = {'content': content}

        if project_id:
            data['project_id'] = project_id
        if section_id:
            data['section_id'] = section_id
        if description:
            data['description'] = description
        if labels:
            data['labels'] = labels
        if priority:
            data['priority'] = priority
        if due_string:
            data['due_string'] = due_string
        elif due_date:
            data['due_date'] = due_date

        task_data = self._rest_request('POST', 'tasks', json_data=data)
        logger.info(f"Created Todoist task {task_data['id']}: {content}")
        return TodoistTask.from_api(task_data)

    def update_task(self, task_id: str, **kwargs) -> TodoistTask:
        """Update a task."""
        data = self._rest_request('POST', f'tasks/{task_id}', json_data=kwargs)
        logger.info(f"Updated Todoist task {task_id}")
        return TodoistTask.from_api(data)

    def close_task(self, task_id: str) -> bool:
        """Mark a task as completed."""
        self._rest_request('POST', f'tasks/{task_id}/close')
        logger.info(f"Closed Todoist task {task_id}")
        return True

    def reopen_task(self, task_id: str) -> bool:
        """Reopen a completed task."""
        self._rest_request('POST', f'tasks/{task_id}/reopen')
        logger.info(f"Reopened Todoist task {task_id}")
        return True

    def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        self._rest_request('DELETE', f'tasks/{task_id}')
        logger.info(f"Deleted Todoist task {task_id}")
        return True

    def move_task(self, task_id: str, project_id: Optional[str] = None, section_id: Optional[str] = None) -> TodoistTask:
        """Move a task to a different project/section."""
        data = {}
        if project_id:
            data['project_id'] = project_id
        if section_id:
            data['section_id'] = section_id

        return self.update_task(task_id, **data)

    # ==========================================================================
    # Labels
    # ==========================================================================

    def get_labels(self) -> list[dict]:
        """Get all labels."""
        return self._rest_request('GET', 'labels')

    def create_label(self, name: str, color: Optional[str] = None) -> dict:
        """Create a new label."""
        data = {'name': name}
        if color:
            data['color'] = color

        label = self._rest_request('POST', 'labels', json_data=data)
        logger.info(f"Created Todoist label {label['id']}: {name}")
        return label

    # ==========================================================================
    # Sync API (for polling)
    # ==========================================================================

    def incremental_sync(self, sync_token: str = '*', resource_types: list = None) -> dict:
        """
        Perform an incremental sync.

        Args:
            sync_token: Token from previous sync, or '*' for full sync
            resource_types: List of types to sync, e.g. ['items', 'projects']

        Returns:
            Dict with sync_token and changed items
        """
        if resource_types is None:
            resource_types = ['items']  # 'items' = tasks in Sync API

        return self._sync_request(resource_types=resource_types, sync_token=sync_token)


# Module-level instance
todoist_client = TodoistClient()
