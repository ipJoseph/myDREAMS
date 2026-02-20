"""
Public API endpoints for the wncmountain.homes public website.

These endpoints require NO authentication and serve listing data for
the public-facing property search. They expose only IDX-compliant fields
(no private remarks, showing instructions, or other BBO-only data).

Endpoints:
    GET /public/listings          - Search/filter listings with pagination
    GET /public/listings/:id      - Single listing detail
    GET /public/areas             - Distinct cities/counties with listing counts
    GET /public/stats             - Aggregate stats (total listings, price ranges)
"""

import json
import os
import sqlite3
import sys
from pathlib import Path
from flask import Blueprint, request, jsonify

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

public_bp = Blueprint('public', __name__)

DB_PATH = os.getenv('DREAMS_DB_PATH', str(PROJECT_ROOT / 'data' / 'dreams.db'))

# Fields safe to expose publicly (no private remarks, showing instructions, etc.)
PUBLIC_LISTING_FIELDS = [
    'id', 'mls_number', 'mls_source', 'status', 'list_price',
    'original_list_price', 'list_date', 'days_on_market',
    'address', 'city', 'state', 'zip', 'county',
    'latitude', 'longitude', 'subdivision',
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
    'idx_opt_in', 'idx_address_display',
    'updated_at',
]

# Compact fields for list view (faster, smaller payload)
PUBLIC_LIST_FIELDS = [
    'id', 'mls_number', 'mls_source', 'status', 'list_price',
    'address', 'city', 'state', 'zip', 'county',
    'latitude', 'longitude',
    'property_type', 'beds', 'baths', 'sqft', 'acreage',
    'year_built', 'primary_photo', 'photo_count',
    'days_on_market', 'list_date',
    'listing_office_name',
]

# Allowed sort columns (whitelist to prevent SQL injection)
ALLOWED_SORT_COLUMNS = {
    'list_price', 'days_on_market', 'list_date', 'beds', 'baths',
    'sqft', 'acreage', 'year_built', 'updated_at', 'city',
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

        # Build WHERE clauses
        conditions = ["idx_opt_in = 1"]  # Only IDX-opted-in listings
        params = []

        # Status filter (default: ACTIVE)
        status = request.args.get('status', 'ACTIVE').upper()
        if status:
            conditions.append("UPPER(status) = ?")
            params.append(status)

        # City filter
        city = request.args.get('city')
        if city:
            conditions.append("LOWER(city) = LOWER(?)")
            params.append(city)

        # County filter
        county = request.args.get('county')
        if county:
            conditions.append("LOWER(county) = LOWER(?)")
            params.append(county)

        # Price range
        min_price = request.args.get('min_price', type=int)
        if min_price is not None:
            conditions.append("list_price >= ?")
            params.append(min_price)

        max_price = request.args.get('max_price', type=int)
        if max_price is not None:
            conditions.append("list_price <= ?")
            params.append(max_price)

        # Beds/baths
        min_beds = request.args.get('min_beds', type=int)
        if min_beds is not None:
            conditions.append("beds >= ?")
            params.append(min_beds)

        min_baths = request.args.get('min_baths', type=float)
        if min_baths is not None:
            conditions.append("baths >= ?")
            params.append(min_baths)

        # Sqft
        min_sqft = request.args.get('min_sqft', type=int)
        if min_sqft is not None:
            conditions.append("sqft >= ?")
            params.append(min_sqft)

        # Acreage
        min_acreage = request.args.get('min_acreage', type=float)
        if min_acreage is not None:
            conditions.append("acreage >= ?")
            params.append(min_acreage)

        # Max days on market
        max_dom = request.args.get('max_dom', type=int)
        if max_dom is not None:
            conditions.append("days_on_market <= ?")
            params.append(max_dom)

        # Property type
        property_type = request.args.get('property_type')
        if property_type:
            conditions.append("property_type = ?")
            params.append(property_type)

        # MLS source
        mls_source = request.args.get('mls_source')
        if mls_source:
            conditions.append("mls_source = ?")
            params.append(mls_source)

        # Full-text search
        q = request.args.get('q')
        if q:
            search_term = f"%{q}%"
            conditions.append(
                "(address LIKE ? OR city LIKE ? OR county LIKE ? "
                "OR subdivision LIKE ? OR public_remarks LIKE ?)"
            )
            params.extend([search_term] * 5)

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
        where_clause = " AND ".join(conditions)
        query_fields = PUBLIC_LIST_FIELDS + ['idx_address_display']
        fields_str = ", ".join(query_fields)

        # Get total count
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
            f"SELECT {fields_str} FROM listings WHERE id = ? AND idx_opt_in = 1",
            [listing_id]
        ).fetchone()

        db.close()

        if not row:
            return jsonify({
                'success': False,
                'error': {'code': 'NOT_FOUND', 'message': 'Listing not found'}
            }), 404

        listing = row_to_dict(row)

        # Suppress address if opted out
        if not listing.get('idx_address_display'):
            listing['address'] = 'Address Withheld'
            listing['latitude'] = None
            listing['longitude'] = None

        # Parse photos JSON if present
        if listing.get('photos') and isinstance(listing['photos'], str):
            try:
                listing['photos'] = json.loads(listing['photos'])
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

        query = (
            f"SELECT {area_type} as name, COUNT(*) as listing_count, "
            f"MIN(list_price) as min_price, MAX(list_price) as max_price, "
            f"AVG(list_price) as avg_price "
            f"FROM listings "
            f"WHERE idx_opt_in = 1 AND UPPER(status) = ? AND {area_type} IS NOT NULL "
            f"GROUP BY {area_type} "
            f"ORDER BY listing_count DESC"
        )

        rows = db.execute(query, [status]).fetchall()
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

        # Overall stats for active listings
        overall = db.execute("""
            SELECT
                COUNT(*) as total_listings,
                COUNT(CASE WHEN UPPER(status) = 'ACTIVE' THEN 1 END) as active_listings,
                COUNT(CASE WHEN UPPER(status) = 'PENDING' THEN 1 END) as pending_listings,
                MIN(CASE WHEN UPPER(status) = 'ACTIVE' THEN list_price END) as min_price,
                MAX(CASE WHEN UPPER(status) = 'ACTIVE' THEN list_price END) as max_price,
                AVG(CASE WHEN UPPER(status) = 'ACTIVE' THEN list_price END) as avg_price,
                COUNT(DISTINCT city) as cities_served,
                COUNT(DISTINCT county) as counties_served
            FROM listings
            WHERE idx_opt_in = 1
        """).fetchone()

        # Breakdown by property type
        by_type = db.execute("""
            SELECT property_type, COUNT(*) as count
            FROM listings
            WHERE idx_opt_in = 1 AND UPPER(status) = 'ACTIVE'
            GROUP BY property_type
            ORDER BY count DESC
        """).fetchall()

        # Breakdown by MLS source
        by_source = db.execute("""
            SELECT mls_source, COUNT(*) as count
            FROM listings
            WHERE idx_opt_in = 1 AND UPPER(status) = 'ACTIVE'
            GROUP BY mls_source
            ORDER BY count DESC
        """).fetchall()

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
