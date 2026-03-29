"""
Unified Listing Service

Shared listing query logic used by both the public API and the agent dashboard.
Both apps import this module directly (no HTTP proxy needed since they share
the same SQLite database on the same machine).

Usage:
    from src.core.listing_service import ListingService, ListingFilters

    service = ListingService(db_path)
    filters = ListingFilters(status='Active', city='Franklin')
    result = service.search_listings(filters)
"""

import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent

# ---------------------------------------------------------------------------
# Constants shared across public site and dashboard
# ---------------------------------------------------------------------------

MLS_DISPLAY_NAMES = {
    'NavicaMLS': 'Carolina Smokies MLS',
    'MountainLakesMLS': 'Mountain Lakes MLS',
    'CanopyMLS': 'Canopy MLS',
}

# Prefixes added by MLS feeds (e.g. CAR = Carolina region via MLS Grid)
_MLS_PREFIX_RE = re.compile(r'^(CAR|NCM|CARNCM)', re.IGNORECASE)


def strip_mls_prefix(mls_number: str) -> str:
    """Strip MLS source prefix (CAR, NCM) for clean display."""
    if not mls_number:
        return ''
    return _MLS_PREFIX_RE.sub('', str(mls_number))

MLS_PRIORITY = {
    'NavicaMLS': 1,
    'MountainLakesMLS': 2,
    'CanopyMLS': 3,
}

PHOTOS_DIRS = {
    'mlsgrid': PROJECT_ROOT / 'data' / 'photos' / 'mlsgrid',
    'canopy': PROJECT_ROOT / 'data' / 'photos' / 'mlsgrid',
    'navica': PROJECT_ROOT / 'data' / 'photos' / 'navica',
}

# Sort columns whitelisted against SQL injection
ALLOWED_SORT_COLUMNS = {
    'list_price', 'days_on_market', 'list_date', 'beds', 'baths',
    'sqft', 'acreage', 'elevation_feet', 'year_built', 'updated_at', 'city',
    'sold_date', 'sold_price', 'address', 'county', 'status',
    'captured_at', 'mls_number',
}

# Cross-MLS dedup subquery: for listings sharing the same address_key AND
# property_type, keep the one with highest MLS source priority (NavicaMLS >
# MountainLakesMLS > CanopyMLS). Ties broken by most recently updated.
DEDUP_CONDITION = (
    "(address_key IS NULL OR NOT EXISTS ("
    "SELECT 1 FROM listings dup "
    "WHERE dup.address_key = listings.address_key "
    "AND dup.property_type = listings.property_type "
    "AND dup.id != listings.id "
    "AND UPPER(dup.status) = UPPER(listings.status) "
    "AND ("
    "  CASE dup.mls_source WHEN 'NavicaMLS' THEN 1 WHEN 'MountainLakesMLS' THEN 2 WHEN 'CanopyMLS' THEN 3 ELSE 4 END"
    "  < CASE listings.mls_source WHEN 'NavicaMLS' THEN 1 WHEN 'MountainLakesMLS' THEN 2 WHEN 'CanopyMLS' THEN 3 ELSE 4 END"
    "  OR ("
    "    CASE dup.mls_source WHEN 'NavicaMLS' THEN 1 WHEN 'MountainLakesMLS' THEN 2 WHEN 'CanopyMLS' THEN 3 ELSE 4 END"
    "    = CASE listings.mls_source WHEN 'NavicaMLS' THEN 1 WHEN 'MountainLakesMLS' THEN 2 WHEN 'CanopyMLS' THEN 3 ELSE 4 END"
    "    AND dup.updated_at > listings.updated_at"
    "  )"
    ")))"
)


# ---------------------------------------------------------------------------
# Filter dataclass
# ---------------------------------------------------------------------------

@dataclass
class ListingFilters:
    """All filter parameters for listing queries.

    Common filters are shared between public site and dashboard.
    Some filters only apply to one consumer.
    """
    # Common filters
    status: Optional[str] = None
    city: Optional[str] = None          # single value or comma-separated
    county: Optional[str] = None        # single value or comma-separated (LIKE match)
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    min_beds: Optional[int] = None
    min_baths: Optional[float] = None
    min_sqft: Optional[int] = None
    min_acreage: Optional[float] = None
    max_dom: Optional[int] = None
    property_type: Optional[str] = None
    mls_source: Optional[str] = None
    q: Optional[str] = None             # free-text search

    # Public-site filters
    zone: Optional[str] = None          # comma-separated zone numbers, or "all"
    require_idx: bool = False           # enforce idx_opt_in = 1

    # Dashboard filters
    added_for: Optional[str] = None     # client filter
    bbo_only: bool = False              # BBO-only listings

    # Search field control: which columns free-text search checks.
    # None = use the default SEARCH_FIELDS_SINGLE/MULTI lists.
    # Provide an explicit list to narrow or widen the search scope.
    search_fields: Optional[List[str]] = None

    @classmethod
    def from_request(cls, request_args, defaults: Optional[Dict[str, Any]] = None) -> 'ListingFilters':
        """Build ListingFilters from Flask request.args with optional defaults."""
        d = defaults or {}

        def get(key, type_fn=None, default=None):
            val = request_args.get(key)
            if val is None or val == '':
                return d.get(key, default)
            if type_fn:
                try:
                    return type_fn(val)
                except (ValueError, TypeError):
                    return d.get(key, default)
            return val

        return cls(
            status=get('status'),
            city=get('city'),
            county=get('county'),
            min_price=get('min_price', int),
            max_price=get('max_price', int),
            min_beds=get('min_beds', int),
            min_baths=get('min_baths', float),
            min_sqft=get('min_sqft', int),
            min_acreage=get('min_acreage', float),
            max_dom=get('max_dom', int),
            property_type=get('property_type'),
            mls_source=get('mls_source'),
            q=get('q'),
            zone=get('zone'),
            require_idx=d.get('require_idx', False),
            added_for=get('client') or get('added_for'),
            bbo_only=(get('status') == 'BBO'),
        )


@dataclass
class SearchResult:
    """Container for paginated search results."""
    listings: List[Dict[str, Any]]
    total: int
    page: int
    limit: int

    @property
    def pages(self) -> int:
        if self.total == 0:
            return 0
        return (self.total + self.limit - 1) // self.limit


# ---------------------------------------------------------------------------
# Shared utility functions
# ---------------------------------------------------------------------------

def _resolve_photos_dir(listing: dict) -> tuple:
    """Determine photos directory for a listing. Returns (mls, photos_dir) or (None, None)."""
    mls = listing.get('mls_number')
    if not mls:
        return None, None
    source = (listing.get('photo_source') or listing.get('mls_source', '')).lower()
    if 'canopy' in source or 'mlsgrid' in source:
        return mls, PHOTOS_DIRS.get('mlsgrid')
    elif 'navica' in source or 'mountain' in source:
        return mls, PHOTOS_DIRS.get('navica')
    return mls, None


def _find_local_primary(mls: str, photos_dir: Path) -> str | None:
    """Find the primary photo file on disk, return local URL or None."""
    for ext in ('.jpg', '.jpeg', '.png', '.webp'):
        filepath = photos_dir / f"{mls}{ext}"
        if filepath.exists() and filepath.stat().st_size > 0:
            return f"/api/public/photos/{photos_dir.name}/{mls}{ext}"
    return None


def localize_photo(listing: dict, on_demand: bool = False) -> None:
    """Rewrite primary_photo and photos array to local URLs where files exist.

    Checks disk for primary ({mls}.ext) and gallery ({mls}_{NN}.ext) files.
    CDN URLs (especially MLS Grid tokens) expire, so local paths are
    always preferred. For listings with no local files, sets primary_photo
    to None and clears the photos array to avoid broken images.

    Args:
        listing: Dict with listing data (modified in place).
        on_demand: If True, fetch missing Canopy photos from the API using
            the throttle. Use for detail page views only, not bulk lists.
    """
    mls, photos_dir = _resolve_photos_dir(listing)
    if not mls:
        return

    if not photos_dir:
        if 'mlsgrid.com' in (listing.get('primary_photo') or ''):
            listing['primary_photo'] = None
        return

    # Localize primary photo
    local_primary = _find_local_primary(mls, photos_dir)

    # Build local gallery URLs from disk
    dir_name = photos_dir.name
    local_urls = []
    if local_primary:
        local_urls.append(local_primary)

    idx = 1
    while True:
        suffix = f"_{idx:02d}"
        found = False
        for ext in ('.jpg', '.jpeg', '.png', '.webp'):
            filepath = photos_dir / f"{mls}{suffix}{ext}"
            if filepath.exists() and filepath.stat().st_size > 0:
                local_urls.append(f"/api/public/photos/{dir_name}/{mls}{suffix}{ext}")
                found = True
                break
        if not found:
            break
        idx += 1

    if local_urls:
        # We have local files; use them
        listing['primary_photo'] = local_urls[0]
        photos = listing.get('photos')
        if isinstance(photos, list):
            listing['photos'] = local_urls
        return

    # No local files found.
    source_lower = (listing.get('mls_source') or '').lower()
    is_canopy = 'canopy' in source_lower or 'mlsgrid' in source_lower

    if is_canopy and on_demand:
        # Single throttled API request to fetch and download all photos.
        # Safe for one-off misses on detail page views.
        fetched = _fetch_and_download_photos_from_api(mls, photos_dir)
        if fetched:
            listing['primary_photo'] = fetched[0]
            listing['photos'] = fetched
            return

    if is_canopy:
        # Canopy with no local files and no on-demand: show nothing
        listing['primary_photo'] = None
        photos = listing.get('photos')
        if isinstance(photos, list) and any('mlsgrid.com' in (p or '') for p in photos):
            listing['photos'] = []
        return

    # Non-Canopy (Navica): CDN URLs don't expire, try download
    cdn_url = listing.get('primary_photo') or ''
    if cdn_url.startswith('http') and 'mlsgrid.com' not in cdn_url:
        local_path = _download_photo_url(mls, cdn_url, photos_dir)
        listing['primary_photo'] = local_path
    else:
        listing['primary_photo'] = None


def _fetch_and_download_photos_from_api(mls: str, photos_dir: Path) -> List[str]:
    """Fetch fresh photo URLs from MLS Grid API and download all photos.

    Uses the throttle to stay within rate limits. Safe for small-scale
    on-demand fetches (a few missing listings), not for bulk operations.
    Returns list of local URLs for downloaded photos, or empty list.
    """
    try:
        import requests as req
        from urllib.parse import urlparse
        from src.core.mlsgrid_throttle import get_throttle

        token = os.getenv('MLSGRID_TOKEN')
        if not token:
            return []

        throttle = get_throttle()
        throttle.wait()

        headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip,deflate',
        }
        api_url = (
            f"https://api.mlsgrid.com/v2/Property"
            f"?$filter=ListingId eq '{mls}'"
            f"&$expand=Media"
            f"&$top=1"
        )
        api_resp = req.get(api_url, headers=headers, timeout=10)
        throttle.record()

        if api_resp.status_code != 200:
            return []

        listings = api_resp.json().get('value', [])
        if not listings:
            return []

        media = listings[0].get('Media', [])
        if not media:
            return []

        # Extract and sort photos
        photos = []
        for m in media:
            cat = m.get('MediaCategory', '')
            if cat and cat != 'Photo':
                continue
            url = m.get('MediaURL')
            if url:
                order = m.get('Order', m.get('MediaOrder', 999))
                photos.append((order, url))
        photos.sort(key=lambda x: x[0])

        if not photos:
            return []

        # Download all photos to disk
        photos_dir.mkdir(parents=True, exist_ok=True)
        local_urls = []
        dir_name = photos_dir.name

        for idx, (_, photo_url) in enumerate(photos):
            path_lower = urlparse(photo_url).path.lower()
            ext = '.png' if path_lower.endswith('.png') else \
                  '.webp' if path_lower.endswith('.webp') else '.jpg'
            filename = f"{mls}{ext}" if idx == 0 else f"{mls}_{idx:02d}{ext}"
            filepath = photos_dir / filename

            if filepath.exists() and filepath.stat().st_size > 0:
                local_urls.append(f"/api/public/photos/{dir_name}/{filename}")
                continue

            try:
                resp = req.get(photo_url, timeout=30, stream=True)
                resp.raise_for_status()
                with open(filepath, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                if filepath.stat().st_size > 0:
                    local_urls.append(f"/api/public/photos/{dir_name}/{filename}")
                else:
                    filepath.unlink(missing_ok=True)
            except Exception as e:
                logger.debug(f"CDN download failed for {mls} [{idx}]: {e}")

        # Update DB with local paths
        if local_urls:
            try:
                import sqlite3 as _sql
                db_path = PROJECT_ROOT / 'data' / 'dreams.db'
                conn = _sql.connect(str(db_path), timeout=10)
                conn.execute('PRAGMA busy_timeout=10000')
                primary_path = str(photos_dir / f"{mls}.jpg")
                conn.execute(
                    "UPDATE listings SET photos = ?, photo_local_path = ? "
                    "WHERE mls_number = ?",
                    [json.dumps(local_urls), primary_path, mls]
                )
                conn.commit()
                conn.close()
            except Exception as e:
                logger.debug(f"DB update failed for {mls}: {e}")

        return local_urls

    except Exception as e:
        logger.debug(f"On-demand API photo fetch failed for {mls}: {e}")
    return []


def _download_photo_url(mls: str, url: str, photos_dir: Path) -> Optional[str]:
    """Download a photo from a URL and save it locally. Returns local URL or None."""
    try:
        import requests as req
        from urllib.parse import urlparse

        path_lower = urlparse(url).path.lower()
        ext = '.png' if path_lower.endswith('.png') else '.webp' if path_lower.endswith('.webp') else '.jpg'
        filename = f"{mls}{ext}"
        filepath = photos_dir / filename

        if filepath.exists() and filepath.stat().st_size > 0:
            return f"/api/public/photos/{photos_dir.name}/{filename}"

        photos_dir.mkdir(parents=True, exist_ok=True)
        resp = req.get(url, timeout=5, stream=True)
        resp.raise_for_status()
        with open(filepath, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        if filepath.stat().st_size > 0:
            return f"/api/public/photos/{photos_dir.name}/{filename}"
        else:
            filepath.unlink(missing_ok=True)
    except Exception as e:
        logger.debug(f"Photo download failed for {mls}: {e}")
    return None


def compute_dom(listing: dict) -> Optional[int]:
    """Compute Days on Market dynamically from list_date for active listings.

    For closed/expired/withdrawn, the stored value is the final DOM.
    For active/pending, recalculate from list_date.
    Falls back to stored days_on_market, then created_at as last resort.
    """
    status = (listing.get('status') or '').lower()
    stored = listing.get('days_on_market')

    if status in ('sold', 'withdrawn', 'terminated', 'expired', 'off market', 'closed'):
        return stored

    list_date_str = listing.get('list_date')
    if list_date_str:
        try:
            if 'T' in str(list_date_str):
                ld = datetime.fromisoformat(list_date_str.replace('Z', '+00:00'))
            else:
                ld = datetime.strptime(str(list_date_str)[:10], '%Y-%m-%d')
            return max(0, (datetime.now() - ld.replace(tzinfo=None)).days)
        except (ValueError, TypeError):
            pass

    if stored is not None:
        return stored

    # Last resort: calculate from created_at
    created_at_str = listing.get('created_at')
    if created_at_str:
        try:
            if 'T' in str(created_at_str):
                ca = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
            else:
                ca = datetime.strptime(str(created_at_str)[:10], '%Y-%m-%d')
            return max(0, (datetime.now() - ca.replace(tzinfo=None)).days)
        except (ValueError, TypeError):
            pass

    return None


def parse_mls_list(q: str) -> Optional[list]:
    """Detect and parse multiple MLS numbers from search input.

    Returns list of MLS numbers if input looks like a multi-MLS query,
    or None to fall through to normal LIKE search.
    Handles bare numeric MLS numbers (e.g. "4286259") as well as
    prefixed ones (e.g. "CAR4286259").
    """
    tokens = re.split(r'[,;\s]+', q.strip())
    tokens = [t.strip() for t in tokens if t.strip()]
    if len(tokens) < 2:
        return None
    for t in tokens:
        if not re.match(r'^[A-Za-z0-9\-]{4,15}$', t):
            return None
        if not re.search(r'\d', t):
            return None  # Pure alpha tokens are words, not MLS numbers
    return tokens


def row_to_dict(row, fields=None) -> Optional[dict]:
    """Convert sqlite3.Row to dict, optionally limiting to specified fields."""
    if row is None:
        return None
    d = dict(row)
    if fields:
        d = {k: v for k, v in d.items() if k in fields}
    return d


def _build_multi_where(conditions: list, params: list, column: str, value: str,
                       use_like: bool = False) -> None:
    """Append WHERE conditions for a potentially comma-separated multi-value filter.

    Modifies conditions and params lists in place.
    """
    if not value:
        return
    values = [v.strip() for v in value.split(',') if v.strip()]
    if not values:
        return
    if len(values) == 1:
        if use_like:
            conditions.append(f'{column} LIKE ?')
            params.append(f'%{values[0]}%')
        else:
            conditions.append(f'LOWER({column}) = LOWER(?)')
            params.append(values[0])
    else:
        if use_like:
            likes = ' OR '.join([f'{column} LIKE ?' for _ in values])
            conditions.append(f'({likes})')
            params.extend([f'%{v}%' for v in values])
        else:
            placeholders = ','.join(['LOWER(?)'] * len(values))
            conditions.append(f'LOWER({column}) IN ({placeholders})')
            params.extend(values)


# ---------------------------------------------------------------------------
# The unified search fields: superset of what both apps search against
# ---------------------------------------------------------------------------

# Single-word search checks all these columns
SEARCH_FIELDS_SINGLE = [
    'address', 'city', 'county', 'subdivision',
    'mls_number', 'listing_agent_name', 'public_remarks',
]

# Multi-word search checks these (skip public_remarks to avoid performance hit)
SEARCH_FIELDS_MULTI = [
    'address', 'city', 'county', 'subdivision',
    'mls_number', 'listing_agent_name',
]


# ---------------------------------------------------------------------------
# ListingService
# ---------------------------------------------------------------------------

class ListingService:
    """Unified listing query service.

    Both the public API and the dashboard import this directly.
    The public API passes require_idx=True and zone filters.
    The dashboard passes added_for, bbo_only, etc.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.getenv(
            'DREAMS_DB_PATH',
            str(PROJECT_ROOT / 'data' / 'dreams.db')
        )

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _build_conditions(self, filters: ListingFilters) -> tuple:
        """Build WHERE conditions and params from ListingFilters.

        Returns (conditions: list[str], params: list).
        """
        conditions = []
        params = []

        # IDX compliance (public site)
        if filters.require_idx:
            conditions.append("idx_opt_in = 1")

        # Zone filtering (public site)
        if filters.zone is not None:
            if filters.zone.lower() == 'all':
                conditions.append("state = 'NC'")
            else:
                zone_values = []
                for z in filters.zone.split(','):
                    z = z.strip()
                    if z.isdigit() and 1 <= int(z) <= 5:
                        zone_values.append(int(z))
                if zone_values:
                    placeholders = ','.join(['?'] * len(zone_values))
                    conditions.append(f"zone IN ({placeholders})")
                    params.extend(zone_values)
                else:
                    conditions.append("zone IN (1, 2)")

        # BBO-only (dashboard)
        if filters.bbo_only:
            conditions.append("feed_types = '[\"BBO\"]'")
            conditions.append("LOWER(status) = 'active'")
        else:
            # Status
            if filters.status:
                conditions.append("UPPER(status) = UPPER(?)")
                params.append(filters.status)

            # Client filter (dashboard)
            if filters.added_for:
                conditions.append("added_for LIKE ?")
                params.append(f'%{filters.added_for}%')

        # City
        if filters.city:
            _build_multi_where(conditions, params, 'city', filters.city)

        # County
        if filters.county:
            _build_multi_where(conditions, params, 'county', filters.county, use_like=True)

        # Price range
        if filters.min_price is not None:
            conditions.append("list_price >= ?")
            params.append(filters.min_price)
        if filters.max_price is not None:
            conditions.append("list_price <= ?")
            params.append(filters.max_price)

        # Beds/Baths/Sqft/Acreage
        if filters.min_beds is not None:
            conditions.append("beds >= ?")
            params.append(filters.min_beds)
        if filters.min_baths is not None:
            conditions.append("baths >= ?")
            params.append(filters.min_baths)
        if filters.min_sqft is not None:
            conditions.append("sqft >= ?")
            params.append(filters.min_sqft)
        if filters.min_acreage is not None:
            conditions.append("acreage >= ?")
            params.append(filters.min_acreage)

        # DOM filter (use list_date for accuracy)
        if filters.max_dom is not None:
            conditions.append("list_date >= date('now', ? || ' days')")
            params.append(str(-filters.max_dom))

        # Property type
        if filters.property_type:
            conditions.append("property_type = ?")
            params.append(filters.property_type)

        # MLS source
        if filters.mls_source:
            conditions.append("mls_source = ?")
            params.append(filters.mls_source)

        # Free-text search
        q = filters.q
        if q:
            mls_list = parse_mls_list(q)
            if mls_list:
                # Use LIKE matching so bare numbers (4286259) match
                # prefixed MLS numbers (CAR4286259) in the database.
                # Prefixed tokens (CAR4286259) get exact match.
                mls_conds = []
                for t in mls_list:
                    if t.isdigit():
                        mls_conds.append('mls_number LIKE ?')
                        params.append(f'%{t}')
                    else:
                        mls_conds.append('mls_number = ?')
                        params.append(t)
                conditions.append(f'({" OR ".join(mls_conds)})')
            else:
                # Use custom search fields if provided, otherwise defaults
                single_fields = filters.search_fields or SEARCH_FIELDS_SINGLE
                multi_fields = filters.search_fields or SEARCH_FIELDS_MULTI

                words = q.strip().split()
                if len(words) == 1:
                    search_term = f"%{words[0]}%"
                    field_conds = ' OR '.join([f'{f} LIKE ?' for f in single_fields])
                    conditions.append(f"({field_conds})")
                    params.extend([search_term] * len(single_fields))
                else:
                    word_conditions = []
                    for word in words:
                        wt = f"%{word}%"
                        field_conds = ' OR '.join([f'{f} LIKE ?' for f in multi_fields])
                        word_conditions.append(f"({field_conds})")
                        params.extend([wt] * len(multi_fields))
                    conditions.append("(" + " AND ".join(word_conditions) + ")")

        return conditions, params

    def search_listings(self, filters: ListingFilters, fields: Optional[List[str]] = None,
                        sort: str = 'list_date', order: str = 'desc',
                        page: int = 1, limit: int = 24,
                        dedup: bool = True) -> SearchResult:
        """Search listings with filtering, sorting, pagination, and dedup.

        Args:
            filters: ListingFilters with all search criteria
            fields: columns to SELECT (None = all columns)
            sort: sort column name (must be in ALLOWED_SORT_COLUMNS)
            order: 'asc' or 'desc'
            page: 1-based page number
            limit: results per page (capped at 500)
            dedup: whether to apply cross-MLS dedup

        Returns:
            SearchResult with listings, total count, and pagination info
        """
        conn = self._get_connection()
        try:
            conditions, params = self._build_conditions(filters)

            # Add dedup condition
            if dedup:
                # For IDX-filtered queries, scope the dedup subquery to IDX too
                if filters.require_idx:
                    dedup_cond = DEDUP_CONDITION.replace(
                        "AND dup.id != listings.id",
                        "AND dup.id != listings.id AND dup.idx_opt_in = 1"
                    )
                else:
                    dedup_cond = DEDUP_CONDITION
                conditions.append(dedup_cond)

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            # Count
            count_sql = f"SELECT COUNT(*) FROM listings WHERE {where_clause}"
            total = conn.execute(count_sql, params).fetchone()[0]

            # Sort (whitelist-validated)
            sort_col = sort if sort in ALLOWED_SORT_COLUMNS else 'list_date'
            sort_dir = 'ASC' if order.upper() == 'ASC' else 'DESC'

            # Pagination
            page = max(1, page)
            limit = min(500, max(1, limit))
            offset = (page - 1) * limit

            # Build SELECT
            if fields:
                fields_str = ", ".join(fields)
            else:
                fields_str = "*"

            # Use NULLS LAST behavior for sort
            query = (
                f"SELECT {fields_str} FROM listings "
                f"WHERE {where_clause} "
                f"ORDER BY {sort_col} IS NULL, {sort_col} {sort_dir} "
                f"LIMIT ? OFFSET ?"
            )
            rows = conn.execute(query, params + [limit, offset]).fetchall()

            listings = [row_to_dict(row) for row in rows]

            # Post-process: compute DOM and localize photos
            for listing in listings:
                listing['days_on_market'] = compute_dom(listing)
                localize_photo(listing)
                listing['mls_display_name'] = MLS_DISPLAY_NAMES.get(
                    listing.get('mls_source'), listing.get('mls_source')
                )
                listing['mls_number_display'] = strip_mls_prefix(listing.get('mls_number'))

            return SearchResult(
                listings=listings,
                total=total,
                page=page,
                limit=limit,
            )
        finally:
            conn.close()

    def get_listing(self, listing_id: str, fields: Optional[List[str]] = None,
                    require_idx: bool = False) -> Optional[dict]:
        """Get a single listing by ID.

        Args:
            listing_id: the listing's id
            fields: columns to SELECT (None = all columns)
            require_idx: if True, only return if idx_opt_in = 1

        Returns:
            Listing dict or None if not found
        """
        conn = self._get_connection()
        try:
            if fields:
                # Always include address_key for cross-MLS sibling lookup
                query_fields = list(fields)
                if 'address_key' not in query_fields:
                    query_fields.append('address_key')
                fields_str = ", ".join(query_fields)
            else:
                fields_str = "*"

            conditions = ["id = ?"]
            params = [listing_id]
            if require_idx:
                conditions.append("idx_opt_in = 1")

            where_clause = " AND ".join(conditions)
            row = conn.execute(
                f"SELECT {fields_str} FROM listings WHERE {where_clause}",
                params
            ).fetchone()

            if not row:
                return None

            listing = row_to_dict(row)
            listing['days_on_market'] = compute_dom(listing)
            localize_photo(listing)
            listing['mls_display_name'] = MLS_DISPLAY_NAMES.get(
                listing.get('mls_source'), listing.get('mls_source')
            )

            # Find cross-MLS siblings
            address_key = listing.get('address_key')
            also_listed_on = []
            if address_key:
                sibling_conditions = [
                    "address_key = ?",
                    "mls_source != ?",
                    "UPPER(status) = 'ACTIVE'",
                ]
                sibling_params = [address_key, listing.get('mls_source')]
                if require_idx:
                    sibling_conditions.append("idx_opt_in = 1")

                siblings = conn.execute(
                    "SELECT id, mls_number, mls_source, list_price, updated_at "
                    "FROM listings "
                    f"WHERE {' AND '.join(sibling_conditions)} "
                    "ORDER BY updated_at DESC",
                    sibling_params
                ).fetchall()
                for sib in siblings:
                    also_listed_on.append({
                        'id': sib['id'],
                        'mls_number': sib['mls_number'],
                        'mls_source': sib['mls_source'],
                        'mls_display_name': MLS_DISPLAY_NAMES.get(sib['mls_source'], sib['mls_source']),
                        'list_price': sib['list_price'],
                        'updated_at': sib['updated_at'],
                    })

            listing['also_listed_on'] = also_listed_on

            return listing
        finally:
            conn.close()

    def get_map_markers(self, filters: ListingFilters,
                        fields: Optional[List[str]] = None,
                        max_results: int = 2000) -> List[dict]:
        """Get lightweight marker data for map view.

        Args:
            filters: ListingFilters with search criteria
            fields: columns to SELECT
            max_results: maximum markers to return

        Returns:
            List of listing dicts with coordinates
        """
        conn = self._get_connection()
        try:
            conditions, params = self._build_conditions(filters)
            conditions.append("latitude IS NOT NULL")
            conditions.append("longitude IS NOT NULL")

            # Dedup
            if filters.require_idx:
                dedup_cond = DEDUP_CONDITION.replace(
                    "AND dup.id != listings.id",
                    "AND dup.id != listings.id AND dup.idx_opt_in = 1"
                )
            else:
                dedup_cond = DEDUP_CONDITION
            conditions.append(dedup_cond)

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            fields_str = ", ".join(fields) if fields else "*"

            query = (
                f"SELECT {fields_str} FROM listings "
                f"WHERE {where_clause} "
                f"ORDER BY list_price DESC "
                f"LIMIT ?"
            )
            rows = conn.execute(query, params + [max_results]).fetchall()

            listings = []
            for row in rows:
                d = dict(row)
                localize_photo(d)
                listings.append(d)

            return listings
        finally:
            conn.close()

    def count_listings(self, filters: ListingFilters, dedup: bool = True) -> int:
        """Count listings matching filters.

        Args:
            filters: ListingFilters with search criteria
            dedup: whether to apply cross-MLS dedup

        Returns:
            Integer count
        """
        conn = self._get_connection()
        try:
            conditions, params = self._build_conditions(filters)

            if dedup:
                if filters.require_idx:
                    dedup_cond = DEDUP_CONDITION.replace(
                        "AND dup.id != listings.id",
                        "AND dup.id != listings.id AND dup.idx_opt_in = 1"
                    )
                else:
                    dedup_cond = DEDUP_CONDITION
                conditions.append(dedup_cond)

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            count_sql = f"SELECT COUNT(*) FROM listings WHERE {where_clause}"
            return conn.execute(count_sql, params).fetchone()[0]
        finally:
            conn.close()

    def get_filter_options(self) -> Dict[str, Any]:
        """Get distinct values for filter dropdowns."""
        conn = self._get_connection()
        try:
            options: Dict[str, Any] = {}

            options['clients'] = sorted([r[0] for r in conn.execute(
                "SELECT DISTINCT added_for FROM listings WHERE added_for IS NOT NULL AND added_for != ''"
            ).fetchall()])
            options['cities'] = sorted([r[0] for r in conn.execute(
                "SELECT DISTINCT city FROM listings WHERE city IS NOT NULL AND city != ''"
            ).fetchall()])
            options['counties'] = sorted([r[0] for r in conn.execute(
                "SELECT DISTINCT county FROM listings WHERE county IS NOT NULL AND county != ''"
            ).fetchall()])
            options['statuses'] = sorted([r[0] for r in conn.execute(
                "SELECT DISTINCT status FROM listings WHERE status IS NOT NULL AND status != ''"
            ).fetchall()])

            # County -> cities mapping for cascade filtering
            county_cities: Dict[str, List[str]] = {}
            rows = conn.execute(
                "SELECT DISTINCT county, city FROM listings "
                "WHERE county IS NOT NULL AND county != '' AND city IS NOT NULL AND city != '' "
                "ORDER BY county, city"
            ).fetchall()
            for county, city in rows:
                county_cities.setdefault(county, []).append(city)
            options['county_cities'] = county_cities

            return options
        finally:
            conn.close()
