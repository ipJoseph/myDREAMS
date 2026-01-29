#!/usr/bin/env python3
"""
NC OneMap Parcel Data Importer

Imports parcel data from NC OneMap shapefiles to enrich our parcels table with:
- Accurate coordinates (lat/long)
- Owner information
- Assessment values
- Legal descriptions

Matches parcels by APN (parcel number).

Usage:
    python scripts/import_onemap_parcels.py <shapefile_path> [--county COUNTY] [--update-all]

Examples:
    python scripts/import_onemap_parcels.py /path/to/nc_macon_parcels_pt.shp
    python scripts/import_onemap_parcels.py /path/to/nc_macon_parcels_pt.shp --county Macon
"""

import argparse
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import shapefile
from pyproj import Transformer

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'

# NC State Plane (feet) to WGS84 (lat/long) transformer
# EPSG:2264 = NAD83 / North Carolina (ftUS)
# EPSG:4326 = WGS84
transformer = Transformer.from_crs("EPSG:2264", "EPSG:4326", always_xy=True)


def normalize_apn(apn: str) -> str:
    """Normalize APN for matching - remove non-alphanumeric chars."""
    if not apn:
        return ''
    return re.sub(r'[^a-zA-Z0-9]', '', str(apn)).upper()


def convert_coords(x: float, y: float) -> tuple:
    """Convert NC State Plane coordinates to lat/long."""
    try:
        lon, lat = transformer.transform(x, y)
        # Sanity check - should be in NC
        if 33 < lat < 37 and -85 < lon < -75:
            return (lat, lon)
    except Exception:
        pass
    return (None, None)


def import_onemap(shapefile_path: str, county: str = None, update_all: bool = False):
    """Import OneMap parcel data and match to existing parcels."""

    print("=" * 60)
    print("NC ONEMAP PARCEL IMPORTER")
    print("=" * 60)
    print(f"Shapefile: {shapefile_path}")
    print(f"Database: {DB_PATH}")
    print()

    # Read shapefile
    print("Loading shapefile...")
    sf = shapefile.Reader(shapefile_path)
    fields = [f[0] for f in sf.fields[1:]]  # Skip DeletionFlag

    total_records = len(sf)
    print(f"Total records in shapefile: {total_records:,}")

    # Detect county from data if not specified
    if not county:
        for rec in sf.records():
            values = dict(zip(fields, rec))
            if values.get('CNTYNAME'):
                county = values['CNTYNAME'].strip().title()
                break

    if county:
        print(f"County: {county}")

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get our parcels for this county that need coordinates
    if update_all:
        query = "SELECT id, apn, address FROM parcels WHERE county = ?"
    else:
        query = "SELECT id, apn, address FROM parcels WHERE county = ? AND (latitude IS NULL OR latitude = 0)"

    our_parcels = conn.execute(query, [county]).fetchall()
    print(f"Our parcels in {county}: {len(our_parcels)}")

    if not our_parcels:
        print("No parcels to update.")
        conn.close()
        return

    # Build lookup by normalized APN
    our_apn_lookup = {}
    for p in our_parcels:
        apn = normalize_apn(p['apn'])
        if apn:
            our_apn_lookup[apn] = p['id']

    print(f"Parcels with APN for matching: {len(our_apn_lookup)}")

    # Process shapefile records
    print("\nMatching parcels...")
    matched = 0
    updated_coords = 0
    updated_other = 0
    not_matched = 0

    for i, shaperec in enumerate(sf.iterShapeRecords()):
        rec = shaperec.record
        shape = shaperec.shape

        values = dict(zip(fields, rec))

        # Get APN from OneMap
        onemap_apn = values.get('PARNO') or values.get('NPARNO') or values.get('ALTPARNO')
        normalized_apn = normalize_apn(onemap_apn)

        if not normalized_apn:
            continue

        # Try to match
        parcel_id = our_apn_lookup.get(normalized_apn)

        if not parcel_id:
            # Try without county prefix (some APNs have 37113_ prefix)
            if '_' in normalized_apn:
                short_apn = normalized_apn.split('_')[-1]
                parcel_id = our_apn_lookup.get(short_apn)

        if not parcel_id:
            not_matched += 1
            continue

        matched += 1

        # Get coordinates
        lat, lon = None, None
        if shape.points:
            x, y = shape.points[0]
            lat, lon = convert_coords(x, y)

        # Build update
        updates = []
        params = []

        if lat and lon:
            updates.append("latitude = ?")
            params.append(lat)
            updates.append("longitude = ?")
            params.append(lon)
            updated_coords += 1

        # Optional: update other fields if missing
        # Owner name
        if values.get('OWNNAME'):
            updates.append("owner_name = COALESCE(owner_name, ?)")
            params.append(values['OWNNAME'].strip())

        # Mailing address
        if values.get('MAILADD'):
            updates.append("mailing_address = COALESCE(mailing_address, ?)")
            params.append(values['MAILADD'].strip())

        # Legal description
        if values.get('LEGDECFULL'):
            updates.append("legal_description = COALESCE(legal_description, ?)")
            params.append(values['LEGDECFULL'].strip())

        # Assessment values
        if values.get('PARVAL'):
            try:
                assessed = int(float(values['PARVAL']))
                updates.append("assessed_value = COALESCE(assessed_value, ?)")
                params.append(assessed)
            except:
                pass

        if values.get('LANDVAL'):
            try:
                land_val = int(float(values['LANDVAL']))
                updates.append("assessed_land_value = COALESCE(assessed_land_value, ?)")
                params.append(land_val)
            except:
                pass

        # Acreage
        if values.get('GISACRES'):
            try:
                acres = float(values['GISACRES'])
                if acres > 0:
                    updates.append("acreage = COALESCE(acreage, ?)")
                    params.append(acres)
            except:
                pass

        if updates:
            updates.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(parcel_id)

            sql = f"UPDATE parcels SET {', '.join(updates)} WHERE id = ?"
            conn.execute(sql, params)
            updated_other += 1

        # Progress
        if (i + 1) % 5000 == 0:
            print(f"  Processed {i + 1:,}/{total_records:,} - Matched: {matched:,}")
            conn.commit()

    conn.commit()
    conn.close()

    print()
    print("=" * 60)
    print("IMPORT COMPLETE")
    print("=" * 60)
    print(f"OneMap records processed: {total_records:,}")
    print(f"Matched to our parcels: {matched:,}")
    print(f"Updated with coordinates: {updated_coords:,}")
    print(f"Updated with other data: {updated_other:,}")
    print(f"Not matched: {not_matched:,}")


def main():
    parser = argparse.ArgumentParser(description='Import NC OneMap parcel data')
    parser.add_argument('shapefile', help='Path to shapefile (.shp)')
    parser.add_argument('--county', help='County name (auto-detected if not specified)')
    parser.add_argument('--update-all', action='store_true',
                       help='Update all parcels, not just those missing coordinates')

    args = parser.parse_args()

    shapefile_path = args.shapefile
    if not Path(shapefile_path).exists():
        print(f"File not found: {shapefile_path}")
        return

    import_onemap(shapefile_path, args.county, args.update_all)


if __name__ == '__main__':
    main()
