#!/usr/bin/env python3
"""
Enrich listings with flood zone data from FEMA National Flood Hazard Layer (NFHL).

Queries the FEMA ArcGIS REST service to determine flood zone designation for each
listing, then derives a flood_factor score (1-10) from the zone code.

Usage:
    python3 -m apps.navica.enrich_flood           # Enrich listings missing flood data
    python3 -m apps.navica.enrich_flood --all      # Re-enrich all listings
    python3 -m apps.navica.enrich_flood --test     # Test with 5 listings only
"""

import argparse
import json
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# Resolve project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "dreams.db"

FEMA_NFHL_URL = (
    "https://hazards.fema.gov/arcgis/rest/services/public/NFHLWMS/MapServer/28/query"
)
REQUEST_DELAY = 0.3  # seconds between requests (polite rate limiting)

# Flood factor derivation from FEMA zone codes
# Higher = more flood risk
FLOOD_FACTOR_MAP = {
    # High-risk zones (100-year floodplain, Special Flood Hazard Area)
    "A": 8,
    "AE": 8,
    "AH": 8,
    "AO": 8,
    "AR": 8,
    "V": 8,
    "VE": 8,
    # Future conditions / levee zones
    "A99": 6,
    # Moderate risk (500-year floodplain)
    "B": 4,
    # Minimal risk
    "C": 1,
    "X": 1,  # default for X; subtypes handled separately
    # Undetermined
    "D": 1,
}


def derive_flood_factor(zone: str, subtype: str | None) -> int:
    """Derive a 1-10 flood factor score from FEMA zone code and subtype."""
    if not zone:
        return 1

    zone_upper = zone.strip().upper()

    # Floodway designation is the highest risk
    if subtype and "FLOODWAY" in subtype.upper():
        return 10

    # X zone with 500-year subtype
    if zone_upper == "X" and subtype:
        sub_upper = subtype.upper()
        if "0.2" in sub_upper or "500" in sub_upper:
            return 4

    return FLOOD_FACTOR_MAP.get(zone_upper, 1)


def get_flood_zone(lat: float, lon: float) -> tuple[str | None, str | None]:
    """Query FEMA NFHL for flood zone at a given lat/lon.

    Returns (flood_zone, zone_subtype) or (None, None) on failure.
    """
    params = (
        f"?geometry={lon},{lat}"
        "&geometryType=esriGeometryPoint"
        "&inSR=4326"
        "&spatialRel=esriSpatialRelIntersects"
        "&outFields=FLD_ZONE,ZONE_SUBTY,SFHA_TF"
        "&returnGeometry=false"
        "&f=json"
    )
    url = FEMA_NFHL_URL + params
    req = urllib.request.Request(url, headers={"User-Agent": "myDREAMS/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        features = data.get("features", [])
        if not features:
            # No flood zone data at this point (likely outside mapped area)
            return ("X", None)

        attrs = features[0].get("attributes", {})
        fld_zone = attrs.get("FLD_ZONE")
        zone_subty = attrs.get("ZONE_SUBTY")

        return (fld_zone, zone_subty)

    except (urllib.error.URLError, json.JSONDecodeError, ValueError, KeyError) as e:
        print(f"  Error for ({lat}, {lon}): {e}")
        return (None, None)


def enrich_listings(all_listings: bool = False, test_mode: bool = False):
    """Fetch flood zone for listings that have coordinates but no flood data."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.row_factory = sqlite3.Row

    if all_listings:
        query = """
            SELECT id, latitude, longitude, address, city
            FROM listings
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
                  AND latitude != 0 AND longitude != 0
        """
    else:
        query = """
            SELECT id, latitude, longitude, address, city
            FROM listings
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
                  AND latitude != 0 AND longitude != 0
                  AND flood_zone IS NULL
        """

    rows = conn.execute(query).fetchall()

    if test_mode:
        rows = rows[:5]

    total = len(rows)
    print(f"Found {total} listings to enrich with flood zone data")

    if total == 0:
        conn.close()
        return

    success = 0
    errors = 0

    for i, row in enumerate(rows, 1):
        lat, lon = row["latitude"], row["longitude"]
        label = f"{row['address'] or 'Unknown'}, {row['city'] or ''}"

        fld_zone, zone_subty = get_flood_zone(lat, lon)

        if fld_zone is not None:
            factor = derive_flood_factor(fld_zone, zone_subty)
            conn.execute(
                "UPDATE listings SET flood_zone = ?, flood_factor = ? WHERE id = ?",
                (fld_zone, factor, row["id"]),
            )
            success += 1
            subtype_str = f" ({zone_subty})" if zone_subty else ""
            print(f"  [{i}/{total}] {label}: Zone {fld_zone}{subtype_str}, factor={factor}")
        else:
            errors += 1
            print(f"  [{i}/{total}] {label}: FAILED")

        # Commit every 50 records
        if i % 50 == 0:
            conn.commit()

        # Rate limiting
        if i < total:
            time.sleep(REQUEST_DELAY)

    conn.commit()
    conn.close()

    print(f"\nDone: {success} enriched, {errors} failed out of {total}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich listings with FEMA flood zone data")
    parser.add_argument("--all", action="store_true", help="Re-enrich all listings")
    parser.add_argument("--test", action="store_true", help="Test with 5 listings only")
    args = parser.parse_args()

    enrich_listings(all_listings=args.all, test_mode=args.test)
