#!/usr/bin/env python3
"""
NC OneMap Parcel Importer via ArcGIS REST API

Downloads parcel data directly from NC OneMap's ArcGIS FeatureServer
and enriches our parcels table with coordinates and other data.

Uses GeoPandas for efficient spatial data handling.

Usage:
    python scripts/import_onemap_api.py --county Macon
    python scripts/import_onemap_api.py --all-counties
    python scripts/import_onemap_api.py --list-counties

Examples:
    # Import single county
    python scripts/import_onemap_api.py --county Buncombe

    # Import all 11 WNC counties
    python scripts/import_onemap_api.py --all-counties
"""

import argparse
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'

# NC OneMap ArcGIS REST API endpoint
PARCELS_URL = "https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/FeatureServer/0/query"

# Our 11 WNC counties
WNC_COUNTIES = [
    'Buncombe', 'Jackson', 'Henderson', 'Haywood', 'Macon',
    'Transylvania', 'Cherokee', 'Clay', 'Madison', 'Swain', 'Graham'
]


def normalize_apn(apn: str) -> str:
    """Normalize APN for matching - remove non-alphanumeric chars."""
    if not apn:
        return ''
    return re.sub(r'[^a-zA-Z0-9]', '', str(apn)).upper()


def fetch_county_parcels(county: str, max_records: int = None) -> gpd.GeoDataFrame:
    """
    Fetch parcel data for a county from NC OneMap API.

    Returns a GeoDataFrame with parcel geometries and attributes.
    """
    print(f"  Fetching {county} County parcels from NC OneMap API...")

    # Query parameters
    params = {
        'where': f"cntyname = '{county}'",
        'outFields': 'parno,nparno,altparno,ownname,mailadd,parval,landval,gisacres,legdecfull,cntyname',
        'returnGeometry': 'true',
        'outSR': '4326',  # WGS84 lat/long
        'f': 'geojson'
    }

    all_features = []
    offset = 0
    batch_size = 5000  # API max per request

    while True:
        params['resultOffset'] = offset
        params['resultRecordCount'] = batch_size

        response = requests.get(PARCELS_URL, params=params, timeout=120)
        response.raise_for_status()

        data = response.json()
        features = data.get('features', [])

        if not features:
            break

        all_features.extend(features)
        print(f"    Fetched {len(all_features):,} records...")

        if len(features) < batch_size:
            break

        offset += batch_size

        if max_records and len(all_features) >= max_records:
            all_features = all_features[:max_records]
            break

    if not all_features:
        print(f"    No parcels found for {county}")
        return gpd.GeoDataFrame()

    # Convert to GeoDataFrame
    geojson = {
        'type': 'FeatureCollection',
        'features': all_features
    }

    gdf = gpd.GeoDataFrame.from_features(geojson, crs='EPSG:4326')
    print(f"    Total: {len(gdf):,} parcels")

    return gdf


def import_county(county: str, update_all: bool = False):
    """Import OneMap data for a single county."""

    print(f"\n{'='*60}")
    print(f"IMPORTING: {county} County")
    print('='*60)

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get our parcels for this county
    if update_all:
        query = "SELECT id, apn, address FROM parcels WHERE county = ?"
    else:
        query = "SELECT id, apn, address FROM parcels WHERE county = ? AND (latitude IS NULL OR latitude = 0)"

    our_parcels = conn.execute(query, [county]).fetchall()
    print(f"  Our parcels needing enrichment: {len(our_parcels)}")

    if not our_parcels:
        print("  No parcels to update.")
        conn.close()
        return {'matched': 0, 'updated': 0}

    # Build lookup by normalized APN
    our_apn_lookup = {}
    for p in our_parcels:
        apn = normalize_apn(p['apn'])
        if apn:
            our_apn_lookup[apn] = p['id']

    print(f"  Parcels with APN for matching: {len(our_apn_lookup)}")

    # Fetch from OneMap API
    gdf = fetch_county_parcels(county)

    if gdf.empty:
        conn.close()
        return {'matched': 0, 'updated': 0}

    # Match and update
    print(f"\n  Matching parcels...")
    matched = 0
    updated = 0

    for idx, row in gdf.iterrows():
        # Get APN from OneMap
        onemap_apn = row.get('parno') or row.get('nparno') or row.get('altparno')
        normalized_apn = normalize_apn(onemap_apn)

        if not normalized_apn:
            continue

        # Try to match
        parcel_id = our_apn_lookup.get(normalized_apn)

        if not parcel_id:
            # Try without county prefix
            if '_' in normalized_apn:
                short_apn = normalized_apn.split('_')[-1]
                parcel_id = our_apn_lookup.get(short_apn)

        if not parcel_id:
            continue

        matched += 1

        # Get coordinates from geometry centroid
        lat, lon = None, None
        if row.geometry and not row.geometry.is_empty:
            centroid = row.geometry.centroid
            lon = centroid.x
            lat = centroid.y

            # Sanity check - should be in NC
            if not (33 < lat < 37 and -85 < lon < -75):
                lat, lon = None, None

        # Build update
        updates = []
        params = []

        if lat and lon:
            updates.append("latitude = ?")
            params.append(lat)
            updates.append("longitude = ?")
            params.append(lon)

        # Owner name
        if row.get('ownname'):
            updates.append("owner_name = COALESCE(owner_name, ?)")
            params.append(str(row['ownname']).strip())

        # Mailing address
        if row.get('mailadd'):
            updates.append("mailing_address = COALESCE(mailing_address, ?)")
            params.append(str(row['mailadd']).strip())

        # Legal description
        if row.get('legdecfull'):
            updates.append("legal_description = COALESCE(legal_description, ?)")
            params.append(str(row['legdecfull']).strip())

        # Assessment values
        if row.get('parval'):
            try:
                assessed = int(float(row['parval']))
                updates.append("assessed_value = COALESCE(assessed_value, ?)")
                params.append(assessed)
            except (ValueError, TypeError):
                pass

        if row.get('landval'):
            try:
                land_val = int(float(row['landval']))
                updates.append("assessed_land_value = COALESCE(assessed_land_value, ?)")
                params.append(land_val)
            except (ValueError, TypeError):
                pass

        # Acreage
        if row.get('gisacres'):
            try:
                acres = float(row['gisacres'])
                if acres > 0:
                    updates.append("acreage = COALESCE(acreage, ?)")
                    params.append(acres)
            except (ValueError, TypeError):
                pass

        if updates:
            updates.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(parcel_id)

            sql = f"UPDATE parcels SET {', '.join(updates)} WHERE id = ?"
            conn.execute(sql, params)
            updated += 1

        # Remove from lookup to avoid duplicate processing
        if normalized_apn in our_apn_lookup:
            del our_apn_lookup[normalized_apn]

    conn.commit()
    conn.close()

    print(f"\n  Results:")
    print(f"    Matched: {matched}")
    print(f"    Updated: {updated}")

    return {'matched': matched, 'updated': updated}


def get_county_stats():
    """Get current coordinate coverage by county."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute('''
        SELECT county,
               COUNT(*) as total,
               SUM(CASE WHEN latitude IS NOT NULL AND latitude > 0 THEN 1 ELSE 0 END) as with_coords
        FROM parcels
        GROUP BY county
        ORDER BY total DESC
    ''')
    stats = cursor.fetchall()
    conn.close()
    return stats


def main():
    parser = argparse.ArgumentParser(description='Import NC OneMap parcel data via API')
    parser.add_argument('--county', help='Single county to import')
    parser.add_argument('--all-counties', action='store_true', help='Import all 11 WNC counties')
    parser.add_argument('--list-counties', action='store_true', help='List counties and current stats')
    parser.add_argument('--update-all', action='store_true', help='Update all parcels, not just missing coords')

    args = parser.parse_args()

    if args.list_counties:
        print("\nCurrent coordinate coverage by county:")
        print("-" * 50)
        stats = get_county_stats()
        for county, total, with_coords in stats:
            pct = (with_coords / total * 100) if total > 0 else 0
            marker = "✓" if pct > 90 else "○" if pct > 50 else "✗"
            print(f"  {marker} {county:15} {with_coords:5}/{total:5} ({pct:5.1f}%)")
        return

    if args.county:
        counties = [args.county]
    elif args.all_counties:
        counties = WNC_COUNTIES
    else:
        parser.print_help()
        return

    print("=" * 60)
    print("NC ONEMAP PARCEL IMPORTER (API)")
    print("=" * 60)
    print(f"Database: {DB_PATH}")
    print(f"Counties: {', '.join(counties)}")
    print()

    # Show before stats
    print("BEFORE - Coordinate coverage:")
    print("-" * 40)
    stats_before = {row[0]: (row[1], row[2]) for row in get_county_stats()}
    for county in counties:
        if county in stats_before:
            total, with_coords = stats_before[county]
            pct = (with_coords / total * 100) if total > 0 else 0
            print(f"  {county:15} {with_coords:5}/{total:5} ({pct:5.1f}%)")

    # Import each county
    total_matched = 0
    total_updated = 0

    for county in counties:
        result = import_county(county, args.update_all)
        total_matched += result['matched']
        total_updated += result['updated']

    # Show after stats
    print("\n" + "=" * 60)
    print("AFTER - Coordinate coverage:")
    print("-" * 40)
    stats_after = {row[0]: (row[1], row[2]) for row in get_county_stats()}
    for county in counties:
        if county in stats_after:
            total, with_coords = stats_after[county]
            pct = (with_coords / total * 100) if total > 0 else 0
            before_coords = stats_before.get(county, (0, 0))[1]
            added = with_coords - before_coords
            print(f"  {county:15} {with_coords:5}/{total:5} ({pct:5.1f}%) +{added}")

    print("\n" + "=" * 60)
    print("IMPORT COMPLETE")
    print("=" * 60)
    print(f"Total matched: {total_matched}")
    print(f"Total updated: {total_updated}")


if __name__ == '__main__':
    main()
