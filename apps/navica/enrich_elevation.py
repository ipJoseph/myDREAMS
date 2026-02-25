#!/usr/bin/env python3
"""
Enrich listings with elevation data from the USGS Elevation Point Query Service (EPQS).

Usage:
    python3 -m apps.navica.enrich_elevation           # Enrich listings missing elevation
    python3 -m apps.navica.enrich_elevation --all      # Re-enrich all listings
    python3 -m apps.navica.enrich_elevation --test     # Test with 5 listings only
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

USGS_EPQS_URL = "https://epqs.nationalmap.gov/v1/json"
REQUEST_DELAY = 0.15  # seconds between requests (polite rate limiting)


def get_elevation(lat: float, lon: float) -> int | None:
    """Query USGS EPQS for elevation in feet at a given lat/lon."""
    url = f"{USGS_EPQS_URL}?x={lon}&y={lat}&units=Feet&wkid=4326&includeDate=false"
    req = urllib.request.Request(url, headers={"User-Agent": "myDREAMS/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            value = data.get("value")
            if value is not None and value != -1000000:
                return round(float(value))
            return None
    except (urllib.error.URLError, json.JSONDecodeError, ValueError, KeyError) as e:
        print(f"  Error for ({lat}, {lon}): {e}")
        return None


def enrich_listings(all_listings: bool = False, test_mode: bool = False):
    """Fetch elevation for listings that have coordinates but no elevation."""
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
                  AND (elevation_feet IS NULL OR elevation_feet = 0)
        """

    rows = conn.execute(query).fetchall()

    if test_mode:
        rows = rows[:5]

    total = len(rows)
    print(f"Found {total} listings to enrich with elevation data")

    if total == 0:
        conn.close()
        return

    success = 0
    errors = 0

    for i, row in enumerate(rows, 1):
        lat, lon = row["latitude"], row["longitude"]
        label = f"{row['address'] or 'Unknown'}, {row['city'] or ''}"

        elevation = get_elevation(lat, lon)

        if elevation is not None:
            conn.execute(
                "UPDATE listings SET elevation_feet = ? WHERE id = ?",
                (elevation, row["id"]),
            )
            success += 1
            print(f"  [{i}/{total}] {label}: {elevation:,} ft")
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
    parser = argparse.ArgumentParser(description="Enrich listings with USGS elevation data")
    parser.add_argument("--all", action="store_true", help="Re-enrich all listings")
    parser.add_argument("--test", action="store_true", help="Test with 5 listings only")
    args = parser.parse_args()

    enrich_listings(all_listings=args.all, test_mode=args.test)
