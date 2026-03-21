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
import re
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify, send_from_directory

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

public_bp = Blueprint('public', __name__)

DB_PATH = os.getenv('DREAMS_DB_PATH', str(PROJECT_ROOT / 'data' / 'dreams.db'))

# Photo directories by source
PHOTOS_DIRS = {
    'mlsgrid': PROJECT_ROOT / 'data' / 'photos' / 'mlsgrid',
    'canopy': PROJECT_ROOT / 'data' / 'photos' / 'mlsgrid',
    'navica': PROJECT_ROOT / 'data' / 'photos' / 'navica',
}

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

# Allowed sort columns (whitelist to prevent SQL injection)
ALLOWED_SORT_COLUMNS = {
    'list_price', 'days_on_market', 'list_date', 'beds', 'baths',
    'sqft', 'acreage', 'elevation_feet', 'year_built', 'updated_at', 'city',
    'sold_date', 'sold_price',
}


def get_db():
    """Get a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def row_to_dict(row, fields=None):
    """Convert sqlite3.Row to dict, optionally limiting to specified fields."""
    if row is None:
        return None
    d = dict(row)
    if fields:
        d = {k: v for k, v in d.items() if k in fields}
    return d


def _localize_photo(listing: dict) -> None:
    """Rewrite primary_photo to local URL if we have the file downloaded."""
    mls = listing.get('mls_number')
    if not mls:
        return
    source = (listing.get('photo_source') or listing.get('mls_source', '')).lower()
    if 'canopy' in source or 'mlsgrid' in source:
        photos_dir = PHOTOS_DIRS.get('mlsgrid')
    elif 'navica' in source or 'mountain' in source:
        photos_dir = PHOTOS_DIRS.get('navica')
    else:
        return

    if not photos_dir:
        # No local photo directory for this source; strip CDN URLs
        if 'mlsgrid.com' in (listing.get('primary_photo') or ''):
            listing['primary_photo'] = None
        return

    for ext in ('.jpg', '.jpeg', '.png', '.webp'):
        filepath = photos_dir / f"{mls}{ext}"
        if filepath.exists() and filepath.stat().st_size > 0:
            listing['primary_photo'] = f"/api/public/photos/{photos_dir.name}/{mls}{ext}"
            return

    # Local file not found; strip CDN URLs that browsers can't use
    if 'mlsgrid.com' in (listing.get('primary_photo') or ''):
        listing['primary_photo'] = None


def _compute_dom(listing: dict) -> int | None:
    """Compute Days on Market dynamically from list_date for active listings."""
    status = (listing.get('status') or '').lower()
    stored = listing.get('days_on_market')
    # For closed/expired/withdrawn, the stored value is the final DOM
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
    return stored


def parse_mls_list(q: str) -> list | None:
    """Detect and parse multiple MLS numbers from search input.
    Returns list of MLS numbers if input looks like a multi-MLS query,
    or None to fall through to normal LIKE search.
    """
    tokens = re.split(r'[,;\s]+', q.strip())
    tokens = [t.strip() for t in tokens if t.strip()]
    if len(tokens) < 2:
        return None
    for t in tokens:
        if not re.match(r'^[A-Za-z0-9\-]{4,12}$', t):
            return None
    return tokens


def build_listing_filters():
    """Build WHERE conditions and params from query string filters.

    Returns (conditions: list[str], params: list) shared by both
    the paginated listings endpoint and the map markers endpoint.
    """
    conditions = ["idx_opt_in = 1"]
    params = []

    # Zone filtering: default to zones 1+2 (WNC) unless explicitly specified
    zone_param = request.args.get('zone')
    if zone_param and zone_param.lower() == 'all':
        # No zone filter; also keep the state='NC' filter only if no zone param
        conditions.append("state = 'NC'")
    elif zone_param:
        # Parse comma-separated zone numbers (e.g., zone=1,2,3)
        zone_values = []
        for z in zone_param.split(','):
            z = z.strip()
            if z.isdigit() and 1 <= int(z) <= 5:
                zone_values.append(int(z))
        if zone_values:
            placeholders = ','.join(['?'] * len(zone_values))
            conditions.append(f"zone IN ({placeholders})")
            params.extend(zone_values)
        else:
            # Invalid zone param; fall back to default WNC
            conditions.append("zone IN (1, 2)")
    else:
        # Default: zones 1+2 (WNC service area)
        conditions.append("zone IN (1, 2)")

    status = request.args.get('status', 'ACTIVE').upper()
    if status:
        conditions.append("UPPER(status) = ?")
        params.append(status)

    city = request.args.get('city')
    if city:
        conditions.append("LOWER(city) = LOWER(?)")
        params.append(city)

    county = request.args.get('county')
    if county:
        conditions.append("LOWER(county) = LOWER(?)")
        params.append(county)

    min_price = request.args.get('min_price', type=int)
    if min_price is not None:
        conditions.append("list_price >= ?")
        params.append(min_price)

    max_price = request.args.get('max_price', type=int)
    if max_price is not None:
        conditions.append("list_price <= ?")
        params.append(max_price)

    min_beds = request.args.get('min_beds', type=int)
    if min_beds is not None:
        conditions.append("beds >= ?")
        params.append(min_beds)

    min_baths = request.args.get('min_baths', type=float)
    if min_baths is not None:
        conditions.append("baths >= ?")
        params.append(min_baths)

    min_sqft = request.args.get('min_sqft', type=int)
    if min_sqft is not None:
        conditions.append("sqft >= ?")
        params.append(min_sqft)

    min_acreage = request.args.get('min_acreage', type=float)
    if min_acreage is not None:
        conditions.append("acreage >= ?")
        params.append(min_acreage)

    max_dom = request.args.get('max_dom', type=int)
    if max_dom is not None:
        # Use list_date for accurate filtering (stored days_on_market can be stale)
        conditions.append("list_date >= date('now', ? || ' days')")
        params.append(str(-max_dom))

    property_type = request.args.get('property_type')
    if property_type:
        conditions.append("property_type = ?")
        params.append(property_type)

    mls_source = request.args.get('mls_source')
    if mls_source:
        conditions.append("mls_source = ?")
        params.append(mls_source)

    q = request.args.get('q')
    mls_list = parse_mls_list(q) if q else None
    if mls_list:
        placeholders = ','.join(['?'] * len(mls_list))
        conditions.append(f'mls_number IN ({placeholders})')
        params.extend(mls_list)
    elif q:
        search_term = f"%{q}%"
        conditions.append(
            "(address LIKE ? OR city LIKE ? OR county LIKE ? "
            "OR subdivision LIKE ? OR public_remarks LIKE ? OR mls_number LIKE ?)"
        )
        params.extend([search_term] * 6)

    return conditions, params


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
        db = get_db()
        conditions, params = build_listing_filters()

        # Sort
        sort_col = request.args.get('sort', 'list_date')
        if sort_col not in ALLOWED_SORT_COLUMNS:
            sort_col = 'list_date'
        sort_dir = request.args.get('order', 'desc').upper()
        if sort_dir not in ('ASC', 'DESC'):
            sort_dir = 'DESC'

        # Pagination
        page = max(1, request.args.get('page', 1, type=int))
        limit = min(100, max(1, request.args.get('limit', 24, type=int)))
        offset = (page - 1) * limit

        # Build query (include idx_address_display for address suppression check)
        # Deduplicate by address_key: pick most recently updated listing per address
        where_clause = " AND ".join(conditions)
        query_fields = PUBLIC_LIST_FIELDS + ['idx_address_display']
        fields_str = ", ".join(query_fields)

        # Dedup: for listings sharing the same address_key AND property_type,
        # keep only the most recently updated one. This handles both cross-MLS
        # duplicates and same-MLS re-listings. Different property types at the
        # same address (e.g., land + commercial on one parcel) are kept.
        dedup_condition = (
            "(address_key IS NULL OR NOT EXISTS ("
            "SELECT 1 FROM listings dup "
            "WHERE dup.address_key = listings.address_key "
            "AND dup.property_type = listings.property_type "
            "AND dup.id != listings.id "
            "AND dup.idx_opt_in = 1 "
            "AND UPPER(dup.status) = UPPER(listings.status) "
            "AND dup.updated_at > listings.updated_at))"
        )
        conditions.append(dedup_condition)
        where_clause = " AND ".join(conditions)

        # Get total count (deduplicated)
        count_sql = f"SELECT COUNT(*) FROM listings WHERE {where_clause}"
        total = db.execute(count_sql, params).fetchone()[0]

        # Get results
        query = (
            f"SELECT {fields_str} FROM listings "
            f"WHERE {where_clause} "
            f"ORDER BY {sort_col} {sort_dir} "
            f"LIMIT ? OFFSET ?"
        )
        rows = db.execute(query, params + [limit, offset]).fetchall()

        listings = [row_to_dict(row) for row in rows]

        # Suppress address for listings that opted out, then remove the flag from response
        for listing in listings:
            if not listing.get('idx_address_display'):
                listing['address'] = 'Address Withheld'
                listing['latitude'] = None
                listing['longitude'] = None
            listing.pop('idx_address_display', None)
            listing['days_on_market'] = _compute_dom(listing)
            _localize_photo(listing)

        db.close()

        return jsonify({
            'success': True,
            'data': listings,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'pages': (total + limit - 1) // limit if total > 0 else 0,
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
        db = get_db()
        conditions, params = build_listing_filters()

        # Map markers require coordinates
        conditions.append("latitude IS NOT NULL")
        conditions.append("longitude IS NOT NULL")

        # Dedup by address_key + property_type (same as search endpoint)
        dedup_condition = (
            "(address_key IS NULL OR NOT EXISTS ("
            "SELECT 1 FROM listings dup "
            "WHERE dup.address_key = listings.address_key "
            "AND dup.property_type = listings.property_type "
            "AND dup.id != listings.id "
            "AND dup.idx_opt_in = 1 "
            "AND UPPER(dup.status) = UPPER(listings.status) "
            "AND dup.updated_at > listings.updated_at))"
        )
        conditions.append(dedup_condition)

        where_clause = " AND ".join(conditions)
        fields_str = ", ".join(MAP_MARKER_FIELDS + ['idx_address_display'])

        query = (
            f"SELECT {fields_str} FROM listings "
            f"WHERE {where_clause} "
            f"ORDER BY list_price DESC "
            f"LIMIT 2000"
        )
        rows = db.execute(query, params).fetchall()

        listings = []
        for row in rows:
            d = dict(row)
            # Suppress address/coords if opted out
            if not d.get('idx_address_display'):
                continue  # Skip entirely for map view (no coords = no marker)
            d.pop('idx_address_display', None)
            _localize_photo(d)
            listings.append(d)

        db.close()

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
        db = get_db()

        fields_str = ", ".join(PUBLIC_LISTING_FIELDS)
        row = db.execute(
            f"SELECT {fields_str}, address_key FROM listings WHERE id = ? AND idx_opt_in = 1",
            [listing_id]
        ).fetchone()

        if not row:
            db.close()
            return jsonify({
                'success': False,
                'error': {'code': 'NOT_FOUND', 'message': 'Listing not found'}
            }), 404

        listing = row_to_dict(row)
        address_key = listing.pop('address_key', None)

        # Compute DOM dynamically
        listing['days_on_market'] = _compute_dom(listing)

        # Suppress address if opted out
        if not listing.get('idx_address_display'):
            listing['address'] = 'Address Withheld'
            listing['latitude'] = None
            listing['longitude'] = None

        _localize_photo(listing)

        # Parse photos from JSON string to list, strip CDN URLs
        if listing.get('photos') and isinstance(listing['photos'], str):
            try:
                photos = json.loads(listing['photos'])
                # Only keep local paths; drop CDN URLs browsers can't load
                listing['photos'] = [p for p in photos if isinstance(p, str) and not p.startswith('http')]
            except json.JSONDecodeError:
                listing['photos'] = []

        # Find cross-MLS siblings at the same address
        also_listed_on = []
        if address_key:
            siblings = db.execute(
                "SELECT id, mls_number, mls_source, list_price, updated_at "
                "FROM listings "
                "WHERE address_key = ? AND mls_source != ? AND idx_opt_in = 1 "
                "AND UPPER(status) = 'ACTIVE' "
                "ORDER BY updated_at DESC",
                [address_key, listing.get('mls_source')]
            ).fetchall()
            for sib in siblings:
                also_listed_on.append({
                    'id': sib['id'],
                    'mls_number': sib['mls_number'],
                    'mls_source': sib['mls_source'],
                    'list_price': sib['list_price'],
                    'updated_at': sib['updated_at'],
                })

        listing['also_listed_on'] = also_listed_on

        db.close()

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
        db = get_db()

        # Get the current listing's address info
        current = db.execute(
            "SELECT address, city, parcel_number FROM listings WHERE id = ? AND idx_opt_in = 1",
            [listing_id]
        ).fetchone()

        if not current:
            db.close()
            return jsonify({
                'success': False,
                'error': {'code': 'NOT_FOUND', 'message': 'Listing not found'}
            }), 404

        address = current['address']
        city = current['city']
        parcel = current['parcel_number']

        # Find related listings: prefer parcel_number match, fall back to address+city
        history_fields = [
            'id', 'mls_number', 'status', 'list_price', 'sold_price',
            'list_date', 'sold_date', 'days_on_market', 'listing_office_name',
        ]
        fields_str = ", ".join(history_fields)

        if parcel and parcel.strip():
            related_rows = db.execute(
                f"SELECT {fields_str} FROM listings "
                "WHERE parcel_number = ? AND id != ? AND idx_opt_in = 1 "
                "ORDER BY list_date DESC",
                [parcel, listing_id]
            ).fetchall()
        else:
            related_rows = db.execute(
                f"SELECT {fields_str} FROM listings "
                "WHERE LOWER(address) = LOWER(?) AND LOWER(city) = LOWER(?) "
                "AND id != ? AND idx_opt_in = 1 "
                "ORDER BY list_date DESC",
                [address, city, listing_id]
            ).fetchall()

        prior_listings = [row_to_dict(r) for r in related_rows]

        # Get price/status changes from property_changes table
        change_rows = db.execute(
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

        db.close()

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
        db = get_db()

        collection = db.execute(
            'SELECT id, name, description, status, created_at '
            'FROM property_packages WHERE share_token = ?',
            [share_token]
        ).fetchone()

        if not collection:
            db.close()
            return jsonify({
                'success': False,
                'error': {'code': 'NOT_FOUND', 'message': 'Collection not found'}
            }), 404

        # Get listings in collection
        rows = db.execute(
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
            d['days_on_market'] = _compute_dom(d)
            _localize_photo(d)
            listings.append(d)

        # Increment view count
        db.execute(
            'UPDATE property_packages SET view_count = COALESCE(view_count, 0) + 1, '
            'viewed_at = ? WHERE id = ?',
            [datetime.now().isoformat(), collection['id']]
        )
        db.commit()
        db.close()

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
        db = get_db()

        area_type = request.args.get('type', 'city')
        if area_type not in ('city', 'county'):
            area_type = 'city'

        status = request.args.get('status', 'ACTIVE').upper()

        # Zone filtering (same logic as listings)
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

        rows = db.execute(query, [status] + zone_params).fetchall()
        db.close()

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


@public_bp.route('/stats', methods=['GET'])
def listing_stats():
    """
    Get aggregate listing statistics.

    Returns total counts, price ranges, and breakdowns by type and source.
    Used for homepage stats, search filters, and market overview.
    """
    try:
        db = get_db()

        # Zone filtering (same logic as listings)
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

        # Overall stats for WNC listings (zone-scoped)
        overall = db.execute(f"""
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

        # Breakdown by property type
        by_type = db.execute(f"""
            SELECT property_type, COUNT(*) as count
            FROM listings
            WHERE idx_opt_in = 1 AND UPPER(status) = 'ACTIVE' {zone_where}
            GROUP BY property_type
            ORDER BY count DESC
        """, zone_params).fetchall()

        # Breakdown by MLS source
        by_source = db.execute(f"""
            SELECT mls_source, COUNT(*) as count
            FROM listings
            WHERE idx_opt_in = 1 AND UPPER(status) = 'ACTIVE' {zone_where}
            GROUP BY mls_source
            ORDER BY count DESC
        """, zone_params).fetchall()

        db.close()

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

    # Clean collection name for filename
    import re as _re
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
        db = get_db()

        rows = db.execute('''
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

        db.close()

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
        db = get_db()

        collection = db.execute(
            '''SELECT id, name, description, slug, cover_image, featured_order,
                      collection_type, created_at, derived_from_id, derived_from_type
               FROM property_packages
               WHERE slug = ? AND is_public = 1 AND status != 'archived' ''',
            [slug]
        ).fetchone()

        if not collection:
            db.close()
            return jsonify({
                'success': False,
                'error': {'code': 'NOT_FOUND', 'message': 'Collection not found'}
            }), 404

        # Get listings
        rows = db.execute(
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
            d['days_on_market'] = _compute_dom(d)
            _localize_photo(d)
            listings.append(d)

        # Increment view count
        db.execute(
            'UPDATE property_packages SET view_count = COALESCE(view_count, 0) + 1, '
            'viewed_at = ? WHERE id = ?',
            [datetime.now().isoformat(), collection['id']]
        )
        db.commit()
        db.close()

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
