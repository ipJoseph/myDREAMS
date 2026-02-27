"""Follow Up Boss API client for Linear Sync module.

This is a simplified version focused on task/deal operations needed for sync.
"""

import logging
import re
from typing import Optional
import httpx

from .config import config
from .models import FUBTask, FUBPerson, FUBDeal

logger = logging.getLogger(__name__)


class FUBClient:
    """HTTP client for Follow Up Boss API."""

    def __init__(self):
        self.base_url = config.FUB_BASE_URL
        self.api_key = config.FUB_API_KEY

    def _get_headers(self) -> dict:
        """Get request headers."""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        if config.FUB_SYSTEM_NAME:
            headers['X-System'] = config.FUB_SYSTEM_NAME
        if config.FUB_SYSTEM_KEY:
            headers['X-System-Key'] = config.FUB_SYSTEM_KEY
        return headers

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict = None,
        json_data: dict = None,
        timeout: int = 30,
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
                auth=(self.api_key, ''),
            )

            # Check rate limits
            remaining = response.headers.get('X-RateLimit-Remaining')
            if remaining and int(remaining) < 10:
                logger.warning(f"FUB rate limit low: {remaining}")

            response.raise_for_status()

            # Some endpoints return empty body
            if response.status_code == 204 or not response.text:
                return {}

            return response.json()

    def _audit_log(self, operation: str, endpoint: str, http_method: str, **kwargs):
        """Log a FUB write operation to the audit table."""
        try:
            from src.core.fub_audit import log_fub_write
            log_fub_write(module='linear_sync', operation=operation,
                          endpoint=endpoint, http_method=http_method, **kwargs)
        except Exception as e:
            logger.warning(f"Failed to write audit log: {e}")

    # =========================================================================
    # TASKS
    # =========================================================================

    def get_task(self, task_id: int) -> Optional[FUBTask]:
        """Get a specific task by ID."""
        try:
            data = self._request('GET', f'tasks/{task_id}')
            return FUBTask.from_api(data) if data else None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    def get_tasks(
        self,
        person_id: Optional[int] = None,
        include_completed: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FUBTask]:
        """Get tasks with optional filters."""
        params = {'limit': limit, 'offset': offset}
        if person_id:
            params['personId'] = person_id
        if not include_completed:
            params['status'] = 'incomplete'

        data = self._request('GET', 'tasks', params=params)
        tasks = data.get('tasks', [])
        return [FUBTask.from_api(t) for t in tasks]

    def create_task(
        self,
        person_id: int,
        name: str,
        task_type: str = 'Todo',
        due_date: Optional[str] = None,
        assigned_user_id: Optional[int] = None,
    ) -> FUBTask:
        """Create a new task.

        Note: FUB API does not support 'note' field on task creation.
        """
        payload = {
            'personId': person_id,
            'name': name,
            'type': task_type,
        }
        if due_date:
            payload['dueDate'] = due_date
        if assigned_user_id:
            payload['assignedUserId'] = assigned_user_id

        data = self._request('POST', 'tasks', json_data=payload)
        self._audit_log('create_task', 'tasks', 'POST',
                        fub_person_id=person_id, fub_entity_id=data.get('id'),
                        payload_summary=f'{task_type}: {name}')
        return FUBTask.from_api(data)

    def update_task(
        self,
        task_id: int,
        name: Optional[str] = None,
        task_type: Optional[str] = None,
        due_date: Optional[str] = None,
        note: Optional[str] = None,
    ) -> FUBTask:
        """Update an existing task."""
        payload = {}
        if name is not None:
            payload['name'] = name
        if task_type is not None:
            payload['type'] = task_type
        if due_date is not None:
            payload['dueDate'] = due_date
        if note is not None:
            payload['note'] = note

        data = self._request('PUT', f'tasks/{task_id}', json_data=payload)
        self._audit_log('update_task', f'tasks/{task_id}', 'PUT',
                        fub_entity_id=task_id,
                        payload_summary=str(payload)[:200])
        return FUBTask.from_api(data)

    def complete_task(self, task_id: int) -> FUBTask:
        """Mark a task as completed."""
        data = self._request('PUT', f'tasks/{task_id}', json_data={'isCompleted': True})
        self._audit_log('complete_task', f'tasks/{task_id}', 'PUT',
                        fub_entity_id=task_id,
                        payload_summary='isCompleted=True')
        return FUBTask.from_api(data)

    def delete_task(self, task_id: int) -> bool:
        """Delete a task."""
        try:
            self._request('DELETE', f'tasks/{task_id}')
            self._audit_log('delete_task', f'tasks/{task_id}', 'DELETE',
                            fub_entity_id=task_id)
            return True
        except httpx.HTTPStatusError:
            return False

    # =========================================================================
    # PEOPLE
    # =========================================================================

    def get_person(self, person_id: int) -> Optional[FUBPerson]:
        """Get a specific person by ID."""
        try:
            data = self._request('GET', f'people/{person_id}')
            return FUBPerson.from_api(data) if data else None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    def search_people(self, query: str, limit: int = 10) -> list[FUBPerson]:
        """Search for people by name, email, or phone."""
        # Handle apostrophes and special characters
        clean_query = re.sub(r"['\"]", '', query)

        params = {'q': clean_query, 'limit': limit}
        data = self._request('GET', 'people', params=params)
        people = data.get('people', [])
        return [FUBPerson.from_api(p) for p in people]

    def find_person_by_name(self, name: str) -> Optional[FUBPerson]:
        """Find a person by exact or partial name match."""
        results = self.search_people(name, limit=5)

        # Try exact match first
        name_lower = name.lower()
        for person in results:
            if person.name.lower() == name_lower:
                return person

        # Try partial match
        for person in results:
            if name_lower in person.name.lower():
                return person

        return results[0] if results else None

    # =========================================================================
    # DEALS
    # =========================================================================

    def get_deal(self, deal_id: int) -> Optional[FUBDeal]:
        """Get a specific deal by ID."""
        try:
            data = self._request('GET', f'deals/{deal_id}')
            return FUBDeal.from_api(data) if data else None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    def get_deals(
        self,
        person_id: Optional[int] = None,
        pipeline_id: Optional[int] = None,
        limit: int = 100,
    ) -> list[FUBDeal]:
        """Get deals with optional filters."""
        params = {'limit': limit}
        if person_id:
            params['personId'] = person_id
        if pipeline_id:
            params['pipelineId'] = pipeline_id

        data = self._request('GET', 'deals', params=params)
        deals = data.get('deals', [])
        return [FUBDeal.from_api(d) for d in deals]

    def get_deals_for_person(self, person_id: int) -> list[FUBDeal]:
        """Get all deals for a specific person."""
        return self.get_deals(person_id=person_id)

    # =========================================================================
    # PIPELINES
    # =========================================================================

    def get_pipelines(self) -> list[dict]:
        """Get all pipelines."""
        data = self._request('GET', 'pipelines')
        return data.get('pipelines', [])

    def get_pipeline_stages(self, pipeline_id: int) -> list[dict]:
        """Get stages for a pipeline."""
        data = self._request('GET', f'pipelines/{pipeline_id}')
        return data.get('stages', [])


# Module-level singleton
fub_client = FUBClient()
