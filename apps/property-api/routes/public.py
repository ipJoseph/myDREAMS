"""
Public API endpoints for the wncmountain.homes public website.

These endpoints require NO authentication and serve listing data for
the public-facing property search. They expose only IDX-compliant fields
(no private remarks, showing instructions, or other BBO-only data).

Endpoints:
    GET /public/listings          - Search/filter listings with pagination
    GET /public/listings/map      - Lightweight marker data for map view
    GET /public/listings/:id      - Single listing detail (photos served locally)
    GET /public/areas             - Distinct cities/counties with listing counts
    GET /public/stats             - Aggregate stats (total listings, price ranges)
"""

import json
import logging
import os
import sqlite3
import sys
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from flask import Blueprint, request, jsonify, send_from_directory

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.listing_service import (
    ListingService, ListingFilters,
    MLS_DISPLAY_NAMES, PHOTOS_DIRS,
    localize_photo, compute_dom, row_to_dict,
)

logger = logging.getLogger(__name__)

public_bp = Blueprint('public', __name__)

DB_PATH = os.getenv('DREAMS_DB_PATH', str(PROJECT_ROOT / 'data' / 'dreams.db'))

# Instantiate shared service
_service = ListingService(DB_PATH)

# Fields safe to expose publicly (no private remarks, showing instructions, etc.)
PUBLIC_LISTING_FIELDS = [
    'id', 'mls_number', 'mls_source', 'status', 'list_price',
    'original_list_price', 'list_date', 'days_on_market',
    'address', 'city', 'state', 'zip', 'county',
    'latitude', 'longitude', 'elevation_feet', 'subdivision',
    'property_type', 'property_subtype', 'beds', 'baths', 'sqft',
    'acreage', 'lot_sqft', 'year_built', 'stories', 'garage_spaces',
    'heating', 'cooling', 'appliances', 'interior_features',
    'exterior_features', 'amenities', 'views', 'style', 'roof',
    'sewer', 'water_source', 'construction_materials', 'foundation',
    'flooring', 'fireplace_features', 'parking_features',
    'hoa_fee', 'hoa_frequency', 'tax_annual_amount', 'tax_assessed_value',
    'listing_agent_name', 'listing_agent_phone', 'listing_agent_email',
    'listing_office_name',
    'primary_photo', 'photos', 'photo_count', 'virtual_tour_url',
    'public_remarks', 'directions',
    'parcel_number',
    'sold_price', 'sold_date',
    'idx_opt_in', 'idx_address_display',
    'updated_at',
]

# Compact fields for list view (faster, smaller payload)
PUBLIC_LIST_FIELDS = [
    'id', 'mls_number', 'mls_source', 'status', 'list_price',
    'address', 'city', 'state', 'zip', 'county',
    'latitude', 'longitude',
    'property_type', 'beds', 'baths', 'sqft', 'acreage',
    'elevation_feet', 'year_built', 'primary_photo', 'photo_count',
    'days_on_market', 'list_date',
    'sold_price', 'sold_date',
    'listing_office_name',
]

# Lightweight fields for map markers (no photos array, no remarks)
MAP_MARKER_FIELDS = [
    'id', 'mls_number', 'status', 'list_price',
    'address', 'city', 'county',
    'latitude', 'longitude', 'elevation_feet',
    'property_type', 'beds', 'baths', 'sqft',
    'primary_photo',
]


# ---------------------------------------------------------------------------
# Public-specific defaults for filters
# ---------------------------------------------------------------------------

PUBLIC_FILTER_DEFAULTS = {
    'status': 'ACTIVE',
    'zone': '1,2',
    'require_idx': True,
}


def _get_public_filters() -> ListingFilters:
    """Build ListingFilters from request with public-site defaults."""
    return ListingFilters.from_request(request.args, defaults=PUBLIC_FILTER_DEFAULTS)


# ---------------------------------------------------------------------------
# On-demand gallery download (public-specific, not shared)
# ---------------------------------------------------------------------------

_gallery_downloads_in_progress = set()
_gallery_lock = threading.Lock()


def _download_gallery_on_demand(mls_number: str, photos_json: str) -> None:
    """Background download of gallery photos for a single listing."""
    import requests as req

    with _gallery_lock:
        if mls_number in _gallery_downloads_in_progress:
            return
        _gallery_downloads_in_progress.add(mls_number)

    try:
        urls = json.loads(photos_json)
        if not urls or not isinstance(urls, list):
            return

        photos_dir = PHOTOS_DIRS.get('mlsgrid')
        if not photos_dir:
            return

        local_paths = []
        for i, url in enumerate(urls):
            if not url or not isinstance(url, str) or not url.startswith('http'):
                local_paths.append(url)
                continue

            path_lower = urlparse(url).path.lower()
            ext = '.png' if path_lower.endswith('.png') else '.webp' if path_lower.endswith('.webp') else '.jpg'

            filename = f"{mls_number}{ext}" if i == 0 else f"{mls_number}_{i:02d}{ext}"
            filepath = photos_dir / filename

            if filepath.exists() and filepath.stat().st_size > 0:
                local_paths.append(f"/api/public/photos/mlsgrid/{filename}")
                continue

            try:
                resp = req.get(url, timeout=30, stream=True)
                resp.raise_for_status()
                with open(filepath, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                if filepath.stat().st_size > 0:
                    local_paths.append(f"/api/public/photos/mlsgrid/{filename}")
                else:
                    filepath.unlink(missing_ok=True)
            except Exception:
                filepath.unlink(missing_ok=True)

        # Update DB with local paths
        if local_paths:
            try:
                from src.core.pg_adapter import get_db as _pg_get_db
                conn = _pg_get_db(str(DB_PATH))
                conn.execute(
                    "UPDATE listings SET photos = ? WHERE mls_number = ?",
                    [json.dumps(local_paths), mls_number]
                )
                conn.commit()
                conn.close()
            except Exception:
                pass

    except Exception as e:
        logger.warning(f"On-demand gallery download failed for {mls_number}: {e}")
    finally:
        with _gallery_lock:
            _gallery_downloads_in_progress.discard(mls_number)


def _suppress_address(listing: dict) -> None:
    """Suppress address/coords for listings that opted out of IDX address display."""
    if not listing.get('idx_address_display'):
        listing['address'] = 'Address Withheld'
        listing['latitude'] = None
        listing['longitude'] = None
    listing.pop('idx_address_display', None)


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

@public_bp.route('/listings', methods=['GET'])
def search_listings():
    """
    Search and filter listings with pagination.

    Query parameters:
        status      - Filter by status (default: ACTIVE)
        city        - Filter by city name
        county      - Filter by county
        min_price   - Minimum list price
        max_price   - Maximum list price
        min_beds    - Minimum bedrooms
        min_baths   - Minimum bathrooms
        min_sqft    - Minimum square footage
        min_acreage - Minimum acreage
        property_type - Filter by property type (Residential, Land, etc.)
        mls_source  - Filter by MLS source
        q           - Full-text search (address, city, county, subdivision, remarks)
        sort        - Sort column (default: list_date)
        order       - Sort direction: asc or desc (default: desc)
        page        - Page number (default: 1)
        limit       - Results per page (default: 24, max: 100)
    """
    try:
        filters = _get_public_filters()
        sort_col = request.args.get('sort', 'list_date')
        sort_dir = request.args.get('order', 'desc')
        page = max(1, request.args.get('page', 1, type=int))
        limit = min(100, max(1, request.args.get('limit', 24, type=int)))

        # Query with idx_address_display for suppression check
        query_fields = PUBLIC_LIST_FIELDS + ['idx_address_display']

        result = _service.search_listings(
            filters, fields=query_fields,
            sort=sort_col, order=sort_dir,
            page=page, limit=limit,
        )

        # Public-specific post-processing
        for listing in result.listings:
            _suppress_address(listing)

        return jsonify({
            'success': True,
            'data': result.listings,
            'pagination': {
                'page': result.page,
                'limit': result.limit,
                'total': result.total,
                'pages': result.pages,
            },
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': {'code': 'SERVER_ERROR', 'message': 'Failed to search listings'}
        }), 500


@public_bp.route('/listings/map', methods=['GET'])
def map_listings():
    """
    Lightweight marker data for the map search view.

    Returns all matching listings (up to 2,000) with only the fields
    needed for map markers and popups. No pagination; filters are
    the same as /listings.
    """
    try:
        filters = _get_public_filters()
        query_fields = MAP_MARKER_FIELDS + ['idx_address_display']

        markers = _service.get_map_markers(filters, fields=query_fields)

        # Filter out listings with suppressed addresses (no coords = no marker)
        listings = []
        for d in markers:
            if not d.get('idx_address_display'):
                continue
            d.pop('idx_address_display', None)
            listings.append(d)

        return jsonify({
            'success': True,
            'data': listings,
            'count': len(listings),
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': {'code': 'SERVER_ERROR', 'message': 'Failed to retrieve map listings'}
        }), 500


@public_bp.route('/listings/<listing_id>', methods=['GET'])
def get_listing(listing_id):
    """
    Get a single listing by ID with full public details.

    Returns all IDX-safe fields including photos, remarks, and agent info.
    """
    try:
        listing = _service.get_listing(listing_id, fields=PUBLIC_LISTING_FIELDS, require_idx=True)

        if not listing:
            return jsonify({
                'success': False,
                'error': {'code': 'NOT_FOUND', 'message': 'Listing not found'}
            }), 404

        # Suppress address if opted out
        _suppress_address(listing)

        # Parse photos from JSON string to list, strip CDN URLs
        raw_photos_json = listing.get('photos')
        if raw_photos_json and isinstance(raw_photos_json, str):
            try:
                photos = json.loads(raw_photos_json)
                local_only = [p for p in photos if isinstance(p, str) and 'mlsgrid.com' not in p]
                has_cdn_urls = any(isinstance(p, str) and 'mlsgrid.com' in p for p in photos)

                # Trigger background download if gallery has CDN URLs
                if (has_cdn_urls and listing.get('mls_number')
                        and not os.getenv('DISABLE_ONDEMAND_GALLERY')):
                    threading.Thread(
                        target=_download_gallery_on_demand,
                        args=(listing['mls_number'], raw_photos_json),
                        daemon=True
                    ).start()

                # Prefer local photos; fall back to CDN URLs if no local
                # copies exist. CDN tokens may expire, but showing something
                # (or triggering the on-demand download) beats an empty gallery.
                listing['photos'] = local_only if local_only else photos
            except json.JSONDecodeError:
                listing['photos'] = []

        return jsonify({
            'success': True,
            'data': listing,
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': {'code': 'SERVER_ERROR', 'message': 'Failed to retrieve listing'}
        }), 500


@public_bp.route('/listings/<listing_id>/history', methods=['GET'])
def get_listing_history(listing_id):
    """
    Get the transaction history for a listing's address.

    Returns prior listings at the same address and price/status changes
    from the property_changes table, merged into a unified timeline.

    Matching strategy: uses parcel_number when available (handles duplicate
    addresses like "00 Deerwood Drive"), falls back to address+city match.
    """
    try:
        conn = _service._get_connection()
        try:
            current = conn.execute(
                "SELECT address, city, parcel_number FROM listings WHERE id = ? AND idx_opt_in = 1",
                [listing_id]
            ).fetchone()

            if not current:
                return jsonify({
                    'success': False,
                    'error': {'code': 'NOT_FOUND', 'message': 'Listing not found'}
                }), 404

            address = current['address']
            city = current['city']
            parcel = current['parcel_number']

            history_fields = [
                'id', 'mls_number', 'status', 'list_price', 'sold_price',
                'list_date', 'sold_date', 'days_on_market', 'listing_office_name',
            ]
            fields_str = ", ".join(history_fields)

            if parcel and parcel.strip():
                related_rows = conn.execute(
                    f"SELECT {fields_str} FROM listings "
                    "WHERE parcel_number = ? AND id != ? AND idx_opt_in = 1 "
                    "ORDER BY list_date DESC",
                    [parcel, listing_id]
                ).fetchall()
            else:
                related_rows = conn.execute(
                    f"SELECT {fields_str} FROM listings "
                    "WHERE LOWER(address) = LOWER(?) AND LOWER(city) = LOWER(?) "
                    "AND id != ? AND idx_opt_in = 1 "
                    "ORDER BY list_date DESC",
                    [address, city, listing_id]
                ).fetchall()

            prior_listings = [row_to_dict(r) for r in related_rows]

            change_rows = conn.execute(
                "SELECT change_type, old_value, new_value, change_amount, "
                "change_percent, detected_at "
                "FROM property_changes WHERE property_id = ? "
                "ORDER BY detected_at DESC",
                [listing_id]
            ).fetchall()

            changes = []
            for row in change_rows:
                changes.append({
                    'change_type': row['change_type'],
                    'old_value': row['old_value'],
                    'new_value': row['new_value'],
                    'change_amount': row['change_amount'],
                    'change_percent': row['change_percent'],
                    'date': row['detected_at'],
                })
        finally:
            conn.close()

        return jsonify({
            'success': True,
            'data': {
                'prior_listings': prior_listings,
                'changes': changes,
            },
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': {'code': 'SERVER_ERROR', 'message': 'Failed to retrieve listing history'}
        }), 500


@public_bp.route('/collections/<share_token>', methods=['GET'])
def get_shared_collection(share_token):
    """
    Get a shared property collection by its share token (no auth required).

    Returns collection metadata and associated listing data.
    """
    try:
        conn = _service._get_connection()
        try:
            collection = conn.execute(
                'SELECT id, name, description, status, created_at '
                'FROM property_packages WHERE share_token = ?',
                [share_token]
            ).fetchone()

            if not collection:
                return jsonify({
                    'success': False,
                    'error': {'code': 'NOT_FOUND', 'message': 'Collection not found'}
                }), 404

            rows = conn.execute(
                '''SELECT l.id, l.mls_number, l.status, l.list_price, l.sold_price,
                          l.address, l.city, l.state, l.zip, l.county,
                          l.latitude, l.longitude,
                          l.property_type, l.beds, l.baths, l.sqft, l.acreage,
                          l.elevation_feet, l.primary_photo, l.photo_count,
                          l.days_on_market, l.list_date,
                          pp.display_order, pp.agent_notes
                   FROM package_properties pp
                   JOIN listings l ON l.id = pp.listing_id
                   WHERE pp.package_id = ? AND l.idx_opt_in = 1
                   ORDER BY pp.display_order, pp.added_at''',
                [collection['id']]
            ).fetchall()

            listings = []
            for row in rows:
                d = dict(row)
                d['days_on_market'] = compute_dom(d)
                localize_photo(d)
                listings.append(d)

            conn.execute(
                'UPDATE property_packages SET view_count = COALESCE(view_count, 0) + 1, '
                'viewed_at = ? WHERE id = ?',
                [datetime.now().isoformat(), collection['id']]
            )
            conn.commit()
        finally:
            conn.close()

        return jsonify({
            'success': True,
            'data': {
                'name': collection['name'],
                'description': collection['description'],
                'status': collection['status'],
                'created_at': collection['created_at'],
                'listings': listings,
                'listing_count': len(listings),
            },
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': {'code': 'SERVER_ERROR', 'message': 'Failed to retrieve collection'}
        }), 500


@public_bp.route('/areas', methods=['GET'])
def list_areas():
    """
    Get distinct cities and counties with listing counts.

    Used for area guide navigation and search filters.

    Query parameters:
        type    - 'city' or 'county' (default: city)
        status  - Filter by status (default: ACTIVE)
    """
    try:
        conn = _service._get_connection()
        try:
            area_type = request.args.get('type', 'city')
            if area_type not in ('city', 'county'):
                area_type = 'city'

            status = request.args.get('status', 'ACTIVE').upper()

            # Zone filtering
            zone_param = request.args.get('zone')
            zone_conditions = []
            zone_params = []
            if zone_param and zone_param.lower() == 'all':
                zone_conditions.append("state = 'NC'")
            elif zone_param:
                zone_values = [int(z.strip()) for z in zone_param.split(',')
                              if z.strip().isdigit() and 1 <= int(z.strip()) <= 5]
                if zone_values:
                    placeholders = ','.join(['?'] * len(zone_values))
                    zone_conditions.append(f"zone IN ({placeholders})")
                    zone_params.extend(zone_values)
                else:
                    zone_conditions.append("zone IN (1, 2)")
            else:
                zone_conditions.append("zone IN (1, 2)")

            zone_where = (" AND " + " AND ".join(zone_conditions)) if zone_conditions else ""

            query = (
                f"SELECT {area_type} as name, COUNT(*) as listing_count, "
                f"MIN(list_price) as min_price, MAX(list_price) as max_price, "
                f"AVG(list_price) as avg_price "
                f"FROM listings "
                f"WHERE idx_opt_in = 1 AND UPPER(status) = ? "
                f"AND {area_type} IS NOT NULL AND {area_type} != 'Other'"
                f"{zone_where} "
                f"GROUP BY {area_type} "
                f"ORDER BY listing_count DESC"
            )

            rows = conn.execute(query, [status] + zone_params).fetchall()
        finally:
            conn.close()

        areas = []
        for row in rows:
            areas.append({
                'name': row['name'],
                'listing_count': row['listing_count'],
                'min_price': row['min_price'],
                'max_price': row['max_price'],
                'avg_price': round(row['avg_price']) if row['avg_price'] else None,
            })

        return jsonify({
            'success': True,
            'data': areas,
            'count': len(areas),
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': {'code': 'SERVER_ERROR', 'message': 'Failed to retrieve areas'}
        }), 500


@public_bp.route('/filtered-stats', methods=['GET'])
def filtered_stats():
    """
    Get stats for the current search filters.

    Returns avg price, median price, avg sqft, avg $/sqft, avg DOM, avg lot size
    filtered by all search params (city, county, price range, beds, type, etc.)
    """
    try:
        filters = ListingFilters.from_request(request.args, require_idx=True)
        conditions, params = _service._build_conditions(filters)
        where = " AND ".join(conditions) if conditions else "1=1"

        conn = _service._get_connection()
        try:
            row = conn.execute(f"""
                SELECT
                    COUNT(*) as count,
                    AVG(list_price) as avg_price,
                    AVG(sqft) as avg_sqft,
                    AVG(CASE WHEN sqft > 0 THEN CAST(list_price AS FLOAT) / sqft END) as avg_price_per_sqft,
                    AVG(CASE WHEN acreage > 0 THEN acreage END) as avg_lot_acres
                FROM listings
                WHERE {where}
            """, params).fetchone()

            count = row[0] if row else 0
            avg_price = round(row[1]) if row and row[1] else None
            avg_sqft = round(row[2]) if row and row[2] else None
            avg_ppsf = round(row[3]) if row and row[3] else None
            avg_lot = round(row[4], 2) if row and row[4] else None

            # Median price (approximate via PERCENTILE or ordered query)
            median_price = None
            if count > 0:
                mid = count // 2
                med_row = conn.execute(f"""
                    SELECT list_price FROM listings
                    WHERE {where} AND list_price IS NOT NULL
                    ORDER BY list_price
                    LIMIT 1 OFFSET ?
                """, params + [mid]).fetchone()
                if med_row:
                    median_price = med_row[0]

            # Avg DOM (computed from list_date)
            avg_dom = None
            try:
                from src.core.pg_adapter import is_postgres
                if is_postgres():
                    dom_row = conn.execute(f"""
                        SELECT AVG(CURRENT_DATE - list_date::date)
                        FROM listings WHERE {where} AND list_date IS NOT NULL
                    """, params).fetchone()
                else:
                    dom_row = conn.execute(f"""
                        SELECT AVG(julianday('now') - julianday(list_date))
                        FROM listings WHERE {where} AND list_date IS NOT NULL
                    """, params).fetchone()
                if dom_row and dom_row[0]:
                    avg_dom = round(float(dom_row[0]))
            except Exception:
                pass

            return jsonify({
                'success': True,
                'data': {
                    'count': count,
                    'avg_price': avg_price,
                    'median_price': median_price,
                    'avg_sqft': avg_sqft,
                    'avg_price_per_sqft': avg_ppsf,
                    'avg_dom': avg_dom,
                    'avg_lot_acres': avg_lot,
                },
            })
        finally:
            conn.close()
    except Exception as e:
        return jsonify({
            'success': False,
            'error': {'code': 'SERVER_ERROR', 'message': 'Failed to compute stats'},
        }), 500


@public_bp.route('/stats', methods=['GET'])
def listing_stats():
    """
    Get aggregate listing statistics.

    Returns total counts, price ranges, and breakdowns by type and source.
    Used for homepage stats, search filters, and market overview.
    """
    try:
        conn = _service._get_connection()
        try:
            # Zone filtering
            zone_param = request.args.get('zone')
            zone_where = ""
            zone_params = []
            if zone_param and zone_param.lower() == 'all':
                zone_where = "AND state = 'NC'"
            elif zone_param:
                zone_values = [int(z.strip()) for z in zone_param.split(',')
                              if z.strip().isdigit() and 1 <= int(z.strip()) <= 5]
                if zone_values:
                    placeholders = ','.join(['?'] * len(zone_values))
                    zone_where = f"AND zone IN ({placeholders})"
                    zone_params = list(zone_values)
                else:
                    zone_where = "AND zone IN (1, 2)"
            else:
                zone_where = "AND zone IN (1, 2)"

            overall = conn.execute(f"""
                SELECT
                    COUNT(*) as total_listings,
                    COUNT(CASE WHEN UPPER(status) = 'ACTIVE' THEN 1 END) as active_listings,
                    COUNT(CASE WHEN UPPER(status) = 'PENDING' THEN 1 END) as pending_listings,
                    MIN(CASE WHEN UPPER(status) = 'ACTIVE' THEN list_price END) as min_price,
                    MAX(CASE WHEN UPPER(status) = 'ACTIVE' THEN list_price END) as max_price,
                    AVG(CASE WHEN UPPER(status) = 'ACTIVE' THEN list_price END) as avg_price,
                    COUNT(DISTINCT CASE WHEN UPPER(status) = 'ACTIVE'
                        AND city IS NOT NULL AND city != 'Other' THEN city END) as cities_served,
                    COUNT(DISTINCT CASE WHEN UPPER(status) = 'ACTIVE'
                        AND county IS NOT NULL AND county != 'Other' THEN county END) as counties_served
                FROM listings
                WHERE idx_opt_in = 1 {zone_where}
            """, zone_params).fetchone()

            by_type = conn.execute(f"""
                SELECT property_type, COUNT(*) as count
                FROM listings
                WHERE idx_opt_in = 1 AND UPPER(status) = 'ACTIVE' {zone_where}
                GROUP BY property_type
                ORDER BY count DESC
            """, zone_params).fetchall()

            by_source = conn.execute(f"""
                SELECT mls_source, COUNT(*) as count
                FROM listings
                WHERE idx_opt_in = 1 AND UPPER(status) = 'ACTIVE' {zone_where}
                GROUP BY mls_source
                ORDER BY count DESC
            """, zone_params).fetchall()
        finally:
            conn.close()

        return jsonify({
            'success': True,
            'data': {
                'total_listings': overall['total_listings'],
                'active_listings': overall['active_listings'],
                'pending_listings': overall['pending_listings'],
                'min_price': overall['min_price'],
                'max_price': overall['max_price'],
                'avg_price': round(overall['avg_price']) if overall['avg_price'] else None,
                'cities_served': overall['cities_served'],
                'counties_served': overall['counties_served'],
                'by_property_type': [
                    {'type': row['property_type'], 'count': row['count']}
                    for row in by_type
                ],
                'by_mls_source': [
                    {'source': row['mls_source'], 'count': row['count']}
                    for row in by_source
                ],
            },
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': {'code': 'SERVER_ERROR', 'message': 'Failed to retrieve stats'}
        }), 500


# ── Smart Search: Query Parser + Autocomplete ──

# Lazy-loaded parser singleton (loads city/county lists from DB once)
_parser = None
_parser_lock = threading.Lock()

def _get_parser():
    global _parser
    if _parser is None:
        with _parser_lock:
            if _parser is None:
                from src.core.query_parser import QueryParser
                conn = sqlite3.connect(DB_PATH)
                cities = [r[0] for r in conn.execute(
                    "SELECT DISTINCT city FROM listings WHERE city IS NOT NULL AND city != '' ORDER BY city"
                ).fetchall()]
                counties = [r[0] for r in conn.execute(
                    "SELECT DISTINCT county FROM listings WHERE county IS NOT NULL AND county != '' ORDER BY county"
                ).fetchall()]
                conn.close()
                _parser = QueryParser(cities=cities, counties=counties)
    return _parser


@public_bp.route('/search/parse', methods=['GET'])
def parse_search_query():
    """Parse a natural language search query into structured filters.

    GET /api/public/search/parse?q=3+bed+cabin+under+400k+in+Sylva

    Returns structured filters compatible with ListingFilters, plus
    human-readable interpretations for display as filter chips.
    """
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'success': True, 'data': {
            'filters': {}, 'remainder': '', 'interpretations': [],
            'redirect': None,
        }})

    parser = _get_parser()
    result = parser.parse(q)

    # For MLS lookups, check if listing exists and provide redirect URL
    redirect_url = None
    if result.is_mls_lookup and result.filters.get('mls_number'):
        mls = result.filters['mls_number']
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT id FROM listings WHERE mls_number = ? OR mls_number = ?",
            [mls, f'CAR{mls}']
        ).fetchone()
        conn.close()
        if row:
            redirect_url = f'/listings/{row[0]}'

    return jsonify({
        'success': True,
        'data': {
            'filters': result.filters,
            'remainder': result.remainder,
            'interpretations': result.interpretations,
            'redirect': redirect_url,
            'is_mls_lookup': result.is_mls_lookup,
            'is_address_lookup': result.is_address_lookup,
        }
    })


@public_bp.route('/autocomplete', methods=['GET'])
def autocomplete():
    """Autocomplete suggestions for the smart search bar.

    GET /api/public/autocomplete?q=syl&limit=8

    Returns city, county, and address matches.
    """
    q = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 8)), 20)

    if len(q) < 2:
        return jsonify({'success': True, 'data': {'suggestions': []}})

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    suggestions = []

    try:
        q_lower = q.lower()
        q_like = f'{q}%'

        # Cities matching prefix
        cities = conn.execute(
            "SELECT city, COUNT(*) as cnt FROM listings "
            "WHERE city IS NOT NULL AND LOWER(city) LIKE LOWER(?) "
            "AND status = 'ACTIVE' AND zone IN (1,2,3) "
            "GROUP BY city ORDER BY cnt DESC LIMIT ?",
            [q_like, limit]
        ).fetchall()
        for row in cities:
            suggestions.append({
                'type': 'city', 'value': row['city'],
                'label': row['city'], 'count': row['cnt'],
            })

        # Counties matching prefix
        counties = conn.execute(
            "SELECT county, COUNT(*) as cnt FROM listings "
            "WHERE county IS NOT NULL AND LOWER(county) LIKE LOWER(?) "
            "AND status = 'ACTIVE' AND zone IN (1,2,3) "
            "GROUP BY county ORDER BY cnt DESC LIMIT ?",
            [q_like, limit]
        ).fetchall()
        for row in counties:
            suggestions.append({
                'type': 'county', 'value': row['county'],
                'label': f"{row['county']} County", 'count': row['cnt'],
            })

        # Address matches (only if 3+ chars)
        if len(q) >= 3:
            addresses = conn.execute(
                "SELECT id, address, city, list_price FROM listings "
                "WHERE address IS NOT NULL AND LOWER(address) LIKE LOWER(?) "
                "AND status = 'ACTIVE' AND zone IN (1,2,3) "
                "ORDER BY list_price DESC LIMIT ?",
                [f'%{q}%', limit]
            ).fetchall()
            for row in addresses:
                suggestions.append({
                    'type': 'address', 'value': row['address'],
                    'label': f"{row['address']}, {row['city'] or ''}".strip(', '),
                    'listing_id': row['id'],
                    'price': row['list_price'],
                })

    finally:
        conn.close()

    return jsonify({'success': True, 'data': {'suggestions': suggestions[:limit]}})


@public_bp.route('/listings/<listing_id>/brochure', methods=['GET'])
def get_listing_brochure(listing_id):
    """
    Generate and return a single-property brochure PDF.

    Returns application/pdf with Content-Disposition attachment header.
    """
    from flask import Response
    try:
        from apps.automation.brochure_generator import (
            generate_brochure_bytes, get_listing_data, get_brochure_filename
        )
    except ImportError:
        return jsonify({
            'success': False,
            'error': {'code': 'SERVER_ERROR', 'message': 'PDF generation unavailable'}
        }), 500

    listing = get_listing_data(listing_id)
    if not listing:
        return jsonify({
            'success': False,
            'error': {'code': 'NOT_FOUND', 'message': 'Listing not found'}
        }), 404

    pdf_bytes = generate_brochure_bytes(listing_id)
    if not pdf_bytes:
        return jsonify({
            'success': False,
            'error': {'code': 'SERVER_ERROR', 'message': 'Failed to generate brochure'}
        }), 500

    filename = get_brochure_filename(listing)

    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
        },
    )


@public_bp.route('/collections/<share_token>/brochure', methods=['GET'])
def get_collection_brochure(share_token):
    """
    Generate and return a combined PDF brochure for all properties in a collection.

    Each property gets its own full brochure pages, concatenated into one PDF.
    """
    from flask import Response
    import re as _re
    try:
        from apps.automation.brochure_generator import generate_collection_pdf
    except ImportError:
        return jsonify({
            'success': False,
            'error': {'code': 'SERVER_ERROR', 'message': 'PDF generation unavailable'}
        }), 500

    pdf_bytes, collection_name = generate_collection_pdf(share_token)

    if not pdf_bytes:
        return jsonify({
            'success': False,
            'error': {'code': 'NOT_FOUND', 'message': 'Collection not found or empty'}
        }), 404

    clean_name = _re.sub(r'[^a-zA-Z0-9\- ]', '', collection_name)
    clean_name = clean_name.replace(' ', '-').strip('-') or 'Collection'
    filename = f"{clean_name}.pdf"

    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
        },
    )


# =============================================================================
# FEATURED COLLECTIONS
# =============================================================================

@public_bp.route('/collections/featured', methods=['GET'])
def list_featured_collections():
    """
    Get featured collections for the public website.

    Returns collections marked as public/featured with cover images,
    property counts, and price range summaries.
    """
    try:
        conn = _service._get_connection()
        try:
            rows = conn.execute('''
                SELECT pp.id, pp.name, pp.description, pp.slug, pp.cover_image,
                       pp.featured_order, pp.collection_type, pp.created_at,
                       COUNT(pkp.id) as property_count,
                       MIN(l.list_price) as min_price,
                       MAX(l.list_price) as max_price,
                       AVG(l.list_price) as avg_price
                FROM property_packages pp
                LEFT JOIN package_properties pkp ON pkp.package_id = pp.id
                LEFT JOIN listings l ON l.id = pkp.listing_id AND l.idx_opt_in = 1
                WHERE pp.is_public = 1
                AND pp.collection_type IN ('template', 'featured')
                AND pp.status != 'archived'
                GROUP BY pp.id
                HAVING property_count > 0
                ORDER BY pp.featured_order ASC NULLS LAST, pp.updated_at DESC
            ''').fetchall()
        finally:
            conn.close()

        collections = []
        for row in rows:
            d = dict(row)
            d['avg_price'] = round(d['avg_price']) if d.get('avg_price') else None
            collections.append(d)

        return jsonify({
            'success': True,
            'data': collections,
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': {'code': 'SERVER_ERROR', 'message': 'Failed to retrieve featured collections'}
        }), 500


@public_bp.route('/collections/featured/<slug>', methods=['GET'])
def get_featured_collection(slug):
    """
    Get a featured collection by its URL slug.

    Returns full collection with listings, similar to the share token endpoint
    but resolved by slug instead.
    """
    try:
        conn = _service._get_connection()
        try:
            collection = conn.execute(
                '''SELECT id, name, description, slug, cover_image, featured_order,
                          collection_type, created_at, derived_from_id, derived_from_type
                   FROM property_packages
                   WHERE slug = ? AND is_public = 1 AND status != 'archived' ''',
                [slug]
            ).fetchone()

            if not collection:
                return jsonify({
                    'success': False,
                    'error': {'code': 'NOT_FOUND', 'message': 'Collection not found'}
                }), 404

            rows = conn.execute(
                '''SELECT l.id, l.mls_number, l.status, l.list_price, l.sold_price,
                          l.address, l.city, l.state, l.zip, l.county,
                          l.latitude, l.longitude,
                          l.property_type, l.beds, l.baths, l.sqft, l.acreage,
                          l.elevation_feet, l.primary_photo, l.photo_count,
                          l.days_on_market, l.list_date,
                          l.year_built, l.lot_sqft, l.stories,
                          l.public_remarks,
                          pp.display_order, pp.agent_notes
                   FROM package_properties pp
                   JOIN listings l ON l.id = pp.listing_id
                   WHERE pp.package_id = ? AND l.idx_opt_in = 1
                   ORDER BY pp.display_order, pp.added_at''',
                [collection['id']]
            ).fetchall()

            listings = []
            for row in rows:
                d = dict(row)
                d['days_on_market'] = compute_dom(d)
                localize_photo(d)
                listings.append(d)

            conn.execute(
                'UPDATE property_packages SET view_count = COALESCE(view_count, 0) + 1, '
                'viewed_at = ? WHERE id = ?',
                [datetime.now().isoformat(), collection['id']]
            )
            conn.commit()
        finally:
            conn.close()

        return jsonify({
            'success': True,
            'data': {
                'id': collection['id'],
                'name': collection['name'],
                'description': collection['description'],
                'slug': collection['slug'],
                'cover_image': collection['cover_image'],
                'collection_type': collection['collection_type'],
                'created_at': collection['created_at'],
                'listings': listings,
                'listing_count': len(listings),
            },
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': {'code': 'SERVER_ERROR', 'message': 'Failed to retrieve collection'}
        }), 500


# =============================================================================
# LOCAL PHOTO SERVING
# =============================================================================

@public_bp.route('/photos/<source>/<filename>')
def serve_photo(source, filename):
    """
    Serve locally-downloaded MLS photos.

    URL pattern: /api/public/photos/{source}/{mls_number}.jpg
    Sources: mlsgrid (Canopy), navica (Carolina Smokies / Mountain Lakes)
    """
    photos_dir = PHOTOS_DIRS.get(source)
    if not photos_dir or not photos_dir.is_dir():
        return jsonify({'error': 'Not found'}), 404

    safe_name = Path(filename).name
    if safe_name != filename or '..' in filename:
        return jsonify({'error': 'Not found'}), 404

    filepath = photos_dir / safe_name
    if not filepath.exists():
        return jsonify({'error': 'Not found'}), 404

    return send_from_directory(
        str(photos_dir), safe_name,
        max_age=86400,
    )
