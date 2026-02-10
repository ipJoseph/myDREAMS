import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

import logging
logger = logging.getLogger(__name__)

from .cache import DataCache

from .exceptions import FUBError, FUBAPIError, RateLimitExceeded, DataValidationError


class FUBClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.followupboss.com/v1",
        request_sleep_seconds: float = 0.2,
        default_fetch_limit: int = 100,
        max_parallel_workers: int = 5,
        enable_stage_sync: bool = False,
        cache: Optional[DataCache] = None,
        logger=None,
    ):
        self.session = requests.Session()
        self.session.auth = (api_key, "")
        self.session.headers["Accept"] = "application/json"

        self.base_url = base_url
        self.request_sleep_seconds = request_sleep_seconds
        self.default_fetch_limit = default_fetch_limit
        self.max_parallel_workers = max_parallel_workers
        self.enable_stage_sync = enable_stage_sync

        self.logger = logger
        self.cache = cache

        if self.logger:
            self.logger.info("FUB API client initialized")

    def _fetch_with_retry(self, url: str, params: Dict = None, max_retries: int = 3) -> Dict:
        params = params or {}
        for attempt in range(max_retries):
            try:
                if self.logger:
                    self.logger.debug(f"GET {url} (attempt {attempt + 1}/{max_retries})")
                response = self.session.get(url, params=params, timeout=30)

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    wait_time = int(retry_after) if retry_after else min(2 ** attempt * 5, 60)
                    if self.logger:
                        self.logger.warning(f"Rate limited. Waiting {wait_time}s")
                    time.sleep(wait_time)
                    continue

                response.raise_for_status()
                return response.json()

            except requests.exceptions.Timeout:
                if self.logger:
                    self.logger.warning(f"Request timeout (attempt {attempt + 1}/{max_retries})")
                if attempt == max_retries - 1:
                    raise FUBAPIError(f"Request timeout after {max_retries} attempts")
                time.sleep(2 ** attempt)

            except requests.exceptions.HTTPError as e:
                if self.logger:
                    self.logger.error(f"HTTP error: {e}")
                if attempt == max_retries - 1:
                    raise FUBAPIError(f"HTTP error after {max_retries} attempts: {e}")
                time.sleep(2 ** attempt)

            except requests.exceptions.RequestException as e:
                if self.logger:
                    self.logger.error(f"Request error: {e}")
                if attempt == max_retries - 1:
                    raise FUBAPIError(f"Request failed after {max_retries} attempts: {e}")
                time.sleep(2 ** attempt)

        raise FUBAPIError(f"Max retries ({max_retries}) exceeded")

    def fetch_collection(self, path: str, collection_key: str, params: Dict = None, use_cache: bool = True) -> List[Dict]:
        cache_key = f"{path}_{json.dumps(params, sort_keys=True)}"

        if use_cache and self.cache:
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                if self.logger:
                    self.logger.info(f"Using cached data for {path}")
                return cached_data

        all_items = []
        params = dict(params or {})
        params.setdefault("limit", self.default_fetch_limit)

        next_token = None
        page = 0

        if self.logger:
            self.logger.info(f"Fetching {path}...")

        while True:
            page += 1
            if next_token:
                params["next"] = next_token
                params.pop("offset", None)

            url = f"{self.base_url}{path}"
            data = self._fetch_with_retry(url, params)

            items = data.get(collection_key, [])
            all_items.extend(items)

            if self.logger and page % 5 == 0:
                self.logger.info(f"  {path}: page {page}, {len(all_items)} items so far")

            meta = data.get("_metadata", {})
            next_token = meta.get("next")
            if not next_token:
                break

            time.sleep(self.request_sleep_seconds)

        if self.logger:
            self.logger.info(f"✓ Fetched {len(all_items)} items from {path} ({page} pages)")

        if use_cache and self.cache:
            self.cache.set(cache_key, all_items)

        return all_items

    def fetch_people(self) -> List[Dict]:
        return self.fetch_collection("/people", "people", {"fields": "allFields", "includeTrash": "true"})

    def fetch_calls(self) -> List[Dict]:
        return self.fetch_collection("/calls", "calls")

    def fetch_events(self, limit: int = 100) -> List[Dict]:
        return self.fetch_collection("/events", "events", {"limit": limit})

    def fetch_text_messages_for_person(self, person_id: str) -> List[Dict]:
        params = {"personId": person_id, "limit": 100}
        try:
            return self.fetch_collection("/textMessages", "textMessages", params, use_cache=False)
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to fetch texts for person {person_id}: {e}")
            return []

    def fetch_text_messages_parallel(self, people: List[Dict]) -> List[Dict]:
        if self.logger:
            self.logger.info(f"Fetching text messages for {len(people)} people (parallel)...")

        all_texts: List[Dict] = []

        def fetch_for_person(person: Dict) -> List[Dict]:
            pid = person.get("id")
            if not pid:
                return []
            return self.fetch_text_messages_for_person(str(pid))

        with ThreadPoolExecutor(max_workers=self.max_parallel_workers) as executor:
            futures = {executor.submit(fetch_for_person, p): p for p in people}
            completed = 0
            for future in as_completed(futures):
                texts = future.result()
                if texts:
                    all_texts.extend(texts)
                completed += 1
                if self.logger and completed % 50 == 0:
                    self.logger.info(f"  Text messages: {completed}/{len(people)} people processed")

        if self.logger:
            self.logger.info(f"✓ Fetched {len(all_texts)} total text messages")
        return all_texts

    def fetch_emails_for_person(self, person_id: str) -> List[Dict]:
        """Fetch all emails for a specific person."""
        params = {"personId": person_id, "limit": 100}
        try:
            return self.fetch_collection("/emails", "emails", params, use_cache=False)
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Failed to fetch emails for person {person_id}: {e}")
            return []

    def fetch_emails_parallel(self, people: List[Dict]) -> List[Dict]:
        """Fetch emails for all people in parallel."""
        if self.logger:
            self.logger.info(f"Fetching emails for {len(people)} people (parallel)...")

        all_emails: List[Dict] = []

        def fetch_for_person(person: Dict) -> List[Dict]:
            pid = person.get("id")
            if not pid:
                return []
            return self.fetch_emails_for_person(str(pid))

        with ThreadPoolExecutor(max_workers=self.max_parallel_workers) as executor:
            futures = {executor.submit(fetch_for_person, p): p for p in people}
            completed = 0
            for future in as_completed(futures):
                emails = future.result()
                if emails:
                    all_emails.extend(emails)
                completed += 1
                if self.logger and completed % 50 == 0:
                    self.logger.info(f"  Emails: {completed}/{len(people)} people processed")

        if self.logger:
            self.logger.info(f"✓ Fetched {len(all_emails)} total emails")
        return all_emails

    def update_person_stage(self, person_id: str, new_stage: str):
        if not new_stage or not self.enable_stage_sync:
            return

        url = f"{self.base_url}/people/{person_id}"
        payload = {"stage": new_stage}
        try:
            response = self.session.put(url, json=payload, timeout=30)
            response.raise_for_status()
            if self.logger:
                self.logger.info(f"Updated stage for {person_id} → {new_stage}")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to update stage for {person_id}: {e}")

    def create_note(self, person_id: int, body: str, user_id: int = None) -> Optional[Dict]:
        """
        Create a note for a person in Follow Up Boss.

        Args:
            person_id: FUB person ID (integer)
            body: Note content
            user_id: Optional FUB user ID for attribution

        Returns:
            Created note dict on success, None on failure
        """
        url = f"{self.base_url}/notes"
        payload = {
            "personId": int(person_id),
            "body": body
        }

        if user_id:
            payload["userId"] = int(user_id)

        try:
            if self.logger:
                self.logger.debug(f"Creating note for person {person_id}")

            response = self.session.post(url, json=payload, timeout=30)

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "5")
                if self.logger:
                    self.logger.warning(f"Rate limited creating note. Retry after {retry_after}s")
                return None

            response.raise_for_status()
            result = response.json()

            if self.logger:
                self.logger.info(f"Created note for person {person_id}")

            return result

        except requests.exceptions.HTTPError as e:
            if self.logger:
                self.logger.error(f"HTTP error creating note for {person_id}: {e}")
            return None
        except requests.exceptions.RequestException as e:
            if self.logger:
                self.logger.error(f"Request error creating note for {person_id}: {e}")
            return None
        except Exception as e:
            if self.logger:
                self.logger.error(f"Unexpected error creating note for {person_id}: {e}")
            return None

    def create_task(
        self,
        person_id: int,
        name: str,
        task_type: str = 'Follow Up',
        due_date: Optional[str] = None,
        assigned_user_id: Optional[int] = None,
        priority: Optional[int] = None
    ) -> Optional[Dict]:
        """
        Create a task for a person in Follow Up Boss.

        Args:
            person_id: FUB person ID
            name: Task name/description
            task_type: Task type ('Follow Up', 'Call', 'Email', 'Text', 'Meeting', 'Other')
            due_date: Due date in YYYY-MM-DD format
            assigned_user_id: FUB user ID to assign to
            priority: Task priority (0=none, 1=high, 2=medium, 3=low)

        Returns:
            Created task dict on success, None on failure
        """
        url = f"{self.base_url}/tasks"
        payload = {
            "personId": int(person_id),
            "name": name,
            "type": task_type,
        }

        if due_date:
            payload["dueDate"] = due_date
        if assigned_user_id:
            payload["assignedUserId"] = int(assigned_user_id)
        if priority is not None:
            payload["priority"] = priority

        try:
            if self.logger:
                self.logger.debug(f"Creating task for person {person_id}: {name}")

            response = self.session.post(url, json=payload, timeout=30)

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "5")
                if self.logger:
                    self.logger.warning(f"Rate limited creating task. Retry after {retry_after}s")
                return None

            response.raise_for_status()
            result = response.json()

            if self.logger:
                self.logger.info(f"Created task for person {person_id}: {name}")

            return result

        except requests.exceptions.HTTPError as e:
            if self.logger:
                self.logger.error(f"HTTP error creating task for {person_id}: {e}")
            return None
        except requests.exceptions.RequestException as e:
            if self.logger:
                self.logger.error(f"Request error creating task for {person_id}: {e}")
            return None
        except Exception as e:
            if self.logger:
                self.logger.error(f"Unexpected error creating task for {person_id}: {e}")
            return None

    def fetch_users(self) -> List[Dict]:
        """
        Fetch all users (team members) from Follow Up Boss.

        Returns:
            List of user dicts with id, name, email, role, etc.
        """
        return self.fetch_collection("/users", "users", use_cache=False)

    def fetch_current_user(self) -> Optional[Dict]:
        """
        Fetch the currently authenticated user (me).

        Returns:
            User dict with id, name, email, role, etc.
        """
        url = f"{self.base_url}/me"
        try:
            data = self._fetch_with_retry(url)
            return data
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to fetch current user: {e}")
            return None
