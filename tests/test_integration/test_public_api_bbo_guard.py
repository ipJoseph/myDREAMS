"""
Integration tests: BBO data must NEVER appear in public API responses.

These tests verify that BBO-only fields (private_remarks, showing_instructions,
buyer_agent_*) are excluded from all public API endpoints, and that listings
with idx_opt_in=0 are never returned.

Run: python3 -m pytest tests/test_integration/test_public_api_bbo_guard.py -v
"""

import json
import os
import sqlite3
import sys
import uuid
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'apps' / 'property-api'))

# Fields that must NEVER appear in public API responses
BBO_FORBIDDEN_FIELDS = {
    'private_remarks',
    'showing_instructions',
    'buyer_agent_id',
    'buyer_agent_name',
    'buyer_office_id',
    'buyer_office_name',
    'vow_opt_in',
    'expiration_date',
    'added_for',
    'added_by',
    'notes',
}


def _make_listing(listing_id, idx_opt_in=1, status='ACTIVE', **overrides):
    """Build a listing dict with required fields."""
    base = {
        'id': listing_id,
        'mls_source': 'TestMLS',
        'mls_number': f'TEST{listing_id[-6:]}',
        'status': status,
        'list_price': 350000,
        'list_date': '2026-01-15',
        'address': f'{listing_id} Test Ave',
        'city': 'Franklin',
        'state': 'NC',
        'zip': '28734',
        'county': 'Macon',
        'latitude': 35.18,
        'longitude': -83.38,
        'property_type': 'Residential',
        'beds': 3,
        'baths': 2.0,
        'sqft': 1800,
        'acreage': 1.5,
        'year_built': 2005,
        'primary_photo': 'https://example.com/photo.jpg',
        'photo_count': 5,
        'public_remarks': 'Beautiful mountain home.',
        'private_remarks': 'Seller motivated. Call for gate code.',
        'showing_instructions': 'Lockbox on front door, code 1234',
        'buyer_agent_id': 'BA001',
        'buyer_agent_name': 'Jane Buyer Agent',
        'buyer_office_id': 'BO001',
        'buyer_office_name': 'Buyer Realty',
        'listing_agent_name': 'John Listing Agent',
        'listing_office_name': 'Listing Realty',
        'idx_opt_in': idx_opt_in,
        'idx_address_display': 1,
        'source': 'test',
    }
    base.update(overrides)
    return base


def _insert_listing(db_conn, listing):
    """Insert a listing into the database."""
    cols = ', '.join(listing.keys())
    placeholders = ', '.join(['?'] * len(listing))
    db_conn.execute(
        f'INSERT OR REPLACE INTO listings ({cols}) VALUES ({placeholders})',
        list(listing.values())
    )


def _insert_package_with_listing(db_conn, listing_id, share_token):
    """Create a property package with a listing and return the package id."""
    pkg_id = f'pkg_{uuid.uuid4().hex[:12]}'
    db_conn.execute(
        'INSERT INTO property_packages (id, name, status, share_token) VALUES (?, ?, ?, ?)',
        [pkg_id, 'Test Package', 'active', share_token]
    )
    pp_id = f'pp_{uuid.uuid4().hex[:12]}'
    db_conn.execute(
        'INSERT INTO package_properties (id, package_id, listing_id, display_order) VALUES (?, ?, ?, ?)',
        [pp_id, pkg_id, listing_id, 1]
    )
    return pkg_id


@pytest.fixture
def app_with_test_db(tmp_path):
    """Create a Flask test app with a seeded test database."""
    db_path = str(tmp_path / 'test_dreams.db')

    # Create schema from production database structure
    conn = sqlite3.connect(db_path)
    conn.execute('''CREATE TABLE listings (
        id TEXT PRIMARY KEY, parcel_id TEXT, mls_source TEXT, mls_number TEXT,
        status TEXT, list_price INTEGER, list_date TEXT, sold_price INTEGER,
        sold_date TEXT, days_on_market INTEGER, beds INTEGER, baths REAL,
        sqft INTEGER, year_built INTEGER, property_type TEXT, style TEXT,
        views TEXT, amenities TEXT, heating TEXT, cooling TEXT, garage TEXT,
        hoa_fee INTEGER, photos TEXT, primary_photo TEXT, virtual_tour_url TEXT,
        mls_url TEXT, idx_url TEXT, redfin_url TEXT, redfin_id TEXT,
        zillow_url TEXT, zillow_id TEXT, listing_agent_id TEXT,
        listing_agent_name TEXT, listing_agent_phone TEXT,
        listing_agent_email TEXT, listing_office_id TEXT,
        listing_office_name TEXT, added_for TEXT, added_by TEXT, notes TEXT,
        source TEXT, captured_at TEXT, updated_at TEXT, photo_source TEXT,
        photo_confidence REAL, photo_verified_at TEXT, photo_verified_by TEXT,
        photo_review_status TEXT, photo_count INTEGER DEFAULT 0,
        address TEXT, city TEXT, state TEXT DEFAULT 'NC', zip TEXT,
        county TEXT, latitude REAL, longitude REAL, acreage REAL,
        is_residential INTEGER DEFAULT 1, listing_key TEXT,
        property_subtype TEXT, original_list_price INTEGER, lot_sqft INTEGER,
        garage_spaces INTEGER, appliances TEXT, interior_features TEXT,
        exterior_features TEXT, water_source TEXT, construction_materials TEXT,
        foundation TEXT, flooring TEXT, fireplace_features TEXT,
        parking_features TEXT, hoa_frequency TEXT, tax_annual_amount INTEGER,
        tax_assessed_value INTEGER, tax_year INTEGER, buyer_agent_id TEXT,
        buyer_agent_name TEXT, buyer_office_id TEXT, buyer_office_name TEXT,
        public_remarks TEXT, private_remarks TEXT, showing_instructions TEXT,
        parcel_number TEXT, subdivision TEXT, directions TEXT,
        expiration_date TEXT, modification_timestamp TEXT,
        idx_opt_in INTEGER DEFAULT 1, idx_address_display INTEGER DEFAULT 1,
        roof TEXT, sewer TEXT, stories INTEGER, vow_opt_in INTEGER,
        photo_local_path TEXT, documents_count INTEGER,
        documents_available TEXT, documents_change_timestamp TEXT,
        elevation_feet INTEGER, flood_zone TEXT, flood_factor INTEGER,
        view_potential INTEGER
    )''')

    conn.execute('''CREATE TABLE property_packages (
        id TEXT PRIMARY KEY, lead_id TEXT, intake_form_id TEXT,
        name TEXT NOT NULL, description TEXT, status TEXT DEFAULT 'draft',
        sent_at TEXT, viewed_at TEXT, view_count INTEGER DEFAULT 0,
        share_token TEXT UNIQUE, share_url TEXT, expires_at TEXT,
        created_by TEXT, notes TEXT, created_at TEXT, updated_at TEXT,
        user_id TEXT, collection_type TEXT DEFAULT 'agent_package',
        showing_requested INTEGER DEFAULT 0, showing_requested_at TEXT,
        derived_from_id TEXT, derived_from_type TEXT,
        is_public INTEGER DEFAULT 0, featured_order INTEGER,
        cover_image TEXT, criteria_json TEXT, auto_refresh INTEGER DEFAULT 0,
        last_refreshed_at TEXT, slug TEXT
    )''')

    conn.execute('''CREATE TABLE package_properties (
        id TEXT PRIMARY KEY, package_id TEXT NOT NULL,
        listing_id TEXT NOT NULL, display_order INTEGER,
        agent_notes TEXT, client_notes TEXT, highlight_features TEXT,
        client_favorited INTEGER DEFAULT 0, client_rating INTEGER,
        client_comments TEXT, client_viewed_at TEXT,
        showing_requested INTEGER DEFAULT 0, showing_scheduled_at TEXT,
        showing_completed_at TEXT, added_at TEXT
    )''')

    # Seed test data
    # IDX listing (should appear in public API, without BBO fields)
    _insert_listing(conn, _make_listing('lst_idx_001', idx_opt_in=1))
    _insert_listing(conn, _make_listing('lst_idx_002', idx_opt_in=1, city='Sylva', county='Jackson'))

    # BBO-only listing (should NEVER appear in public API)
    _insert_listing(conn, _make_listing('lst_bbo_001', idx_opt_in=0))
    _insert_listing(conn, _make_listing('lst_bbo_002', idx_opt_in=0, city='Cashiers'))

    # IDX listing with address display suppressed
    _insert_listing(conn, _make_listing(
        'lst_hidden_addr', idx_opt_in=1, idx_address_display=0
    ))

    # Shared package containing one IDX and one BBO listing
    _insert_package_with_listing(conn, 'lst_idx_001', 'share_test_token')
    # Also add the BBO listing to the same package
    pp_id = f'pp_{uuid.uuid4().hex[:12]}'
    conn.execute(
        'INSERT INTO package_properties (id, package_id, listing_id, display_order) VALUES (?, ?, ?, ?)',
        [pp_id, conn.execute('SELECT id FROM property_packages WHERE share_token = ?', ['share_test_token']).fetchone()[0], 'lst_bbo_001', 2]
    )

    conn.commit()
    conn.close()

    # Set env and import app
    os.environ['DREAMS_DB_PATH'] = db_path
    os.environ['DREAMS_ENV'] = 'test'
    # Clear any cached API key so public endpoints work
    os.environ.pop('DREAMS_API_KEY', None)

    from app import app
    app.config['TESTING'] = True

    with app.test_client() as client:
        yield client, db_path


def _assert_no_bbo_fields(data, context=''):
    """Assert that no BBO-forbidden fields exist in a response dict or list."""
    if isinstance(data, list):
        for i, item in enumerate(data):
            _assert_no_bbo_fields(item, context=f'{context}[{i}]')
    elif isinstance(data, dict):
        for field in BBO_FORBIDDEN_FIELDS:
            assert field not in data, (
                f"BBO field '{field}' found in public API response{context}. "
                f"Value: {data[field]!r}"
            )


# ---------------------------------------------------------------------------
# Test: Listing search excludes BBO-only listings
# ---------------------------------------------------------------------------

class TestListingSearch:
    def test_search_excludes_bbo_listings(self, app_with_test_db):
        client, _ = app_with_test_db
        resp = client.get('/api/public/listings')
        data = resp.get_json()

        assert data['success'] is True
        listing_ids = [l['id'] for l in data['data']]

        # IDX listings should appear
        assert 'lst_idx_001' in listing_ids
        assert 'lst_idx_002' in listing_ids

        # BBO-only listings must NOT appear
        assert 'lst_bbo_001' not in listing_ids
        assert 'lst_bbo_002' not in listing_ids

    def test_search_response_has_no_bbo_fields(self, app_with_test_db):
        client, _ = app_with_test_db
        resp = client.get('/api/public/listings')
        data = resp.get_json()

        assert data['success'] is True
        _assert_no_bbo_fields(data['data'], context=' (listing search)')

    def test_search_with_city_filter_excludes_bbo(self, app_with_test_db):
        """BBO listing in Cashiers should not appear even when filtering by that city."""
        client, _ = app_with_test_db
        resp = client.get('/api/public/listings?city=Cashiers')
        data = resp.get_json()

        assert data['success'] is True
        listing_ids = [l['id'] for l in data['data']]
        assert 'lst_bbo_002' not in listing_ids


# ---------------------------------------------------------------------------
# Test: Map markers exclude BBO-only listings
# ---------------------------------------------------------------------------

class TestMapMarkers:
    def test_map_excludes_bbo_listings(self, app_with_test_db):
        client, _ = app_with_test_db
        resp = client.get('/api/public/listings/map')
        data = resp.get_json()

        assert data['success'] is True
        listing_ids = [l['id'] for l in data['data']]

        assert 'lst_bbo_001' not in listing_ids
        assert 'lst_bbo_002' not in listing_ids

    def test_map_response_has_no_bbo_fields(self, app_with_test_db):
        client, _ = app_with_test_db
        resp = client.get('/api/public/listings/map')
        data = resp.get_json()

        assert data['success'] is True
        _assert_no_bbo_fields(data['data'], context=' (map markers)')


# ---------------------------------------------------------------------------
# Test: Single listing detail excludes BBO fields
# ---------------------------------------------------------------------------

class TestListingDetail:
    def test_idx_listing_has_no_bbo_fields(self, app_with_test_db):
        client, _ = app_with_test_db
        resp = client.get('/api/public/listings/lst_idx_001')
        data = resp.get_json()

        assert data['success'] is True
        _assert_no_bbo_fields(data['data'], context=' (listing detail)')

    def test_bbo_listing_returns_404(self, app_with_test_db):
        """A BBO-only listing should return 404, not the listing data."""
        client, _ = app_with_test_db
        resp = client.get('/api/public/listings/lst_bbo_001')
        data = resp.get_json()

        assert resp.status_code == 404
        assert data['success'] is False

    def test_detail_never_contains_private_remarks(self, app_with_test_db):
        """Even for IDX listings that have private_remarks in the DB."""
        client, _ = app_with_test_db
        resp = client.get('/api/public/listings/lst_idx_001')
        data = resp.get_json()

        assert 'private_remarks' not in data['data']
        assert 'showing_instructions' not in data['data']
        assert 'buyer_agent_name' not in data['data']


# ---------------------------------------------------------------------------
# Test: Shared collections exclude BBO data
# ---------------------------------------------------------------------------

class TestSharedCollections:
    def test_shared_collection_excludes_bbo_listings(self, app_with_test_db):
        """Package has both IDX and BBO listings; only IDX should appear."""
        client, _ = app_with_test_db
        resp = client.get('/api/public/collections/share_test_token')
        data = resp.get_json()

        assert data['success'] is True
        listing_ids = [l['id'] for l in data['data']['listings']]

        assert 'lst_idx_001' in listing_ids
        assert 'lst_bbo_001' not in listing_ids

    def test_shared_collection_has_no_bbo_fields(self, app_with_test_db):
        client, _ = app_with_test_db
        resp = client.get('/api/public/collections/share_test_token')
        data = resp.get_json()

        assert data['success'] is True
        _assert_no_bbo_fields(data['data']['listings'], context=' (shared collection)')


# ---------------------------------------------------------------------------
# Test: Address suppression works correctly
# ---------------------------------------------------------------------------

class TestAddressSuppression:
    def test_hidden_address_listing_suppresses_location(self, app_with_test_db):
        client, _ = app_with_test_db
        resp = client.get('/api/public/listings/lst_hidden_addr')
        data = resp.get_json()

        assert data['success'] is True
        assert data['data']['address'] == 'Address Withheld'
        assert data['data']['latitude'] is None
        assert data['data']['longitude'] is None

    def test_hidden_address_excluded_from_map(self, app_with_test_db):
        """Listings with idx_address_display=0 should not appear on the map."""
        client, _ = app_with_test_db
        resp = client.get('/api/public/listings/map')
        data = resp.get_json()

        listing_ids = [l['id'] for l in data['data']]
        assert 'lst_hidden_addr' not in listing_ids


# ---------------------------------------------------------------------------
# Test: Areas and stats endpoints only count IDX listings
# ---------------------------------------------------------------------------

class TestAggregateEndpoints:
    def test_areas_only_count_idx_listings(self, app_with_test_db):
        client, _ = app_with_test_db
        resp = client.get('/api/public/areas?type=city')
        data = resp.get_json()

        assert data['success'] is True
        city_names = [a['name'] for a in data['data']]

        # Cashiers only has a BBO listing, so it should not appear
        assert 'Cashiers' not in city_names
        # Franklin has IDX listings, so it should appear
        assert 'Franklin' in city_names

    def test_stats_only_count_idx_listings(self, app_with_test_db):
        client, _ = app_with_test_db
        resp = client.get('/api/public/stats')
        data = resp.get_json()

        assert data['success'] is True
        # We have 3 IDX listings (lst_idx_001, lst_idx_002, lst_hidden_addr)
        # and 2 BBO listings that should NOT be counted
        assert data['data']['active_listings'] == 3


# ---------------------------------------------------------------------------
# Test: Field whitelist completeness
# ---------------------------------------------------------------------------

class TestFieldWhitelists:
    def test_public_listing_fields_exclude_all_bbo_fields(self):
        """Verify the PUBLIC_LISTING_FIELDS constant doesn't contain BBO fields."""
        from routes.public import PUBLIC_LISTING_FIELDS
        for field in BBO_FORBIDDEN_FIELDS:
            assert field not in PUBLIC_LISTING_FIELDS, (
                f"BBO field '{field}' found in PUBLIC_LISTING_FIELDS whitelist!"
            )

    def test_public_list_fields_exclude_all_bbo_fields(self):
        from routes.public import PUBLIC_LIST_FIELDS
        for field in BBO_FORBIDDEN_FIELDS:
            assert field not in PUBLIC_LIST_FIELDS, (
                f"BBO field '{field}' found in PUBLIC_LIST_FIELDS whitelist!"
            )

    def test_map_marker_fields_exclude_all_bbo_fields(self):
        from routes.public import MAP_MARKER_FIELDS
        for field in BBO_FORBIDDEN_FIELDS:
            assert field not in MAP_MARKER_FIELDS, (
                f"BBO field '{field}' found in MAP_MARKER_FIELDS whitelist!"
            )
