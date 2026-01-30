#!/usr/bin/env python3
"""
Spatial Data Enrichment Script

Enriches properties with NC OneMap spatial data:
- Flood zones (FEMA flood hazard areas)
- Elevation and terrain (slope, aspect, view potential)
- Wildfire risk

Usage:
    python scripts/enrich_spatial.py                    # Enrich properties missing spatial data
    python scripts/enrich_spatial.py --limit 100        # Limit to 100 properties
    python scripts/enrich_spatial.py --force            # Re-enrich all properties
    python scripts/enrich_spatial.py --county Buncombe  # Single county
    python scripts/enrich_spatial.py --property-id X    # Single property
    python scripts/enrich_spatial.py --dry-run          # Show what would be enriched
"""

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.services.spatial_data_service import SpatialDataService

DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'


def get_properties_to_enrich(
    conn,
    limit: int = 0,
    force: bool = False,
    county: str = None,
    property_id: str = None
) -> list:
    """Get list of properties needing spatial enrichment."""

    conditions = ["latitude IS NOT NULL", "longitude IS NOT NULL"]
    params = []

    if not force:
        conditions.append("spatial_enriched_at IS NULL")

    if county:
        conditions.append("county = ?")
        params.append(county)

    if property_id:
        conditions.append("id = ?")
        params.append(property_id)

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT id, address, city, county, latitude, longitude,
               flood_zone, elevation_feet, spatial_enriched_at
        FROM properties
        WHERE {where_clause}
        ORDER BY updated_at DESC
    """

    if limit > 0:
        query += f" LIMIT {limit}"

    cursor = conn.execute(query, params)
    return [dict(row) for row in cursor.fetchall()]


def enrich_property(service: SpatialDataService, prop: dict) -> dict:
    """
    Enrich a single property with spatial data.

    Returns dict of fields to update.
    """
    lat = prop['latitude']
    lon = prop['longitude']

    updates = {}

    # Query flood zone
    try:
        flood = service.query_flood_zone(lat, lon)
        if flood:
            updates['flood_zone'] = flood.zone
            updates['flood_zone_subtype'] = flood.zone_subtype
            updates['flood_factor'] = flood.flood_factor
            updates['flood_sfha'] = 1 if flood.sfha else 0
    except Exception as e:
        print(f"    Flood zone error: {e}")

    # Query elevation
    try:
        elevation = service.query_elevation(lat, lon)
        if elevation:
            updates['elevation_feet'] = elevation.elevation_feet

            # Get slope and aspect
            slope, aspect = service.query_slope_aspect(lat, lon)
            if slope is not None:
                updates['slope_percent'] = round(slope, 1)
            if aspect:
                updates['aspect'] = aspect

            # Calculate view potential
            view_score = service.calculate_view_potential(lat, lon, elevation.elevation_feet)
            updates['view_potential'] = view_score
    except Exception as e:
        print(f"    Elevation error: {e}")

    # Query wildfire risk
    try:
        wildfire_risk = service.query_wildfire_risk(lat, lon)
        if wildfire_risk:
            updates['wildfire_risk'] = wildfire_risk
            # Calculate wildfire score
            from src.services.spatial_data_service import EnvironmentResult
            updates['wildfire_score'] = EnvironmentResult._wildfire_score(wildfire_risk)
    except Exception as e:
        print(f"    Wildfire error: {e}")

    if updates:
        updates['spatial_enriched_at'] = datetime.now().isoformat()

    return updates


def update_property(conn, property_id: str, updates: dict):
    """Update property with spatial data."""
    if not updates:
        return

    set_clauses = [f"{k} = ?" for k in updates.keys()]
    values = list(updates.values())
    values.append(property_id)

    query = f"""
        UPDATE properties
        SET {', '.join(set_clauses)}
        WHERE id = ?
    """

    conn.execute(query, values)


def main():
    parser = argparse.ArgumentParser(description='Enrich properties with NC OneMap spatial data')
    parser.add_argument('--limit', type=int, default=0, help='Max properties to enrich (0=all)')
    parser.add_argument('--force', action='store_true', help='Re-enrich all properties')
    parser.add_argument('--county', help='Filter to single county')
    parser.add_argument('--property-id', help='Enrich single property by ID')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be enriched')
    parser.add_argument('--delay', type=float, default=0.5, help='Delay between API calls (seconds)')

    args = parser.parse_args()

    print("=" * 60)
    print("SPATIAL DATA ENRICHMENT")
    print("=" * 60)
    print(f"Database: {DB_PATH}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    if args.county:
        print(f"County filter: {args.county}")
    if args.property_id:
        print(f"Property ID: {args.property_id}")
    print()

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get properties to enrich
    properties = get_properties_to_enrich(
        conn,
        limit=args.limit,
        force=args.force,
        county=args.county,
        property_id=args.property_id
    )

    print(f"Properties to enrich: {len(properties)}")

    if not properties:
        print("No properties need enrichment.")
        conn.close()
        return

    if args.dry_run:
        print("\nSample properties:")
        for p in properties[:5]:
            print(f"  {p['address']}, {p['city']} ({p['latitude']:.4f}, {p['longitude']:.4f})")
            if p['flood_zone']:
                print(f"    Current: Flood={p['flood_zone']}, Elev={p['elevation_feet']}")
        conn.close()
        return

    # Initialize service
    service = SpatialDataService(rate_limit_delay=args.delay)

    # Process properties
    print("\nEnriching properties...")
    print("-" * 40)

    enriched = 0
    failed = 0

    for i, prop in enumerate(properties):
        addr = prop['address'] or 'Unknown'
        city = prop['city'] or ''

        print(f"[{i+1}/{len(properties)}] {addr}, {city}")

        try:
            updates = enrich_property(service, prop)

            if updates:
                update_property(conn, prop['id'], updates)
                enriched += 1

                # Show what was found
                parts = []
                if 'flood_zone' in updates:
                    parts.append(f"Flood={updates['flood_zone']}")
                if 'elevation_feet' in updates:
                    parts.append(f"Elev={updates['elevation_feet']}ft")
                if 'view_potential' in updates:
                    parts.append(f"View={updates['view_potential']}/10")
                if 'wildfire_risk' in updates:
                    parts.append(f"Fire={updates['wildfire_risk']}")

                print(f"    {', '.join(parts)}")
            else:
                print("    No data available")
                failed += 1

        except Exception as e:
            print(f"    ERROR: {e}")
            failed += 1

        # Commit every 10 properties
        if (i + 1) % 10 == 0:
            conn.commit()
            print(f"    [Committed {i+1} properties]")

    # Final commit
    conn.commit()
    conn.close()

    # Summary
    print()
    print("=" * 60)
    print("ENRICHMENT COMPLETE")
    print("=" * 60)
    print(f"Successfully enriched: {enriched}")
    print(f"Failed/no data: {failed}")
    print(f"Success rate: {enriched / len(properties) * 100:.1f}%")


if __name__ == '__main__':
    main()
