#!/usr/bin/env python3
"""
MLS Grid API Importer

Imports listings from Canopy MLS via the MLS Grid RESO Web API.
Provides automated sync for active, pending, and sold listings.

Usage:
    python scripts/import_mlsgrid.py --full          # Full initial import
    python scripts/import_mlsgrid.py --incremental   # Incremental sync (changed since last run)
    python scripts/import_mlsgrid.py --status Active # Import only active listings
    python scripts/import_mlsgrid.py --dry-run       # Preview without database changes
    python scripts/import_mlsgrid.py --test          # Test API connection only

Prerequisites:
    - MLS Grid API access token (set MLSGRID_TOKEN in .env)
    - Contact data@canopyrealtors.com to request API access

MLS Grid Documentation:
    - https://docs.mlsgrid.com/
    - Rate limits: 2 req/sec, 7200 req/hr, 40000 req/day
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode

import requests

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'
PHOTOS_DIR = PROJECT_ROOT / 'data' / 'photos'
STATE_FILE = PROJECT_ROOT / 'data' / 'mlsgrid_sync_state.json'

# MLS Grid API Configuration
MLSGRID_BASE_URL = "https://api.mlsgrid.com/v2"
MLSGRID_DEMO_URL = "https://api-demo.mlsgrid.com/v2"

# Canopy MLS system identifier in MLS Grid
# Per docs: "carolina" = Canopy MLS
CANOPY_SYSTEM_NAME = "carolina"

# Rate limiting (MLS Grid limits: 2/sec, 7200/hr)
REQUEST_DELAY = 0.6  # seconds between requests (conservative)
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


def get_api_token() -> str:
    """Get MLS Grid API token from environment."""
    load_env()
    token = os.environ.get('MLSGRID_TOKEN')
    if not token:
        raise ValueError(
            "MLSGRID_TOKEN not found in environment.\n"
            "To get API access:\n"
            "1. Contact data@canopyrealtors.com\n"
            "2. Request MLS Grid API access\n"
            "3. Add MLSGRID_TOKEN=your_token to .env file"
        )
    return token


def load_sync_state() -> Dict:
    """Load last sync state (timestamp of last successful sync)."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_sync_state(state: Dict):
    """Save sync state for incremental imports."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


class MLSGridClient:
    """Client for MLS Grid RESO Web API."""

    def __init__(self, token: str, use_demo: bool = False):
        self.token = token
        self.base_url = MLSGRID_DEMO_URL if use_demo else MLSGRID_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json',
        })
        self.request_count = 0
        self.last_request_time = 0

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < REQUEST_DELAY:
            time.sleep(REQUEST_DELAY - elapsed)
        self.last_request_time = time.time()
        self.request_count += 1

        if self.request_count >= MAX_REQUESTS_PER_RUN:
            raise Exception(f"Reached max requests per run ({MAX_REQUESTS_PER_RUN})")

    def get(self, endpoint: str, params: Dict = None) -> Dict:
        """Make GET request to MLS Grid API."""
        self._rate_limit()

        url = f"{self.base_url}{endpoint}"
        if params:
            url += "?" + urlencode(params, safe="'$")

        response = self.session.get(url, timeout=30)

        if response.status_code == 429:
            raise Exception("Rate limit exceeded. Wait and try again later.")
        elif response.status_code == 401:
            raise Exception("Authentication failed. Check MLSGRID_TOKEN.")
        elif response.status_code != 200:
            raise Exception(f"API error {response.status_code}: {response.text}")

        return response.json()

    def get_all_pages(self, endpoint: str, params: Dict = None) -> List[Dict]:
        """Fetch all pages of results following @odata.nextLink."""
        all_results = []

        # First request
        data = self.get(endpoint, params)
        results = data.get('value', [])
        all_results.extend(results)
        print(f"  Page 1: {len(results)} records")

        # Follow pagination
        page = 2
        while '@odata.nextLink' in data:
            next_url = data['@odata.nextLink']
            # Extract path from full URL
            if next_url.startswith('http'):
                next_url = next_url.replace(self.base_url, '')

            self._rate_limit()
            response = self.session.get(
                data['@odata.nextLink'],
                timeout=30
            )
            if response.status_code != 200:
                print(f"  Warning: Page {page} failed ({response.status_code})")
                break

            data = response.json()
            results = data.get('value', [])
            all_results.extend(results)
            print(f"  Page {page}: {len(results)} records (total: {len(all_results)})")
            page += 1

        return all_results

    def test_connection(self) -> bool:
        """Test API connection and show available data."""
        print("Testing MLS Grid API connection...")
        try:
            # Simple test query - get 1 property from Canopy
            data = self.get("/Property", {
                "$filter": f"OriginatingSystemName eq '{CANOPY_SYSTEM_NAME}' and MlgCanView eq true",
                "$top": "1",
            })

            if 'value' in data and len(data['value']) > 0:
                prop = data['value'][0]
                print(f"\nConnection successful!")
                print(f"Sample property from Canopy MLS:")
                print(f"  ListingId: {prop.get('ListingId')}")
                print(f"  Address: {prop.get('UnparsedAddress') or prop.get('StreetNumber', '')} {prop.get('StreetName', '')}")
                print(f"  Price: ${prop.get('ListPrice', 0):,}")
                print(f"  Status: {prop.get('StandardStatus')}")
                print(f"  Type: {prop.get('PropertyType')}")
                return True
            else:
                print("Connection successful but no data returned")
                print("This may be normal if you don't have Canopy MLS access yet")
                return True

        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def fetch_properties(
        self,
        status: Optional[str] = None,
        modified_since: Optional[datetime] = None,
        property_types: List[str] = None,
        expand_media: bool = True,
    ) -> List[Dict]:
        """
        Fetch properties from Canopy MLS.

        Args:
            status: Filter by StandardStatus (Active, Pending, Closed, etc.)
            modified_since: Only records modified after this timestamp
            property_types: Filter by PropertyType (Residential, Land, etc.)
            expand_media: Include Media (photos) in response
        """
        # Build filter clauses
        filters = [
            f"OriginatingSystemName eq '{CANOPY_SYSTEM_NAME}'",
            "MlgCanView eq true",  # Exclude deleted records
        ]

        if status:
            filters.append(f"StandardStatus eq '{status}'")

        if modified_since:
            # Format as ISO 8601 UTC
            ts = modified_since.strftime('%Y-%m-%dT%H:%M:%S.00Z')
            filters.append(f"ModificationTimestamp gt {ts}")

        if property_types:
            type_clauses = " or ".join([f"PropertyType eq '{pt}'" for pt in property_types])
            filters.append(f"({type_clauses})")

        filter_str = " and ".join(filters)

        # Build params
        params = {
            "$filter": filter_str,
        }

        if expand_media:
            params["$expand"] = "Media"

        print(f"Fetching properties...")
        print(f"  Filter: {filter_str}")

        return self.get_all_pages("/Property", params)


# RESO to myDREAMS field mapping
def map_status(reso_status: str) -> str:
    """Map RESO StandardStatus to myDREAMS status."""
    mapping = {
        'Active': 'ACTIVE',
        'Active Under Contract': 'PENDING',
        'Pending': 'PENDING',
        'Closed': 'SOLD',
        'Expired': 'EXPIRED',
        'Withdrawn': 'WITHDRAWN',
        'Canceled': 'CANCELLED',
        'Coming Soon': 'COMING_SOON',
        'Hold': 'HOLD',
    }
    return mapping.get(reso_status, reso_status.upper() if reso_status else 'UNKNOWN')


def map_property_type(reso_type: str) -> str:
    """Map RESO PropertyType to myDREAMS property_type."""
    mapping = {
        'Residential': 'Residential',
        'Land': 'Land',
        'Farm': 'Farm',
        'Commercial Sale': 'Commercial',
        'Residential Income': 'Multi-Family',
        'Manufactured In Park': 'Manufactured',
    }
    return mapping.get(reso_type, reso_type)


def parse_date(date_str: str) -> Optional[str]:
    """Parse RESO date string to YYYY-MM-DD format."""
    if not date_str:
        return None
    # Handle various formats
    for fmt in ['%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d']:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


def extract_photos(media_list: List[Dict]) -> tuple[Optional[str], List[str]]:
    """
    Extract photo URLs from RESO Media array.

    Returns:
        (primary_photo_url, list_of_all_photo_urls)
    """
    if not media_list:
        return None, []

    photos = []
    primary = None

    for media in media_list:
        if media.get('MediaCategory') != 'Photo':
            continue

        url = media.get('MediaURL')
        if not url:
            continue

        photos.append(url)

        # First photo or one marked as primary
        if not primary or media.get('Order') == 1:
            primary = url

    return primary, photos


def generate_listing_id(mls_number: str, mls_source: str = 'CanopyMLS') -> str:
    """Generate a unique listing ID."""
    hash_input = f"{mls_source}:{mls_number}"
    hash_val = hashlib.md5(hash_input.encode()).hexdigest()[:12]
    return f"lst_{hash_val}"


def normalize_apn(apn: str) -> str:
    """Normalize APN for matching - remove dashes and special chars."""
    if not apn:
        return ''
    return re.sub(r'[-/\s]', '', apn.strip())


def find_parcel_by_apn(conn: sqlite3.Connection, apn: str) -> Optional[Dict]:
    """Find a parcel by APN, trying various normalizations."""
    if not apn:
        return None

    # Try exact match first
    row = conn.execute(
        "SELECT id, address, city, county, state, zip, latitude, longitude FROM parcels WHERE apn = ?",
        [apn]
    ).fetchone()
    if row:
        return dict(row)

    # Try normalized (no dashes)
    normalized = normalize_apn(apn)
    if normalized != apn:
        row = conn.execute(
            "SELECT id, address, city, county, state, zip, latitude, longitude FROM parcels WHERE REPLACE(REPLACE(apn, '-', ''), ' ', '') = ?",
            [normalized]
        ).fetchone()
        if row:
            return dict(row)

    return None


def map_reso_to_listing(prop: Dict) -> Dict[str, Any]:
    """
    Map RESO property record to myDREAMS listing schema.

    RESO Data Dictionary reference: https://ddwiki.reso.org/
    """
    # Extract media/photos
    media = prop.get('Media', [])
    primary_photo, all_photos = extract_photos(media)

    # Build address
    street_parts = [
        prop.get('StreetNumber', ''),
        prop.get('StreetDirPrefix', ''),
        prop.get('StreetName', ''),
        prop.get('StreetSuffix', ''),
        prop.get('StreetDirSuffix', ''),
    ]
    address = ' '.join(p for p in street_parts if p).strip()
    if not address:
        address = prop.get('UnparsedAddress', '')

    # Calculate total baths
    full_baths = prop.get('BathroomsFull', 0) or 0
    half_baths = prop.get('BathroomsHalf', 0) or 0
    total_baths = full_baths + (half_baths * 0.5) if full_baths or half_baths else None

    # Map the record
    listing = {
        # Identifiers
        'mls_number': prop.get('ListingId'),
        'mls_source': 'CanopyMLS',
        'mlsgrid_key': prop.get('ListingKey'),  # MLS Grid unique key

        # Status & Dates
        'status': map_status(prop.get('StandardStatus')),
        'list_date': parse_date(prop.get('ListingContractDate') or prop.get('OnMarketDate')),
        'sold_date': parse_date(prop.get('CloseDate')),
        'days_on_market': prop.get('DaysOnMarket'),

        # Pricing
        'list_price': prop.get('ListPrice'),
        'original_list_price': prop.get('OriginalListPrice'),
        'sold_price': prop.get('ClosePrice'),

        # Location
        'address': address,
        'city': prop.get('City'),
        'state': prop.get('StateOrProvince', 'NC'),
        'zip': prop.get('PostalCode'),
        'county': prop.get('CountyOrParish'),
        'latitude': prop.get('Latitude'),
        'longitude': prop.get('Longitude'),

        # Property Details
        'property_type': map_property_type(prop.get('PropertyType')),
        'property_subtype': prop.get('PropertySubType'),
        'beds': prop.get('BedroomsTotal'),
        'baths': total_baths,
        'sqft': prop.get('LivingArea'),
        'acreage': prop.get('LotSizeAcres'),
        'lot_sqft': prop.get('LotSizeSquareFeet'),
        'year_built': prop.get('YearBuilt'),
        'stories': prop.get('StoriesTotal'),
        'garage_spaces': prop.get('GarageSpaces'),

        # Features (as JSON strings for array fields)
        'heating': json.dumps(prop.get('Heating', [])) if prop.get('Heating') else None,
        'cooling': json.dumps(prop.get('Cooling', [])) if prop.get('Cooling') else None,
        'appliances': json.dumps(prop.get('Appliances', [])) if prop.get('Appliances') else None,
        'interior_features': json.dumps(prop.get('InteriorFeatures', [])) if prop.get('InteriorFeatures') else None,
        'exterior_features': json.dumps(prop.get('ExteriorFeatures', [])) if prop.get('ExteriorFeatures') else None,

        # HOA
        'hoa_fee': prop.get('AssociationFee'),
        'hoa_frequency': prop.get('AssociationFeeFrequency'),

        # Agent Info
        'listing_agent_id': prop.get('ListAgentMlsId'),
        'listing_agent_name': prop.get('ListAgentFullName'),
        'listing_agent_phone': prop.get('ListAgentDirectPhone'),
        'listing_agent_email': prop.get('ListAgentEmail'),
        'listing_office_id': prop.get('ListOfficeMlsId'),
        'listing_office_name': prop.get('ListOfficeName'),

        # Photos
        'primary_photo': primary_photo,
        'photos': json.dumps(all_photos) if all_photos else None,
        'photo_count': len(all_photos),
        'photo_source': 'mlsgrid' if all_photos else None,
        'photo_verified_at': datetime.now().isoformat() if all_photos else None,
        'photo_review_status': 'verified' if all_photos else None,

        # Parcel link
        'parcel_number': prop.get('ParcelNumber'),

        # Descriptions
        'public_remarks': prop.get('PublicRemarks'),

        # Metadata
        'modification_timestamp': prop.get('ModificationTimestamp'),
    }

    return listing


def upsert_listing(conn: sqlite3.Connection, listing: Dict, dry_run: bool = False) -> str:
    """
    Insert or update a listing in the database.

    Returns: 'created', 'updated', or 'skipped'
    """
    mls_number = listing['mls_number']
    mls_source = listing['mls_source']

    if not mls_number:
        return 'skipped'

    # Check if exists
    existing = conn.execute(
        "SELECT id, mls_number FROM listings WHERE mls_source = ? AND mls_number = ?",
        [mls_source, mls_number]
    ).fetchone()

    # Try to match parcel
    parcel = None
    parcel_id = None
    if listing.get('parcel_number'):
        parcel = find_parcel_by_apn(conn, listing['parcel_number'])
        if parcel:
            parcel_id = parcel['id']
            # Inherit coords from parcel if not in listing
            if not listing.get('latitude') and parcel.get('latitude'):
                listing['latitude'] = parcel['latitude']
                listing['longitude'] = parcel['longitude']

    listing_id = generate_listing_id(mls_number, mls_source)
    now = datetime.now().isoformat()

    if dry_run:
        return 'created' if not existing else 'updated'

    if existing:
        # Update existing listing
        update_fields = [
            'status', 'list_price', 'original_list_price', 'sold_price',
            'list_date', 'sold_date', 'days_on_market',
            'beds', 'baths', 'sqft', 'acreage', 'year_built',
            'property_type', 'property_subtype',
            'latitude', 'longitude',
            'listing_agent_id', 'listing_agent_name', 'listing_agent_phone', 'listing_agent_email',
            'listing_office_id', 'listing_office_name',
            'hoa_fee', 'hoa_frequency',
            'public_remarks',
        ]

        # Only update photos if we have new ones
        if listing.get('photos') and listing.get('photo_count', 0) > 0:
            update_fields.extend(['primary_photo', 'photos', 'photo_count', 'photo_source', 'photo_verified_at', 'photo_review_status'])

        set_clause = ", ".join([f"{f} = ?" for f in update_fields])
        values = [listing.get(f) for f in update_fields]
        values.extend([now, parcel_id, existing['id']])

        conn.execute(
            f"UPDATE listings SET {set_clause}, updated_at = ?, parcel_id = ? WHERE id = ?",
            values
        )
        return 'updated'
    else:
        # Insert new listing
        listing['id'] = listing_id
        listing['parcel_id'] = parcel_id
        listing['created_at'] = now
        listing['updated_at'] = now

        # Build insert
        fields = [k for k in listing.keys() if listing[k] is not None]
        placeholders = ", ".join(["?" for _ in fields])
        values = [listing[f] for f in fields]

        conn.execute(
            f"INSERT INTO listings ({', '.join(fields)}) VALUES ({placeholders})",
            values
        )
        return 'created'


def run_import(
    client: MLSGridClient,
    status: Optional[str] = None,
    incremental: bool = False,
    dry_run: bool = False,
    property_types: List[str] = None,
) -> Dict[str, int]:
    """
    Run the import process.

    Args:
        client: MLSGridClient instance
        status: Filter by status (Active, Pending, Closed)
        incremental: Only fetch records modified since last sync
        dry_run: Preview without database changes
        property_types: Filter by property type

    Returns:
        Stats dict with counts
    """
    stats = {
        'fetched': 0,
        'created': 0,
        'updated': 0,
        'skipped': 0,
        'matched_parcel': 0,
        'with_photos': 0,
        'errors': 0,
    }

    # Load sync state for incremental
    modified_since = None
    if incremental:
        state = load_sync_state()
        if 'last_sync' in state:
            modified_since = datetime.fromisoformat(state['last_sync'])
            print(f"Incremental sync: fetching records modified since {modified_since}")
        else:
            print("No previous sync state found. Running full import.")

    # Fetch properties from API
    try:
        properties = client.fetch_properties(
            status=status,
            modified_since=modified_since,
            property_types=property_types,
            expand_media=True,
        )
    except Exception as e:
        print(f"Error fetching properties: {e}")
        return stats

    stats['fetched'] = len(properties)
    print(f"\nFetched {len(properties)} properties from MLS Grid")

    if not properties:
        print("No properties to import")
        return stats

    if dry_run:
        print("\n=== DRY RUN - No database changes ===")

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Process each property
    for i, prop in enumerate(properties):
        try:
            listing = map_reso_to_listing(prop)

            result = upsert_listing(conn, listing, dry_run=dry_run)

            if result == 'created':
                stats['created'] += 1
            elif result == 'updated':
                stats['updated'] += 1
            else:
                stats['skipped'] += 1

            if listing.get('parcel_id'):
                stats['matched_parcel'] += 1
            if listing.get('photo_count', 0) > 0:
                stats['with_photos'] += 1

            # Progress indicator
            if (i + 1) % 100 == 0:
                print(f"  Processed {i + 1}/{len(properties)}...")

        except Exception as e:
            print(f"  Error processing {prop.get('ListingId')}: {e}")
            stats['errors'] += 1

    if not dry_run:
        conn.commit()

        # Save sync state
        save_sync_state({
            'last_sync': datetime.now(timezone.utc).isoformat(),
            'records_synced': len(properties),
            'status_filter': status,
        })

    conn.close()

    return stats


def print_stats(stats: Dict[str, int]):
    """Print import statistics."""
    print("\n" + "=" * 50)
    print("IMPORT SUMMARY")
    print("=" * 50)
    print(f"  Fetched from API:    {stats['fetched']:,}")
    print(f"  Created:             {stats['created']:,}")
    print(f"  Updated:             {stats['updated']:,}")
    print(f"  Skipped:             {stats['skipped']:,}")
    print(f"  Matched to parcel:   {stats['matched_parcel']:,}")
    print(f"  With photos:         {stats['with_photos']:,}")
    print(f"  Errors:              {stats['errors']:,}")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(
        description="Import listings from Canopy MLS via MLS Grid API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Test API connection
    python scripts/import_mlsgrid.py --test

    # Full import of active listings
    python scripts/import_mlsgrid.py --full --status Active

    # Incremental sync (only changes since last run)
    python scripts/import_mlsgrid.py --incremental

    # Preview without database changes
    python scripts/import_mlsgrid.py --full --dry-run

    # Import specific property types
    python scripts/import_mlsgrid.py --full --types Residential Land
        """
    )

    parser.add_argument('--test', action='store_true',
                        help='Test API connection only')
    parser.add_argument('--full', action='store_true',
                        help='Full import (all matching records)')
    parser.add_argument('--incremental', action='store_true',
                        help='Incremental sync (only records modified since last run)')
    parser.add_argument('--status', choices=['Active', 'Pending', 'Closed', 'Expired', 'Withdrawn'],
                        help='Filter by listing status')
    parser.add_argument('--types', nargs='+',
                        choices=['Residential', 'Land', 'Farm', 'Commercial Sale', 'Residential Income'],
                        help='Filter by property types')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview without database changes')
    parser.add_argument('--demo', action='store_true',
                        help='Use demo API (for testing without production access)')

    args = parser.parse_args()

    # Validate args
    if not any([args.test, args.full, args.incremental]):
        parser.print_help()
        print("\nError: Must specify --test, --full, or --incremental")
        return 1

    # Get token and create client
    try:
        token = get_api_token()
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    client = MLSGridClient(token, use_demo=args.demo)

    # Test mode
    if args.test:
        success = client.test_connection()
        return 0 if success else 1

    # Run import
    stats = run_import(
        client,
        status=args.status,
        incremental=args.incremental,
        dry_run=args.dry_run,
        property_types=args.types,
    )

    print_stats(stats)
    return 0 if stats['errors'] == 0 else 1


if __name__ == '__main__':
    exit(main())
