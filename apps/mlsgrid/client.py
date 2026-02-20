"""
MLS Grid RESO Web API Client

Connects to MLS Grid's OData-based RESO Web API for Canopy MLS data.
Canopy MLS (OriginatingSystemName = 'carolina') is a founding member of MLS Grid.

API documentation: https://docs.mlsgrid.com/
Rate limits: 2 req/sec, 7,200 req/hr, 40,000 req/day

Environment variables:
    MLSGRID_TOKEN       - Bearer token for API access
    MLSGRID_USE_DEMO    - Set to 'true' to use demo API (for testing)

Usage:
    from apps.mlsgrid.client import MLSGridClient

    client = MLSGridClient.from_env()
    properties = client.fetch_properties(status='Active')
"""

import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent

# API URLs
MLSGRID_BASE_URL = "https://api.mlsgrid.com/v2"
MLSGRID_DEMO_URL = "https://api-demo.mlsgrid.com/v2"

# Canopy MLS identifier in MLS Grid
CANOPY_SYSTEM_NAME = "carolina"

# Rate limiting (MLS Grid: 2/sec, 7200/hr, 40000/day)
DEFAULT_REQUEST_DELAY = 0.6  # seconds between requests (conservative)
MAX_REQUESTS_PER_RUN = 5000  # stay well under hourly limit


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


class MLSGridAPIError(Exception):
    """Base exception for MLS Grid API errors."""
    pass


class MLSGridAuthError(MLSGridAPIError):
    """Authentication/authorization failure."""
    pass


class MLSGridRateLimitError(MLSGridAPIError):
    """Rate limit exceeded (HTTP 429)."""
    pass


class MLSGridClient:
    """
    Client for MLS Grid RESO Web API (OData).

    Handles auth, OData query building, cursor-based pagination (@odata.nextLink),
    $expand=Media for photos, rate limiting, and retries.

    Key differences from Navica client:
    - OData protocol (not REST query params)
    - Cursor-based pagination via @odata.nextLink (not limit/offset)
    - $expand=Media to include photos (not inline)
    - OriginatingSystemName filter to select Canopy MLS
    - MlgCanView filter to exclude deleted records
    """

    def __init__(
        self,
        token: str,
        use_demo: bool = False,
        request_delay: float = DEFAULT_REQUEST_DELAY,
        max_retries: int = 3,
        max_requests_per_run: int = MAX_REQUESTS_PER_RUN,
        timeout: int = 60,
    ):
        """
        Initialize MLS Grid API client.

        Args:
            token: Bearer token for API access
            use_demo: Use demo API (for testing without production access)
            request_delay: Seconds between requests (rate limiting)
            max_retries: Max retry attempts for failed requests
            max_requests_per_run: Safety limit on total requests per run
            timeout: Request timeout in seconds
        """
        self.token = token
        self.base_url = MLSGRID_DEMO_URL if use_demo else MLSGRID_BASE_URL
        self.use_demo = use_demo
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

        mode = "DEMO" if use_demo else "PRODUCTION"
        logger.info(f"MLS Grid client initialized ({mode}, url={self.base_url})")

    @classmethod
    def from_env(cls, **kwargs) -> 'MLSGridClient':
        """
        Create client from environment variables.

        Raises:
            MLSGridAuthError: If MLSGRID_TOKEN is not set
        """
        load_env()

        token = os.environ.get('MLSGRID_TOKEN')
        if not token:
            raise MLSGridAuthError(
                "MLSGRID_TOKEN not found in environment.\n"
                "To get API access:\n"
                "1. Contact data@canopyrealtors.com\n"
                "2. Request MLS Grid API access for Jon Tharp Homes / Keller Williams\n"
                "3. Add MLSGRID_TOKEN=your_token to .env file"
            )

        use_demo = os.environ.get('MLSGRID_USE_DEMO', 'false').lower() == 'true'

        return cls(token=token, use_demo=use_demo, **kwargs)

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)

        self.last_request_time = time.time()
        self.request_count += 1

        if self.request_count > self.max_requests_per_run:
            raise MLSGridRateLimitError(
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
            MLSGridAuthError: On 401/403
            MLSGridRateLimitError: On 429
            MLSGridAPIError: On other failures after retries
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
                    raise MLSGridAuthError("Authentication failed. Check MLSGRID_TOKEN.")

                if response.status_code == 403:
                    raise MLSGridAuthError(
                        "Access denied. Your MLS Grid subscription may not include "
                        "Canopy MLS data, or your token may have expired."
                    )

                if response.status_code == 429:
                    retry_after = response.headers.get('Retry-After')
                    wait_time = int(retry_after) if retry_after else min(2 ** attempt * 5, 120)
                    logger.warning(f"Rate limited (429). Waiting {wait_time}s before retry.")
                    time.sleep(wait_time)
                    self.stats['retries'] += 1
                    continue

                # Server errors (5xx): retry with backoff
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
                raise MLSGridAPIError(
                    f"API error {response.status_code}: {response.text[:500]}"
                )

            except requests.exceptions.Timeout:
                self.stats['errors'] += 1
                if attempt == self.max_retries - 1:
                    raise MLSGridAPIError(f"Request timed out after {self.max_retries} attempts")
                wait_time = 2 ** attempt * 2
                logger.warning(f"Timeout. Retrying in {wait_time}s.")
                time.sleep(wait_time)

            except requests.exceptions.ConnectionError:
                self.stats['errors'] += 1
                if attempt == self.max_retries - 1:
                    raise MLSGridAPIError(f"Connection failed after {self.max_retries} attempts")
                wait_time = 2 ** attempt * 2
                logger.warning(f"Connection error. Retrying in {wait_time}s.")
                time.sleep(wait_time)

        raise MLSGridAPIError(f"Max retries ({self.max_retries}) exceeded")

    def get(self, endpoint: str, params: Dict[str, str] = None) -> Dict:
        """
        Make a GET request to an MLS Grid API endpoint.

        Args:
            endpoint: API path (e.g., '/Property')
            params: OData query parameters ($filter, $expand, $top, etc.)

        Returns:
            Parsed JSON response
        """
        url = f"{self.base_url}{endpoint}"
        if params:
            # OData params use $ prefix; urlencode with safe chars for OData syntax
            url += "?" + urlencode(params, safe="$'() ")

        response = self._request('GET', url)
        return response.json()

    def get_all_pages(
        self,
        endpoint: str,
        params: Dict[str, str] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        max_records: Optional[int] = None,
    ) -> List[Dict]:
        """
        Fetch all pages of results following @odata.nextLink cursor pagination.

        MLS Grid uses cursor-based pagination: each response includes an
        @odata.nextLink URL if more results are available. We follow this
        chain until no more pages exist.

        Args:
            endpoint: API resource endpoint (e.g., '/Property')
            params: OData query parameters
            progress_callback: Optional fn(page_num, total_records) called per page
            max_records: Stop after fetching this many records (safety limit)

        Returns:
            List of all records across all pages
        """
        all_results = []
        page = 0

        # First request
        data = self.get(endpoint, params)
        results = data.get('value', [])
        all_results.extend(results)
        page += 1
        logger.info(f"Page {page}: {len(results)} records (total: {len(all_results)})")

        if progress_callback:
            progress_callback(page, len(all_results))

        # Follow @odata.nextLink pagination
        while '@odata.nextLink' in data:
            if max_records and len(all_results) >= max_records:
                logger.info(f"Reached max_records limit ({max_records}). Stopping pagination.")
                all_results = all_results[:max_records]
                break

            next_url = data['@odata.nextLink']

            # The nextLink is a full URL; use it directly
            self._rate_limit()
            self.stats['requests'] += 1

            try:
                response = self.session.get(next_url, timeout=self.timeout)
                if response.status_code != 200:
                    logger.warning(f"Page {page + 1} failed ({response.status_code})")
                    break

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
    # OData filter builders
    # ---------------------------------------------------------------

    @staticmethod
    def _build_filter(
        status: Optional[str] = None,
        modified_since: Optional[datetime] = None,
        property_types: Optional[List[str]] = None,
        originating_system: str = CANOPY_SYSTEM_NAME,
    ) -> str:
        """
        Build an OData $filter string for property queries.

        Args:
            status: StandardStatus filter (Active, Pending, Closed, etc.)
            modified_since: Only records modified after this timestamp
            property_types: Filter by PropertyType(s)
            originating_system: MLS system name (default: carolina for Canopy)

        Returns:
            OData $filter string
        """
        clauses = [
            f"OriginatingSystemName eq '{originating_system}'",
            "MlgCanView eq true",  # Exclude deleted records
        ]

        if status:
            clauses.append(f"StandardStatus eq '{status}'")

        if modified_since:
            ts = modified_since.strftime('%Y-%m-%dT%H:%M:%S.00Z')
            clauses.append(f"ModificationTimestamp gt {ts}")

        if property_types:
            if len(property_types) == 1:
                clauses.append(f"PropertyType eq '{property_types[0]}'")
            else:
                type_clauses = " or ".join(
                    [f"PropertyType eq '{pt}'" for pt in property_types]
                )
                clauses.append(f"({type_clauses})")

        return " and ".join(clauses)

    # ---------------------------------------------------------------
    # Resource-specific fetch methods
    # ---------------------------------------------------------------

    def fetch_properties(
        self,
        status: Optional[str] = None,
        modified_since: Optional[datetime] = None,
        property_types: Optional[List[str]] = None,
        expand_media: bool = True,
        max_records: Optional[int] = None,
    ) -> List[Dict]:
        """
        Fetch property listings from Canopy MLS via MLS Grid.

        Args:
            status: Filter by StandardStatus (Active, Pending, Closed, etc.)
            modified_since: Only records modified after this timestamp
            property_types: Filter by PropertyType (Residential, Land, etc.)
            expand_media: Include Media (photos) in response
            max_records: Stop after this many records

        Returns:
            List of property records (RESO Data Dictionary fields)
        """
        filter_str = self._build_filter(
            status=status,
            modified_since=modified_since,
            property_types=property_types,
        )

        params = {"$filter": filter_str}

        if expand_media:
            params["$expand"] = "Media"

        logger.info(f"Fetching properties from Canopy MLS...")
        logger.info(f"  Filter: {filter_str}")

        return self.get_all_pages("/Property", params, max_records=max_records)

    def fetch_agents(
        self,
        member_status: Optional[str] = None,
        modified_since: Optional[datetime] = None,
        max_records: Optional[int] = None,
    ) -> List[Dict]:
        """
        Fetch agent/member records from Canopy MLS.

        Args:
            member_status: Filter by MemberStatus (Active, etc.)
            modified_since: Only records modified after this timestamp
            max_records: Stop after this many records
        """
        clauses = [
            f"OriginatingSystemName eq '{CANOPY_SYSTEM_NAME}'",
        ]

        if member_status:
            clauses.append(f"MemberStatus eq '{member_status}'")

        if modified_since:
            ts = modified_since.strftime('%Y-%m-%dT%H:%M:%S.00Z')
            clauses.append(f"ModificationTimestamp gt {ts}")

        params = {"$filter": " and ".join(clauses)}

        logger.info("Fetching agents from Canopy MLS...")
        return self.get_all_pages("/Member", params, max_records=max_records)

    def fetch_offices(
        self,
        modified_since: Optional[datetime] = None,
        max_records: Optional[int] = None,
    ) -> List[Dict]:
        """Fetch office records from Canopy MLS."""
        clauses = [
            f"OriginatingSystemName eq '{CANOPY_SYSTEM_NAME}'",
        ]

        if modified_since:
            ts = modified_since.strftime('%Y-%m-%dT%H:%M:%S.00Z')
            clauses.append(f"ModificationTimestamp gt {ts}")

        params = {"$filter": " and ".join(clauses)}

        logger.info("Fetching offices from Canopy MLS...")
        return self.get_all_pages("/Office", params, max_records=max_records)

    def fetch_open_houses(
        self,
        modified_since: Optional[datetime] = None,
        max_records: Optional[int] = None,
    ) -> List[Dict]:
        """Fetch open house records from Canopy MLS."""
        clauses = [
            f"OriginatingSystemName eq '{CANOPY_SYSTEM_NAME}'",
        ]

        if modified_since:
            ts = modified_since.strftime('%Y-%m-%dT%H:%M:%S.00Z')
            clauses.append(f"ModificationTimestamp gt {ts}")

        params = {"$filter": " and ".join(clauses)}

        logger.info("Fetching open houses from Canopy MLS...")
        return self.get_all_pages("/OpenHouse", params, max_records=max_records)

    # ---------------------------------------------------------------
    # Connection test
    # ---------------------------------------------------------------

    def test_connection(self) -> bool:
        """
        Test API connection by fetching a single Canopy MLS property.

        Returns:
            True if connection successful
        """
        mode = "DEMO" if self.use_demo else "PRODUCTION"
        logger.info(f"Testing MLS Grid API connection ({mode})...")

        try:
            filter_str = self._build_filter(status='Active')
            data = self.get("/Property", {
                "$filter": filter_str,
                "$top": "1",
            })

            if 'value' in data and len(data['value']) > 0:
                prop = data['value'][0]
                logger.info("Connection successful!")
                logger.info(f"  ListingId: {prop.get('ListingId')}")
                addr = prop.get('UnparsedAddress') or f"{prop.get('StreetNumber', '')} {prop.get('StreetName', '')}"
                logger.info(f"  Address: {addr}")
                logger.info(f"  Price: ${prop.get('ListPrice', 0):,}")
                logger.info(f"  Status: {prop.get('StandardStatus')}")
                logger.info(f"  City: {prop.get('City')}")
                return True
            elif 'value' in data:
                logger.info("Connection successful but no data returned.")
                logger.info("This may be normal if you don't have Canopy MLS access yet.")
                return True
            else:
                logger.error(f"Unexpected response format: {list(data.keys())}")
                return False

        except MLSGridAuthError as e:
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
