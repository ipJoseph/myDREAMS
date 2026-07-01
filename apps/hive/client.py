"""
Hive (SourceRE) RESO Web API Client

Connects to SourceRE's OData API for Mountain Lakes Board of REALTORS® data.
Replaces the Navica nav26 feed as of 2026-06-30.

API docs: https://docs.sourceredb.com/
Rate limits: 3 req/s, 5,000 req/hr, no concurrent requests

Environment variables:
    HIVE_TOKEN  - Bearer token (1-year lifetime, issued 2026-06-30)

Usage:
    from apps.hive.client import HiveClient
    client = HiveClient.from_env()
    properties = client.fetch_properties(modified_since=datetime(...))
"""

import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent

BASE_URL = "https://api.sourceredb.com/odata"

# Mountain Lakes Board of REALTORS® as it appears in ListAOR
ML_AOR = "Mountain Lakes Board of REALTORS®"

# 3 req/s limit; 0.38s gap keeps us comfortably under with no cross-process
# throttle needed (single cron process, generous ceiling vs MLS Grid's 2 req/s)
REQUEST_DELAY = 0.38


class HiveAPIError(Exception):
    pass


class HiveAuthError(HiveAPIError):
    pass


class HiveRateLimitError(HiveAPIError):
    pass


class HiveClient:
    """
    Client for SourceRE RESO Web API (OData).

    Key differences vs MLS Grid client:
    - Scoped by ListAOR (not OriginatingSystemName)
    - Deletion via DeletedInSource flag (not MlgCanView)
    - APIModificationTimestamp for true server-side incrementals
    - 3 req/s ceiling (vs 2 req/s for MLS Grid)
    - No shared cross-process throttle needed
    """

    def __init__(
        self,
        token: str,
        request_delay: float = REQUEST_DELAY,
        max_retries: int = 3,
        timeout=(10, 60),
    ):
        self.token = token
        self.request_delay = request_delay
        self.max_retries = max_retries
        self.timeout = (10, float(timeout)) if isinstance(timeout, (int, float)) else timeout
        self.last_request_time = 0.0

        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip,deflate',
        })

        self.stats = {'requests': 0, 'records_fetched': 0, 'errors': 0, 'retries': 0}
        logger.info(f"Hive client initialized (url={BASE_URL})")

    @classmethod
    def from_env(cls, **kwargs) -> 'HiveClient':
        token = os.environ.get('HIVE_TOKEN')
        if not token:
            raise HiveAuthError(
                "HIVE_TOKEN not found in environment. "
                "Add HIVE_TOKEN=<bearer_token> to .env file."
            )
        return cls(token=token, **kwargs)

    def _rate_limit(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self.last_request_time = time.time()

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault('timeout', self.timeout)

        for attempt in range(self.max_retries):
            self._rate_limit()
            self.stats['requests'] += 1

            try:
                response = self.session.request(method, url, **kwargs)

                if response.status_code == 200:
                    return response

                if response.status_code in (401, 403):
                    raise HiveAuthError(
                        f"Auth failed ({response.status_code}). "
                        "Check HIVE_TOKEN — it expires 2027-06-30."
                    )

                if response.status_code == 429:
                    wait = int(response.headers.get('Retry-After', min(2 ** attempt * 5, 120)))
                    logger.warning(f"Rate limited (429). Waiting {wait}s.")
                    time.sleep(wait)
                    self.stats['retries'] += 1
                    continue

                if response.status_code >= 500:
                    wait = 2 ** attempt * 2
                    logger.warning(f"Server error {response.status_code}. Retry in {wait}s.")
                    time.sleep(wait)
                    self.stats['retries'] += 1
                    continue

                raise HiveAPIError(f"API error {response.status_code}: {response.text[:500]}")

            except requests.exceptions.Timeout:
                self.stats['errors'] += 1
                if attempt == self.max_retries - 1:
                    raise HiveAPIError("Request timed out")
                time.sleep(2 ** attempt * 2)

            except requests.exceptions.ConnectionError:
                self.stats['errors'] += 1
                if attempt == self.max_retries - 1:
                    raise HiveAPIError("Connection failed")
                time.sleep(2 ** attempt * 2)

        raise HiveAPIError(f"Max retries ({self.max_retries}) exceeded")

    def get(self, endpoint: str, params: Dict = None) -> Dict:
        url = f"{BASE_URL}{endpoint}"
        response = self._request('GET', url, params=params)
        return response.json()

    def get_all_pages(
        self,
        endpoint: str,
        params: Dict = None,
        max_records: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[Dict]:
        """Fetch all pages following @odata.nextLink cursor pagination."""
        all_results = []
        page = 0

        data = self.get(endpoint, params)
        results = data.get('value', [])
        all_results.extend(results)
        page += 1
        logger.info(f"Page {page}: {len(results)} records (total: {len(all_results)})")
        if progress_callback:
            progress_callback(page, len(all_results))

        while '@odata.nextLink' in data:
            if max_records and len(all_results) >= max_records:
                all_results = all_results[:max_records]
                break

            # Route through _request() so pages 2+ get the same retry,
            # backoff, and 429/5xx handling as page 1.
            try:
                response = self._request('GET', data['@odata.nextLink'])
                data = response.json()
                results = data.get('value', [])
                all_results.extend(results)
                page += 1
                logger.info(f"Page {page}: {len(results)} records (total: {len(all_results)})")
                if progress_callback:
                    progress_callback(page, len(all_results))
            except Exception as e:
                logger.error(f"Error fetching page {page + 1}: {e}")
                break

        logger.info(f"Fetched {len(all_results)} records in {page} pages")
        self.stats['records_fetched'] = len(all_results)
        return all_results

    # ---------------------------------------------------------------
    # Filter builder
    # ---------------------------------------------------------------

    @staticmethod
    def _build_filter(
        modified_since: Optional[datetime] = None,
        status: Optional[str] = None,
        include_deleted: bool = False,
    ) -> str:
        """Build OData $filter string for Mountain Lakes property queries."""
        clauses = [f"ListAOR eq '{ML_AOR}'"]

        # Most records have DeletedInSource=null (not false), so use 'ne true'
        # to correctly include null-valued records (active listings).
        if not include_deleted:
            clauses.append("DeletedInSource ne true")

        if status:
            clauses.append(f"StandardStatus eq '{status}'")

        if modified_since:
            ts = modified_since.strftime('%Y-%m-%dT%H:%M:%S.000Z')
            # APIModificationTimestamp is SourceRE's own watermark — more reliable
            # than ModificationTimestamp (which reflects the MLS system's timestamp)
            clauses.append(f"APIModificationTimestamp gt {ts}")

        return " and ".join(clauses)

    # ---------------------------------------------------------------
    # Resource fetchers
    # ---------------------------------------------------------------

    def fetch_properties(
        self,
        modified_since: Optional[datetime] = None,
        status: Optional[str] = None,
        expand_media: bool = True,
        include_deleted: bool = False,
        max_records: Optional[int] = None,
    ) -> List[Dict]:
        """
        Fetch Mountain Lakes property listings from SourceRE.

        Args:
            modified_since: Server-side timestamp filter (APIModificationTimestamp).
                            Hive supports this natively — true incremental syncs.
            status: StandardStatus filter (Active, Pending, etc.)
            expand_media: Include Media (photos) inline via $expand
            include_deleted: Include records with DeletedInSource=true
            max_records: Safety cap on total records
        """
        filter_str = self._build_filter(
            modified_since=modified_since,
            status=status,
            include_deleted=include_deleted,
        )

        params = {"$filter": filter_str}
        if expand_media:
            params["$expand"] = "Media"

        logger.info("Fetching properties from Mountain Lakes (Hive)...")
        logger.info(f"  Filter: {filter_str}")

        return self.get_all_pages("/Property", params, max_records=max_records)

    def fetch_media_for_listing(self, listing_key: str) -> List[Dict]:
        """Fetch fresh Media for a single listing by ListingKey."""
        try:
            data = self.get("/Media", {
                "$filter": f"ResourceRecordKey eq '{listing_key}'",
                "$orderby": "Order asc",
            })
            return data.get('value', [])
        except Exception as e:
            logger.warning(f"Failed to fetch media for {listing_key}: {e}")
        return []

    def fetch_agents(
        self,
        modified_since: Optional[datetime] = None,
        max_records: Optional[int] = None,
    ) -> List[Dict]:
        """Fetch Mountain Lakes agent/member records."""
        # SourceRE Member entity doesn't have ListOfficeMlsId — use MemberAOR
        # to scope to Mountain Lakes members only.
        clauses = [f"MemberAOR eq '{ML_AOR}'"]
        if modified_since:
            ts = modified_since.strftime('%Y-%m-%dT%H:%M:%S.000Z')
            clauses.append(f"ModificationTimestamp gt {ts}")
        params = {"$filter": " and ".join(clauses)}
        logger.info("Fetching agents from Mountain Lakes (Hive)...")
        return self.get_all_pages("/Member", params, max_records=max_records)

    def test_connection(self) -> bool:
        """Test API connectivity. Returns True on success."""
        logger.info("Testing Hive API connection...")
        try:
            data = self.get("/Property", {
                "$filter": self._build_filter(status='Active'),
                "$top": "1",
                "$count": "true",
            })
            count = data.get('@odata.count', 0)
            records = data.get('value', [])
            if records:
                r = records[0]
                logger.info(f"Connection OK — {count} active ML listings")
                logger.info(f"  Sample: {r.get('ListingId')} | {r.get('City')}, {r.get('CountyOrParish')} | ${r.get('ListPrice', 0):,.0f}")
                return True
            logger.info(f"Connection OK — {count} active ML listings (empty response)")
            return True
        except HiveAuthError as e:
            logger.error(f"Auth failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False

    def get_stats(self) -> Dict:
        return dict(self.stats)

    def reset_stats(self):
        self.stats = {'requests': 0, 'records_fetched': 0, 'errors': 0, 'retries': 0}
