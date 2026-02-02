"""
Follow Up Boss API client for Task Sync.

Handles tasks, deals, and people endpoints.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx

from .config import config
from .models import FUBTask, FUBDeal, FUBPipeline

logger = logging.getLogger(__name__)


class FUBClient:
    """Follow Up Boss API client."""

    def __init__(self):
        self.base_url = config.FUB_BASE_URL
        self.api_key = config.FUB_API_KEY

    def _get_headers(self) -> dict:
        """Get request headers."""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        # Add system identification if configured
        if config.FUB_SYSTEM_NAME:
            headers['X-System'] = config.FUB_SYSTEM_NAME
        if config.FUB_SYSTEM_KEY:
            headers['X-System-Key'] = config.FUB_SYSTEM_KEY
        return headers

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
        timeout: int = 30
    ) -> dict:
        """Make a request to the FUB API."""
        url = f"{self.base_url}/{endpoint}"
        headers = self._get_headers()

        with httpx.Client(timeout=timeout) as client:
            response = client.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_data,
                auth=(self.api_key, '')
            )

            # Check rate limits
            remaining = response.headers.get('X-RateLimit-Remaining')
            if remaining and int(remaining) < 10:
                logger.warning(f"FUB rate limit low: {remaining} remaining")

            response.raise_for_status()
            return response.json()

    # ==========================================================================
    # Tasks
    # ==========================================================================

    def get_tasks(
        self,
        person_id: Optional[int] = None,
        updated_after: Optional[datetime] = None,
        limit: int = 100
    ) -> list[FUBTask]:
        """Get tasks, optionally filtered."""
        params = {'limit': min(limit, 100)}

        if person_id:
            params['personId'] = person_id

        if updated_after:
            params['updatedAfter'] = updated_after.isoformat()

        data = self._request('GET', 'tasks', params=params)
        tasks = data.get('tasks', [])

        return [FUBTask.from_api(t) for t in tasks]

    def get_task(self, task_id: int) -> FUBTask:
        """Get a single task by ID."""
        data = self._request('GET', f'tasks/{task_id}')
        return FUBTask.from_api(data)

    def create_task(
        self,
        person_id: int,
        name: str,
        task_type: str = 'Follow Up',
        due_date: Optional[str] = None,
        assigned_user_id: Optional[int] = None
    ) -> FUBTask:
        """Create a new task."""
        task_data = {
            'personId': person_id,
            'name': name,
            'type': task_type,
        }

        if due_date:
            task_data['dueDate'] = due_date

        if assigned_user_id:
            task_data['assignedUserId'] = assigned_user_id

        data = self._request('POST', 'tasks', json_data=task_data)
        logger.info(f"Created FUB task {data['id']}: {name}")
        return FUBTask.from_api(data)

    def update_task(self, task_id: int, **kwargs) -> FUBTask:
        """Update a task."""
        # Map field names to API format
        field_map = {
            'name': 'name',
            'task_type': 'type',
            'due_date': 'dueDate',
            'is_completed': 'isCompleted',
            'assigned_user_id': 'assignedUserId',
        }

        update_data = {}
        for key, value in kwargs.items():
            api_key = field_map.get(key, key)
            if value is not None:
                # Convert bool to int for isCompleted
                if api_key == 'isCompleted':
                    value = 1 if value else 0
                update_data[api_key] = value

        data = self._request('PUT', f'tasks/{task_id}', json_data=update_data)
        logger.info(f"Updated FUB task {task_id}")
        return FUBTask.from_api(data)

    def complete_task(self, task_id: int) -> FUBTask:
        """Mark a task as completed."""
        return self.update_task(task_id, is_completed=True)

    def uncomplete_task(self, task_id: int) -> FUBTask:
        """Mark a task as not completed."""
        return self.update_task(task_id, is_completed=False)

    def delete_task(self, task_id: int) -> bool:
        """Delete a task."""
        self._request('DELETE', f'tasks/{task_id}')
        logger.info(f"Deleted FUB task {task_id}")
        return True

    # ==========================================================================
    # Deals
    # ==========================================================================

    def get_deals(
        self,
        person_id: Optional[int] = None,
        limit: int = 100
    ) -> list[FUBDeal]:
        """Get deals, optionally filtered by person."""
        params = {'limit': min(limit, 100)}

        if person_id:
            params['personId'] = person_id

        data = self._request('GET', 'deals', params=params)
        deals = data.get('deals', [])

        return [FUBDeal.from_api(d) for d in deals]

    def get_deal(self, deal_id: int) -> FUBDeal:
        """Get a single deal by ID."""
        data = self._request('GET', f'deals/{deal_id}')
        return FUBDeal.from_api(data)

    # ==========================================================================
    # Pipelines
    # ==========================================================================

    def get_pipelines(self) -> list[FUBPipeline]:
        """Get all deal pipelines with their stages."""
        data = self._request('GET', 'pipelines')
        pipelines = data.get('pipelines', [])
        return [FUBPipeline.from_api(p) for p in pipelines]

    # ==========================================================================
    # People
    # ==========================================================================

    def get_person(self, person_id: int) -> dict:
        """Get a person by ID."""
        return self._request('GET', f'people/{person_id}')

    def get_person_name(self, person_id: int) -> str:
        """Get a person's name by ID."""
        person = self.get_person(person_id)
        first = person.get('firstName', '')
        last = person.get('lastName', '')
        return f"{first} {last}".strip() or 'Unknown'

    def search_people(self, query: str, limit: int = 10) -> list[dict]:
        """
        Search for people by name, email, or phone.

        Returns list of matching people with id, name, email, phone.
        """
        params = {
            'query': query,
            'limit': min(limit, 100)
        }
        data = self._request('GET', 'people', params=params)
        people = data.get('people', [])

        results = []
        for p in people:
            first = p.get('firstName', '')
            last = p.get('lastName', '')
            name = f"{first} {last}".strip()

            results.append({
                'id': p['id'],
                'name': name,
                'email': p.get('emails', [{}])[0].get('value') if p.get('emails') else None,
                'phone': p.get('phones', [{}])[0].get('value') if p.get('phones') else None,
                'stage': p.get('stage'),
            })

        return results


# Module-level instance
fub_client = FUBClient()
