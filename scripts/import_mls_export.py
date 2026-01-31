#!/usr/bin/env python3
"""
MLS Export Importer

Imports listings from Carolina Smokies MLS export (CSV + Photos ZIP).
Matches listings to existing parcels via APN for data enrichment.

Usage:
    python scripts/import_mls_export.py --csv /path/to/export.csv --photos /path/to/photos.zip
    python scripts/import_mls_export.py --csv /path/to/export.csv  # CSV only, no photos
    python scripts/import_mls_export.py --dry-run  # Preview without database changes

Features:
    - Parses MLS CSV export with proper handling of quoted fields
    - Matches to existing parcels via APN (Parcel Number)
    - Extracts photos from ZIP to data/photos/
    - Creates/updates listings with full MLS data
    - Tracks import source and timestamp
"""

import argparse
import csv
import hashlib
import re
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'
PHOTOS_DIR = PROJECT_ROOT / 'data' / 'photos'


def parse_price(price_str: str) -> Optional[int]:
    """Parse price string like '$2,999,500' to integer."""
    if not price_str:
        return None
    # Remove $ and commas, convert to int
    cleaned = re.sub(r'[$,]', '', price_str.strip())
    try:
        return int(float(cleaned))
    except (ValueError, TypeError):
        return None


def parse_float(val: str) -> Optional[float]:
    """Parse float from string, handling commas."""
    if not val or val.strip() == '':
        return None
    cleaned = re.sub(r'[$,]', '', val.strip())
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def parse_int(val: str) -> Optional[int]:
    """Parse int from string."""
    if not val or val.strip() == '':
        return None
    try:
        return int(val.strip())
    except (ValueError, TypeError):
        return None


def normalize_status(status: str) -> str:
    """Normalize MLS status codes."""
    status = (status or '').strip().upper()
    status_map = {
        'ACT': 'ACTIVE',
        'ACTIVE': 'ACTIVE',
        'PND': 'PENDING',
        'PENDING': 'PENDING',
        'SLD': 'SOLD',
        'SOLD': 'SOLD',
        'WDN': 'WITHDRAWN',
        'WITHDRAWN': 'WITHDRAWN',
        'EXP': 'EXPIRED',
        'EXPIRED': 'EXPIRED',
        'CAN': 'CANCELLED',
        'CTG': 'CONTINGENT',
    }
    return status_map.get(status, status)


def normalize_apn(apn: str) -> str:
    """Normalize APN for matching - remove dashes and special chars."""
    if not apn:
        return ''
    # Remove common separators but keep the digits
    return re.sub(r'[-/\s]', '', apn.strip())


def generate_listing_id(mls_number: str, mls_source: str = 'CSMLS') -> str:
    """Generate a unique listing ID."""
    hash_input = f"{mls_source}:{mls_number}"
    hash_val = hashlib.md5(hash_input.encode()).hexdigest()[:12]
    return f"lst_{hash_val}"


def detect_csv_format(row: Dict[str, str]) -> str:
    """Detect which CSV format we're dealing with."""
    if 'MLS Number' in row:
        return 'classic'  # Classic CS MLS format with photos
    elif 'ML #' in row:
        return 'eug'  # EUG Display format
    else:
        return 'unknown'


def parse_csv_row(row: Dict[str, str], fmt: str = None) -> Dict[str, Any]:
    """Parse a CSV row into a normalized listing dict. Handles multiple formats."""
    if fmt is None:
        fmt = detect_csv_format(row)

    if fmt == 'classic':
        # Classic CS MLS format (MLS Number, Parcel ID, LA Name, etc.)
        full_baths = parse_int(row.get('Baths', '')) or 0
        half_baths = parse_int(row.get('Half Baths', '')) or 0
        total_baths = full_baths + (half_baths * 0.5) if full_baths or half_baths else None

        hoa_fee = parse_float(row.get('HOA Dues', ''))
        hoa_freq = row.get('HOA Frequency', '').strip()

        # Build address from House # and Address
        house_num = row.get('House #', '').strip()
        street = row.get('Address', '').strip()
        if house_num and street:
            address = f"{house_num} {street}"
        else:
            address = street or house_num

        listing = {
            'mls_number': row.get('MLS Number', '').strip(),
            'mls_source': 'CSMLS',
            'parcel_number': row.get('Parcel ID', '').strip(),
            'deed_reference': f"{row.get('Deed Book', '').strip()}/{row.get('Deed Page', '').strip()}".strip('/'),
            'status': 'ACTIVE',  # This export is typically active listings
            'property_type': None,
            'style': None,
            'address': address,
            'city': row.get('City', '').strip(),
            'state': row.get('State', 'NC').strip(),
            'zip': row.get('Zip Code', '').strip(),
            'county': row.get('County', '').strip(),
            'days_on_market': parse_int(row.get('Days on Market', '')),
            'beds': parse_int(row.get('Bedrooms', '')),
            'baths': total_baths,
            'list_price': parse_price(row.get('List Price', '')),
            'price_per_acre': parse_float(row.get('List Price Per ACRE', '')),
            'acreage': parse_float(row.get('Parcel Size', '')),
            'subdivision': row.get('Subdivision', '').strip(),
            'township': row.get('Township', '').strip(),
            'hoa_fee': int(hoa_fee) if hoa_fee else None,
            'hoa_frequency': hoa_freq if hoa_freq else None,
            'listing_agent_name': row.get('LA Name', '').strip(),
            'listing_agent_email': row.get('LA Email', '').strip(),
            'listing_agent_phone': row.get('LA Phone', '').strip(),
            'listing_office_id': row.get('Listing Office', '').strip(),
            'ownership': row.get('Ownership', '').strip(),
            'owner_name': row.get('Additional Owner Name', '').strip(),
        }
    else:
        # EUG Display format (ML #, Parcel Number, List Agent Full Name, etc.)
        full_baths = parse_int(row.get('Bathrooms Full', '')) or 0
        half_baths = parse_int(row.get('Bathrooms Half', '')) or 0
        total_baths = full_baths + (half_baths * 0.5) if full_baths or half_baths else None

        hoa_fee = parse_float(row.get('HOA Fee', ''))
        hoa_freq = row.get('HOA Fee Frequency', '').strip()

        listing = {
            'mls_number': row.get('ML #', '').strip(),
            'mls_source': 'CSMLS',
            'parcel_number': row.get('Parcel Number', '').strip(),
            'deed_reference': row.get('Deed Reference', '').strip(),
            'status': normalize_status(row.get('St', '')),
            'property_type': row.get('Type', '').strip(),
            'style': row.get('Levels', '').strip(),
            'address': row.get('Address', '').strip(),
            'city': row.get('City', '').strip(),
            'state': 'NC',
            'zip': None,
            'county': None,
            'days_on_market': parse_int(row.get('DOM', '')),
            'beds': parse_int(row.get('Bedrooms Total', '')),
            'baths': total_baths,
            'list_price': parse_price(row.get('List Price', '')),
            'price_per_acre': parse_float(row.get('$/Acre', '')),
            'price_per_sqft': parse_float(row.get('$/SqFt', '')),
            'acreage': parse_float(row.get('Approximate Acres', '')),
            'sqft': parse_int(row.get('Total Primary HLA', '').replace(',', '') if row.get('Total Primary HLA') else ''),
            'subdivision': row.get('Subdivision Name', '').strip(),
            'year_built': parse_int(row.get('Year Built', '')),
            'zoning': row.get('Zoning', '').strip(),
            'sewer': row.get('Sewer', '').strip(),
            'water': row.get('Water Source', '').strip(),
            'can_subdivide': row.get('Can Subdivide YN', '').strip().upper() == 'Y',
            'hoa_fee': int(hoa_fee) if hoa_fee else None,
            'hoa_frequency': hoa_freq if hoa_freq else None,
            'listing_agent_name': row.get('List Agent Full Name', '').strip(),
            'listing_agent_phone': row.get('List Agent Direct Phone', '').strip(),
            'listing_office_name': row.get('List Office Name', '').strip(),
            'lot_description': row.get('Lot Description', '').strip(),
            'plat_book': row.get('Plat Book Slide', '').strip(),
            'plat_reference': row.get('Plat Reference Section Pages', '').strip(),
        }

    return listing


def find_parcel_by_apn(conn: sqlite3.Connection, apn: str) -> Optional[Dict]:
    """Find a parcel by APN, trying various normalizations."""
    if not apn:
        return None

    # Try exact match first
    row = conn.execute(
        "SELECT id, address, city, county, state, zip FROM parcels WHERE apn = ?",
        [apn]
    ).fetchone()
    if row:
        return dict(row)

    # Try normalized (no dashes)
    normalized = normalize_apn(apn)
    if normalized != apn:
        row = conn.execute(
            "SELECT id, address, city, county, state, zip FROM parcels WHERE REPLACE(REPLACE(apn, '-', ''), ' ', '') = ?",
            [normalized]
        ).fetchone()
        if row:
            return dict(row)

    # Try with just digits
    digits_only = re.sub(r'\D', '', apn)
    if len(digits_only) >= 8:
        row = conn.execute(
            "SELECT id, address, city, county, state, zip FROM parcels WHERE REPLACE(REPLACE(REPLACE(apn, '-', ''), ' ', ''), '/', '') = ?",
            [digits_only]
        ).fetchone()
        if row:
            return dict(row)

    return None


def extract_photos(zip_path: Path, mls_numbers: set) -> Dict[str, Path]:
    """Extract photos from ZIP, returning dict of mls_number -> local path."""
    if not zip_path or not zip_path.exists():
        return {}

    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    extracted = {}

    with zipfile.ZipFile(zip_path, 'r') as zf:
        for name in zf.namelist():
            if not name.endswith('.jpg'):
                continue

            # Parse MLS number from filename (format: MLSNUM_0.jpg)
            match = re.match(r'(\d+)_\d+\.jpg', name)
            if not match:
                continue

            mls_num = match.group(1)
            if mls_num not in mls_numbers:
                continue

            # Extract to photos dir
            local_path = PHOTOS_DIR / f"{mls_num}.jpg"
            if not local_path.exists():
                with zf.open(name) as src, open(local_path, 'wb') as dst:
                    dst.write(src.read())

            extracted[mls_num] = local_path

    return extracted


def import_listings(
    csv_path: Path,
    photos_zip: Optional[Path] = None,
    dry_run: bool = False
) -> Dict[str, int]:
    """
    Import listings from MLS CSV export.

    Returns dict with stats: created, updated, matched_parcel, photos_added, errors
    """
    stats = {
        'total': 0,
        'created': 0,
        'updated': 0,
        'matched_parcel': 0,
        'photos_added': 0,
        'errors': 0,
        'skipped': 0,
    }

    # Read CSV
    print(f"Reading CSV: {csv_path}")
    listings = []
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                listing = parse_csv_row(row)
                if listing['mls_number']:
                    listings.append(listing)
            except Exception as e:
                print(f"  Error parsing row: {e}")
                stats['errors'] += 1

    stats['total'] = len(listings)
    print(f"Parsed {len(listings)} listings")

    # Get MLS numbers for photo extraction
    mls_numbers = {l['mls_number'] for l in listings}

    # Extract photos if ZIP provided
    photos = {}
    if photos_zip and photos_zip.exists():
        print(f"Extracting photos from: {photos_zip}")
        photos = extract_photos(photos_zip, mls_numbers)
        print(f"Extracted {len(photos)} photos")

    if dry_run:
        print("\n=== DRY RUN - No database changes ===")
        print(f"Would import {len(listings)} listings")
        print(f"Would add {len(photos)} photos")

        # Show sample
        print("\nSample listings:")
        for l in listings[:5]:
            print(f"  {l['mls_number']}: {l['address']}, {l['city']} - ${l['list_price']:,}" if l['list_price'] else f"  {l['mls_number']}: {l['address']}, {l['city']}")
        return stats

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    now = datetime.now().isoformat()

    for listing in listings:
        try:
            mls_num = listing['mls_number']
            listing_id = generate_listing_id(mls_num)

            # Try to find matching parcel
            parcel = find_parcel_by_apn(conn, listing['parcel_number'])
            parcel_id = parcel['id'] if parcel else None

            if parcel:
                stats['matched_parcel'] += 1
                # Use parcel's county/zip if available
                if not listing.get('county') and parcel.get('county'):
                    listing['county'] = parcel['county']
                if not listing.get('zip') and parcel.get('zip'):
                    listing['zip'] = parcel['zip']

            # Check if listing exists
            existing = conn.execute(
                "SELECT id FROM listings WHERE mls_source = 'CSMLS' AND mls_number = ?",
                [mls_num]
            ).fetchone()

            # Get photo path
            photo_path = None
            if mls_num in photos:
                photo_path = f"/photos/{mls_num}.jpg"
                stats['photos_added'] += 1

            if existing:
                # Update existing listing
                conn.execute('''
                    UPDATE listings SET
                        parcel_id = COALESCE(?, parcel_id),
                        status = ?,
                        list_price = ?,
                        days_on_market = ?,
                        beds = ?,
                        baths = ?,
                        sqft = ?,
                        year_built = ?,
                        property_type = ?,
                        style = ?,
                        acreage = ?,
                        hoa_fee = ?,
                        listing_agent_name = ?,
                        listing_agent_phone = ?,
                        listing_office_name = ?,
                        primary_photo = COALESCE(?, primary_photo),
                        photo_source = CASE WHEN ? IS NOT NULL THEN 'mls' ELSE photo_source END,
                        photo_review_status = CASE WHEN ? IS NOT NULL THEN 'verified' ELSE photo_review_status END,
                        address = ?,
                        city = ?,
                        state = ?,
                        updated_at = ?,
                        source = 'CSMLS'
                    WHERE id = ?
                ''', [
                    parcel_id,
                    listing['status'],
                    listing['list_price'],
                    listing['days_on_market'],
                    listing['beds'],
                    listing['baths'],
                    listing['sqft'],
                    listing['year_built'],
                    listing['property_type'],
                    listing['style'],
                    listing['acreage'],
                    listing['hoa_fee'],
                    listing['listing_agent_name'],
                    listing['listing_agent_phone'],
                    listing['listing_office_name'],
                    photo_path,
                    photo_path,
                    photo_path,
                    listing['address'],
                    listing['city'],
                    listing['state'],
                    now,
                    existing['id']
                ])
                stats['updated'] += 1
            else:
                # Insert new listing
                conn.execute('''
                    INSERT INTO listings (
                        id, parcel_id, mls_source, mls_number, status,
                        list_price, days_on_market, beds, baths, sqft,
                        year_built, property_type, style, acreage, hoa_fee,
                        listing_agent_name, listing_agent_phone, listing_office_name,
                        primary_photo, photo_source, photo_review_status,
                        address, city, state, zip, county, source, captured_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', [
                    listing_id,
                    parcel_id,
                    'CSMLS',
                    mls_num,
                    listing['status'],
                    listing['list_price'],
                    listing['days_on_market'],
                    listing['beds'],
                    listing['baths'],
                    listing.get('sqft'),
                    listing.get('year_built'),
                    listing.get('property_type'),
                    listing.get('style'),
                    listing['acreage'],
                    listing['hoa_fee'],
                    listing['listing_agent_name'],
                    listing.get('listing_agent_phone'),
                    listing.get('listing_office_name'),
                    photo_path,
                    'mls' if photo_path else None,
                    'verified' if photo_path else None,
                    listing['address'],
                    listing['city'],
                    listing['state'],
                    listing.get('zip'),
                    listing.get('county'),
                    'CSMLS',
                    now,
                    now
                ])
                stats['created'] += 1

        except Exception as e:
            print(f"  Error importing {listing.get('mls_number', 'unknown')}: {e}")
            stats['errors'] += 1

    conn.commit()
    conn.close()

    return stats


def main():
    parser = argparse.ArgumentParser(description='Import MLS export to DREAMS database')
    parser.add_argument('--csv', type=Path, required=True, help='Path to MLS CSV export')
    parser.add_argument('--photos', type=Path, help='Path to photos ZIP file')
    parser.add_argument('--dry-run', action='store_true', help='Preview without database changes')

    args = parser.parse_args()

    if not args.csv.exists():
        print(f"Error: CSV file not found: {args.csv}")
        return 1

    if args.photos and not args.photos.exists():
        print(f"Warning: Photos ZIP not found: {args.photos}")
        args.photos = None

    print("=" * 60)
    print("MLS EXPORT IMPORTER")
    print("=" * 60)
    print(f"CSV: {args.csv}")
    print(f"Photos: {args.photos or 'None'}")
    print(f"Database: {DB_PATH}")
    print(f"Photos Dir: {PHOTOS_DIR}")
    print()

    stats = import_listings(args.csv, args.photos, args.dry_run)

    print()
    print("=" * 60)
    print("IMPORT COMPLETE")
    print("=" * 60)
    print(f"Total parsed:    {stats['total']}")
    print(f"Created:         {stats['created']}")
    print(f"Updated:         {stats['updated']}")
    print(f"Matched parcel:  {stats['matched_parcel']}")
    print(f"Photos added:    {stats['photos_added']}")
    print(f"Errors:          {stats['errors']}")

    return 0


if __name__ == '__main__':
    exit(main())
