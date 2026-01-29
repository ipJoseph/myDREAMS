#!/usr/bin/env python3
"""
Parcel Geocoder

Adds latitude/longitude coordinates to parcels using the US Census Bureau Geocoder.
Free, no API key required, works well for US addresses.

Usage:
    python scripts/geocode_parcels.py [--limit N] [--batch-size N]

Options:
    --limit N       Max parcels to geocode (default: all)
    --batch-size N  Batch size for Census API (default: 100, max: 10000)
    --dry-run       Show what would be geocoded without making changes
"""

import argparse
import csv
import io
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'

# Census Bureau Geocoder endpoints
CENSUS_SINGLE_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
CENSUS_BATCH_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"


def geocode_single(address: str, city: str, state: str, zip_code: str) -> tuple:
    """
    Geocode a single address using Census Bureau API.
    Returns (lat, lon) or (None, None) if not found.
    """
    # Build full address
    full_address = f"{address}, {city}, {state}"
    if zip_code:
        full_address += f" {zip_code}"

    try:
        params = {
            'address': full_address,
            'benchmark': 'Public_AR_Current',
            'format': 'json'
        }

        resp = requests.get(CENSUS_SINGLE_URL, params=params, timeout=10)

        if resp.ok:
            data = resp.json()
            matches = data.get('result', {}).get('addressMatches', [])

            if matches:
                coords = matches[0].get('coordinates', {})
                lat = coords.get('y')
                lon = coords.get('x')
                return (lat, lon)

    except Exception as e:
        pass

    return (None, None)


def geocode_batch(parcels: list) -> dict:
    """
    Geocode a batch of addresses using Census Bureau batch API.

    Args:
        parcels: List of dicts with 'id', 'address', 'city', 'state', 'zip'

    Returns:
        Dict mapping parcel_id to (lat, lon) tuple
    """
    results = {}

    # Build CSV for batch upload
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)

    for p in parcels:
        # Format: Unique ID, Street Address, City, State, ZIP
        writer.writerow([
            p['id'],
            p['address'] or '',
            p['city'] or '',
            p['state'] or 'NC',
            p['zip'] or ''
        ])

    csv_content = csv_buffer.getvalue()

    try:
        files = {
            'addressFile': ('addresses.csv', csv_content, 'text/csv')
        }
        data = {
            'benchmark': 'Public_AR_Current'
        }

        resp = requests.post(CENSUS_BATCH_URL, files=files, data=data, timeout=120)

        if resp.ok:
            # Parse CSV response
            # Format: ID, Input Address, Match Status, Match Type, Matched Address, "lon,lat", Tiger ID, Side
            reader = csv.reader(io.StringIO(resp.text))

            for row in reader:
                if len(row) >= 6:
                    parcel_id = row[0].strip('"')
                    match_status = row[2].strip('"') if len(row) > 2 else ''

                    if match_status == 'Match':
                        try:
                            # Coordinates in column 5 as "lon,lat"
                            coords = row[5].strip('"')
                            if ',' in coords:
                                lon_str, lat_str = coords.split(',')
                                lon = float(lon_str)
                                lat = float(lat_str)
                                results[parcel_id] = (lat, lon)
                        except (ValueError, IndexError) as e:
                            pass

    except Exception as e:
        print(f"  Batch geocode error: {e}")

    return results


def main():
    parser = argparse.ArgumentParser(description='Geocode parcels without coordinates')
    parser.add_argument('--limit', type=int, default=0, help='Max parcels to geocode (0=all)')
    parser.add_argument('--batch-size', type=int, default=100, help='Batch size (max 10000)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done')
    parser.add_argument('--single', action='store_true', help='Use single-address API (slower but more reliable)')

    args = parser.parse_args()

    print("=" * 60)
    print("PARCEL GEOCODER")
    print("=" * 60)
    print(f"Database: {DB_PATH}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"Method: {'Single address' if args.single else f'Batch (size={args.batch_size})'}")
    print()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get parcels needing geocoding
    query = """
        SELECT id, address, city, state, zip, county
        FROM parcels
        WHERE latitude IS NULL
        AND address IS NOT NULL
        AND address != ''
    """
    if args.limit:
        query += f" LIMIT {args.limit}"

    cursor = conn.execute(query)
    parcels = [dict(row) for row in cursor.fetchall()]

    print(f"Parcels needing geocoding: {len(parcels)}")

    if args.dry_run:
        print("\nSample addresses to geocode:")
        for p in parcels[:5]:
            print(f"  {p['address']}, {p['city']}, {p['state']} {p['zip']}")
        conn.close()
        return

    if not parcels:
        print("No parcels need geocoding.")
        conn.close()
        return

    geocoded = 0
    failed = 0

    if args.single:
        # Single address mode - slower but more reliable
        print("\nGeocoding (single address mode)...")

        for i, p in enumerate(parcels):
            lat, lon = geocode_single(p['address'], p['city'], p['state'], p['zip'])

            if lat and lon:
                conn.execute(
                    "UPDATE parcels SET latitude = ?, longitude = ?, updated_at = ? WHERE id = ?",
                    (lat, lon, datetime.now().isoformat(), p['id'])
                )
                geocoded += 1
            else:
                failed += 1

            if (i + 1) % 50 == 0:
                print(f"  Processed {i + 1}/{len(parcels)} - {geocoded} geocoded, {failed} failed")
                conn.commit()

            # Rate limiting - Census API allows ~1000/hour for single requests
            time.sleep(0.5)

        conn.commit()

    else:
        # Batch mode - faster
        print("\nGeocoding (batch mode)...")

        batch_size = min(args.batch_size, 10000)

        for i in range(0, len(parcels), batch_size):
            batch = parcels[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(parcels) + batch_size - 1) // batch_size

            print(f"  Batch {batch_num}/{total_batches} ({len(batch)} addresses)...")

            results = geocode_batch(batch)

            for parcel_id, (lat, lon) in results.items():
                conn.execute(
                    "UPDATE parcels SET latitude = ?, longitude = ?, updated_at = ? WHERE id = ?",
                    (lat, lon, datetime.now().isoformat(), parcel_id)
                )
                geocoded += 1

            failed += len(batch) - len(results)

            conn.commit()

            # Small delay between batches
            if i + batch_size < len(parcels):
                time.sleep(2)

    conn.close()

    print()
    print("=" * 60)
    print("GEOCODING COMPLETE")
    print("=" * 60)
    print(f"Successfully geocoded: {geocoded}")
    print(f"Failed to geocode: {failed}")
    print(f"Success rate: {geocoded / len(parcels) * 100:.1f}%")


if __name__ == '__main__':
    main()
