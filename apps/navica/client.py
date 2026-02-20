"""
Navica MLS RESO Web API Client

Connects to Navica's Data Management REST API for both
IDX and Broker Back Office (BBO) data feeds.

API structure (discovered via live testing):
    Base URL:    https://navapi.navicamls.net/api/v2/{dataset_code}
    Endpoints:   /listing, /agent, /office, /openhouse, /lookup
    Auth:        Bearer token in Authorization header
    Pagination:  ?limit=N&offset=N  (max limit=200, default=10)
    Filtering:   Field names as query params (e.g., ?StandardStatus=Active&City=Asheville)
    Selection:   ?fields=Field1,Field2,...
    Ordering:    ?order=FieldName desc
    Response:    {"success": true, "status": 200, "bundle": [...], "total": N}

Media (photos) are embedded inline in listing responses. No $expand needed.

Environment variables:
    NAVICA_API_URL       - API base URL (default: https://navapi.navicamls.net)
    NAVICA_DATASET_CODE  - Dataset code (default: nav27 for Carolina Smokies AOR)
    NAVICA_IDX_TOKEN     - Bearer token for IDX feed
    NAVICA_BBO_TOKEN     - Bearer token for Broker Back Office feed

Usage:
    from apps.navica.client import NavicaClient

    client = NavicaClient.from_env(feed='idx')
    properties = client.fetch_properties(status='Active', city='Asheville')
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

import requests

import logging

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent


def load_env():
    """Load environment variables from .env file."""
    env_path = PROJECT_ROOT / '.env'
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip().strip('"\''))


class NavicaAPIError(Exception):
    """Base exception for Navica API errors."""
    pass


class NavicaAuthError(NavicaAPIError):
    """Authentication/authorization failure."""
    pass


class NavicaRateLimitError(NavicaAPIError):
    """Rate limit exceeded."""
    pass


class NavicaClient:
    """
    Client for Navica's Data Management REST API.

    Handles auth, query building, pagination (limit/offset), rate limiting, and retries.
    """

    DEFAULT_API_URL = "https://navapi.navicamls.net"
    DEFAULT_DATASET_CODE = "nav27"

    # Max records per page (API-enforced limit)
    MAX_PAGE_SIZE = 200

    # Resource endpoints (lowercase, as the API expects)
    RESOURCES = {
        'listing': '/listing',
        'agent': '/agent',
        'office': '/office',
        'openhouse': '/openhouse',
        'lookup': '/lookup',
    }

    def __init__(
        self,
        token: str,
        api_url: str = None,
        dataset_code: str = None,
        feed_type: str = 'idx',
        request_delay: float = 0.5,
        max_retries: int = 3,
        max_requests_per_run: int = 10000,
        timeout: int = 60,
    ):
        """
        Initialize Navica API client.

        Args:
            token: Bearer token for API access
            api_url: API base URL (defaults to DEFAULT_API_URL)
            dataset_code: Dataset code (defaults to DEFAULT_DATASET_CODE)
            feed_type: 'idx' for IDX feed or 'bbo' for Broker Back Office
            request_delay: Seconds between requests (rate limiting)
            max_retries: Max retry attempts for failed requests
            max_requests_per_run: Safety limit on total requests per run
            timeout: Request timeout in seconds
        """
        self.token = token
        self.base_url = (api_url or self.DEFAULT_API_URL).rstrip('/')
        self.dataset_code = dataset_code or self.DEFAULT_DATASET_CODE
        self.api_url = f"{self.base_url}/api/v2/{self.dataset_code}"
        self.feed_type = feed_type
        self.request_delay = request_delay
        self.max_retries = max_retries
        self.max_requests_per_run = max_requests_per_run
        self.timeout = timeout

        # Session with persistent auth headers
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json',
        })

        # Rate limiting state
        self.request_count = 0
        self.last_request_time = 0.0

        # Stats for current run
        self.stats = {
            'requests': 0,
            'records_fetched': 0,
            'errors': 0,
            'retries': 0,
        }

        logger.info(f"Navica API client initialized (feed={feed_type}, dataset={self.dataset_code}, url={self.api_url})")

    @classmethod
    def from_env(cls, feed: str = 'idx', **kwargs) -> 'NavicaClient':
        """
        Create client from environment variables.

        Args:
            feed: 'idx' or 'bbo' (selects which token to use)
            **kwargs: Additional arguments passed to constructor

        Raises:
            NavicaAuthError: If required token is not set
        """
        load_env()

        api_url = os.environ.get('NAVICA_API_URL', cls.DEFAULT_API_URL)
        dataset_code = os.environ.get('NAVICA_DATASET_CODE', cls.DEFAULT_DATASET_CODE)

        if feed == 'bbo':
            token = os.environ.get('NAVICA_BBO_TOKEN')
            if not token:
                raise NavicaAuthError(
                    "NAVICA_BBO_TOKEN not found in environment.\n"
                    "Contact your MLS board for Broker Back Office API access.\n"
                    "Add NAVICA_BBO_TOKEN=your_token to .env file"
                )
        else:
            token = os.environ.get('NAVICA_IDX_TOKEN')
            if not token:
                raise NavicaAuthError(
                    "NAVICA_IDX_TOKEN not found in environment.\n"
                    "Contact tom@navicamls.net for IDX API access.\n"
                    "Add NAVICA_IDX_TOKEN=your_token to .env file"
                )

        return cls(token=token, api_url=api_url, dataset_code=dataset_code,
                   feed_type=feed, **kwargs)

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)

        self.last_request_time = time.time()
        self.request_count += 1

        if self.request_count > self.max_requests_per_run:
            raise NavicaRateLimitError(
                f"Reached max requests per run ({self.max_requests_per_run}). "
                "Increase max_requests_per_run or run again later."
            )

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Make an HTTP request with retry and rate limiting.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full URL to request
            **kwargs: Passed to requests.Session.request()

        Returns:
            Response object

        Raises:
            NavicaAuthError: On 401/403
            NavicaRateLimitError: On 429
            NavicaAPIError: On other failures after retries
        """
        kwargs.setdefault('timeout', self.timeout)

        for attempt in range(self.max_retries):
            self._rate_limit()
            self.stats['requests'] += 1

            try:
                logger.debug(f"{method} {url} (attempt {attempt + 1})")
                response = self.session.request(method, url, **kwargs)

                if response.status_code == 200:
                    return response

                if response.status_code == 401:
                    raise NavicaAuthError("Authentication failed. Check your API token.")

                if response.status_code == 403:
                    raise NavicaAuthError(
                        f"Access denied. Your {self.feed_type.upper()} feed may not "
                        "have permission for this resource."
                    )

                if response.status_code == 429:
                    retry_after = response.headers.get('Retry-After')
                    wait_time = int(retry_after) if retry_after else min(2 ** attempt * 5, 120)
                    logger.warning(f"Rate limited. Waiting {wait_time}s before retry.")
                    time.sleep(wait_time)
                    self.stats['retries'] += 1
                    continue

                # Other server errors (5xx): retry with backoff
                if response.status_code >= 500:
                    wait_time = 2 ** attempt * 2
                    logger.warning(
                        f"Server error {response.status_code}. "
                        f"Retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries})"
                    )
                    time.sleep(wait_time)
                    self.stats['retries'] += 1
                    continue

                # Client error (4xx besides 401/403/429): don't retry
                raise NavicaAPIError(
                    f"API error {response.status_code}: {response.text[:500]}"
                )

            except requests.exceptions.Timeout:
                self.stats['errors'] += 1
                if attempt == self.max_retries - 1:
                    raise NavicaAPIError(f"Request timed out after {self.max_retries} attempts")
                wait_time = 2 ** attempt * 2
                logger.warning(f"Timeout. Retrying in {wait_time}s.")
                time.sleep(wait_time)

            except requests.exceptions.ConnectionError:
                self.stats['errors'] += 1
                if attempt == self.max_retries - 1:
                    raise NavicaAPIError(f"Connection failed after {self.max_retries} attempts")
                wait_time = 2 ** attempt * 2
                logger.warning(f"Connection error. Retrying in {wait_time}s.")
                time.sleep(wait_time)

        raise NavicaAPIError(f"Max retries ({self.max_retries}) exceeded")

    def get(self, endpoint: str, params: Dict[str, str] = None) -> Dict:
        """
        Make a GET request to an API endpoint.

        Args:
            endpoint: API path (e.g., '/listing')
            params: Query parameters

        Returns:
            Parsed JSON response
        """
        url = f"{self.api_url}{endpoint}"
        if params:
            url += "?" + urlencode(params)

        response = self._request('GET', url)
        return response.json()

    def get_all_pages(
        self,
        endpoint: str,
        params: Dict[str, str] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        max_records: Optional[int] = None,
        page_size: int = 200,
    ) -> List[Dict]:
        """
        Fetch all pages of results using limit/offset pagination.

        Args:
            endpoint: API resource endpoint (e.g., '/listing')
            params: Query parameters (filters, fields, order)
            progress_callback: Optional fn(page_num, total_records) called per page
            max_records: Stop after fetching this many records (safety limit)
            page_size: Records per page (max 200, API-enforced)

        Returns:
            List of all records across all pages
        """
        if params is None:
            params = {}

        page_size = min(page_size, self.MAX_PAGE_SIZE)
        params['limit'] = str(page_size)

        all_results = []
        offset = 0
        page = 0
        server_total = None

        while True:
            params['offset'] = str(offset)
            data = self.get(endpoint, params)

            if not data.get('success'):
                msg = data.get('bundle', {}).get('message', 'Unknown error')
                raise NavicaAPIError(f"API request failed: {msg}")

            results = data.get('bundle', [])
            if server_total is None:
                server_total = data.get('total', 0)

            all_results.extend(results)
            page += 1

            logger.info(f"Page {page}: {len(results)} records (total fetched: {len(all_results)}/{server_total})")

            if progress_callback:
                progress_callback(page, len(all_results))

            # Stop conditions
            if len(results) < page_size:
                break  # Last page (fewer results than requested)

            if max_records and len(all_results) >= max_records:
                logger.info(f"Reached max_records limit ({max_records}). Stopping pagination.")
                all_results = all_results[:max_records]
                break

            if server_total and len(all_results) >= server_total:
                break  # Fetched everything

            offset += page_size

        logger.info(f"Fetched {len(all_results)} records in {page} pages (server total: {server_total})")
        self.stats['records_fetched'] = len(all_results)
        return all_results

    # ---------------------------------------------------------------
    # Resource-specific fetch methods
    # ---------------------------------------------------------------

    def fetch_properties(
        self,
        status: Optional[str] = None,
        property_type: Optional[str] = None,
        select_fields: Optional[List[str]] = None,
        city: Optional[str] = None,
        county: Optional[str] = None,
        max_records: Optional[int] = None,
        order: Optional[str] = None,
        **extra_filters,
    ) -> List[Dict]:
        """
        Fetch property listings from Navica API.

        Args:
            status: Filter by StandardStatus (Active, Pending, Closed, etc.)
            property_type: Filter by PropertyType (Residential, Land, etc.)
            select_fields: Specific fields to return
            city: Filter by City
            county: Filter by CountyOrParish
            max_records: Stop after this many records
            order: Sort order (e.g., 'ModificationTimestamp desc')
            **extra_filters: Additional field=value filters

        Returns:
            List of property records
        """
        params = {}

        if status:
            params['StandardStatus'] = status
        if property_type:
            params['PropertyType'] = property_type
        if city:
            params['City'] = city
        if county:
            params['CountyOrParish'] = county
        if select_fields:
            params['fields'] = ','.join(select_fields)
        if order:
            params['order'] = order

        params.update(extra_filters)

        logger.info(f"Fetching properties (feed={self.feed_type})...")
        filter_desc = {k: v for k, v in params.items() if k not in ('fields', 'order', 'limit', 'offset')}
        if filter_desc:
            logger.info(f"  Filters: {filter_desc}")

        return self.get_all_pages('/listing', params, max_records=max_records)

    def fetch_agents(
        self,
        member_status: Optional[str] = None,
        office_mls_id: Optional[str] = None,
        max_records: Optional[int] = None,
        **extra_filters,
    ) -> List[Dict]:
        """
        Fetch agent/member records.

        Args:
            member_status: Filter by MemberStatus (Active, etc.)
            office_mls_id: Filter by OfficeMlsId
            max_records: Stop after this many records
            **extra_filters: Additional field=value filters
        """
        params = {}
        if member_status:
            params['MemberStatus'] = member_status
        if office_mls_id:
            params['OfficeMlsId'] = office_mls_id
        params.update(extra_filters)

        logger.info("Fetching agents...")
        return self.get_all_pages('/agent', params, max_records=max_records)

    def fetch_offices(
        self,
        office_status: Optional[str] = None,
        max_records: Optional[int] = None,
        **extra_filters,
    ) -> List[Dict]:
        """Fetch office records."""
        params = {}
        if office_status:
            params['OfficeStatus'] = office_status
        params.update(extra_filters)

        logger.info("Fetching offices...")
        return self.get_all_pages('/office', params, max_records=max_records)

    def fetch_open_houses(
        self,
        listing_key: Optional[str] = None,
        max_records: Optional[int] = None,
        **extra_filters,
    ) -> List[Dict]:
        """
        Fetch open house records.

        Args:
            listing_key: Filter by ListingKey for a specific property
            max_records: Stop after this many records
            **extra_filters: Additional field=value filters
        """
        params = {}
        if listing_key:
            params['ListingKey'] = listing_key
        params.update(extra_filters)

        logger.info("Fetching open houses...")
        return self.get_all_pages('/openhouse', params, max_records=max_records)

    def fetch_lookups(
        self,
        resource_name: Optional[str] = None,
        lookup_name: Optional[str] = None,
        max_records: Optional[int] = None,
    ) -> List[Dict]:
        """
        Fetch lookup/enumeration values.

        Args:
            resource_name: Filter by ResourceName (e.g., 'Property', 'Member')
            lookup_name: Filter by LookupName (e.g., 'StandardStatus', 'PropertyType')
            max_records: Stop after this many records
        """
        params = {}
        if resource_name:
            params['ResourceName'] = resource_name
        if lookup_name:
            params['LookupName'] = lookup_name

        logger.info("Fetching lookups...")
        return self.get_all_pages('/lookup', params, max_records=max_records)

    # ---------------------------------------------------------------
    # Single record fetch
    # ---------------------------------------------------------------

    def get_listing_by_key(self, listing_key: str) -> Optional[Dict]:
        """
        Fetch a single listing by its ListingKey.

        Args:
            listing_key: The ListingKey (hash identifier)

        Returns:
            Listing record dict, or None if not found
        """
        url = f"{self.api_url}/listings/{listing_key}"
        try:
            response = self._request('GET', url)
            data = response.json()
            if data.get('success'):
                return data.get('bundle')
            return None
        except NavicaAPIError:
            return None

    # ---------------------------------------------------------------
    # Dataset info
    # ---------------------------------------------------------------

    def get_dataset_info(self) -> Dict:
        """
        Fetch dataset metadata (name, description, etc.)
        """
        url = f"{self.base_url}/api/v2/datasets/{self.dataset_code}"
        response = self._request('GET', url)
        data = response.json()
        if data.get('success'):
            return data.get('bundle', {})
        return {}

    def get_resource_count(self, resource: str, **filters) -> int:
        """
        Get the total count for a resource with optional filters.

        Args:
            resource: Resource name ('listing', 'agent', 'office', 'openhouse')
            **filters: Field=value filters

        Returns:
            Total record count
        """
        endpoint = self.RESOURCES.get(resource, f'/{resource}')
        params = dict(filters)
        params['limit'] = '1'

        data = self.get(endpoint, params)
        return data.get('total', 0) if data.get('success') else 0

    # ---------------------------------------------------------------
    # Connection test
    # ---------------------------------------------------------------

    def test_connection(self) -> bool:
        """
        Test API connection by fetching dataset info and a single listing.

        Returns:
            True if connection successful
        """
        logger.info(f"Testing Navica API connection ({self.feed_type} feed, dataset={self.dataset_code})...")
        try:
            # Test dataset access
            info = self.get_dataset_info()
            logger.info(f"  Dataset: {info.get('name', 'Unknown')}")

            # Test listing access
            data = self.get('/listing', {'limit': '1', 'StandardStatus': 'Active'})

            if data.get('success') and data.get('bundle'):
                prop = data['bundle'][0]
                total = data.get('total', 0)
                logger.info("Connection successful!")
                logger.info(f"  Active listings: {total:,}")
                logger.info(f"  ListingId: {prop.get('ListingId')}")
                logger.info(f"  Address: {prop.get('UnparsedAddress', 'N/A')}")
                logger.info(f"  Price: ${prop.get('ListPrice', 0):,}")
                logger.info(f"  Status: {prop.get('StandardStatus')}")
                logger.info(f"  City: {prop.get('City')}")
                return True
            elif data.get('success'):
                logger.info("Connection successful but no active listings found.")
                return True
            else:
                logger.error(f"API returned error: {data}")
                return False

        except NavicaAuthError as e:
            logger.error(f"Authentication failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False

    def get_stats(self) -> Dict[str, int]:
        """Return stats for the current run."""
        return dict(self.stats)

    def reset_stats(self):
        """Reset run statistics."""
        self.stats = {
            'requests': 0,
            'records_fetched': 0,
            'errors': 0,
            'retries': 0,
        }
        self.request_count = 0
