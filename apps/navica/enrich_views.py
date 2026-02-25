#!/usr/bin/env python3
"""
Enrich listings with view potential scores using USGS elevation data.

Samples 8 compass points in a 1km circle around each listing, compares
the listing's known elevation to surrounding terrain, and derives a
view_potential score (1-10).

Scoring: 60% elevation advantage + 40% directional dominance.

Usage:
    python3 -m apps.navica.enrich_views           # Enrich listings missing view data
    python3 -m apps.navica.enrich_views --all      # Re-enrich all listings
    python3 -m apps.navica.enrich_views --test     # Test with 5 listings only
"""

import argparse
import json
import math
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
REQUEST_DELAY = 0.15  # seconds between API calls
SAMPLE_RADIUS_KM = 1.0  # radius for surrounding points
NUM_DIRECTIONS = 8  # N, NE, E, SE, S, SW, W, NW

# Direction bearings in degrees (clockwise from north)
BEARINGS = [0, 45, 90, 135, 180, 225, 270, 315]


def offset_point(lat: float, lon: float, bearing_deg: float, distance_km: float) -> tuple[float, float]:
    """Calculate a new lat/lon given a starting point, bearing, and distance.

    Uses the haversine-based destination formula.
    """
    R = 6371.0  # Earth radius in km
    d = distance_km / R

    lat_r = math.radians(lat)
    lon_r = math.radians(lon)
    brg_r = math.radians(bearing_deg)

    new_lat = math.asin(
        math.sin(lat_r) * math.cos(d) + math.cos(lat_r) * math.sin(d) * math.cos(brg_r)
    )
    new_lon = lon_r + math.atan2(
        math.sin(brg_r) * math.sin(d) * math.cos(lat_r),
        math.cos(d) - math.sin(lat_r) * math.sin(new_lat),
    )

    return (math.degrees(new_lat), math.degrees(new_lon))


def get_elevation(lat: float, lon: float) -> float | None:
    """Query USGS EPQS for elevation in feet at a given lat/lon."""
    url = f"{USGS_EPQS_URL}?x={lon}&y={lat}&units=Feet&wkid=4326&includeDate=false"
    req = urllib.request.Request(url, headers={"User-Agent": "myDREAMS/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            value = data.get("value")
            if value is not None and value != -1000000:
                return float(value)
            return None
    except (urllib.error.URLError, json.JSONDecodeError, ValueError, KeyError):
        return None


def calculate_view_potential(listing_elev: float, surrounding_elevs: list[float | None]) -> int:
    """Calculate view potential score (1-10) from listing elevation vs surrounding terrain.

    Scoring formula:
    - Elevation advantage (60% weight): how far above average surrounding terrain
    - Directional dominance (40% weight): proportion of 8 directions where listing is higher

    Returns integer 1-10.
    """
    valid_elevs = [e for e in surrounding_elevs if e is not None]

    if not valid_elevs:
        return 1

    avg_surrounding = sum(valid_elevs) / len(valid_elevs)
    advantage_ft = listing_elev - avg_surrounding

    # Elevation advantage score (0-10)
    # -100ft or below = 0, 0ft = 3, +100ft = 6, +300ft = 9, +500ft+ = 10
    if advantage_ft <= -100:
        adv_score = 0
    elif advantage_ft <= 0:
        adv_score = 3.0 * (1 + advantage_ft / 100)
    elif advantage_ft <= 100:
        adv_score = 3.0 + 3.0 * (advantage_ft / 100)
    elif advantage_ft <= 300:
        adv_score = 6.0 + 3.0 * ((advantage_ft - 100) / 200)
    else:
        adv_score = min(10, 9.0 + (advantage_ft - 300) / 200)

    # Directional dominance score (0-10)
    dirs_higher = sum(1 for e in valid_elevs if listing_elev > e)
    dir_score = (dirs_higher / len(valid_elevs)) * 10

    # Weighted blend: 60% advantage + 40% directional
    raw = adv_score * 0.6 + dir_score * 0.4

    # Clamp to 1-10 integer
    return max(1, min(10, round(raw)))


def enrich_listing_view(lat: float, lon: float, listing_elev: float) -> int | None:
    """Sample 8 surrounding points and calculate view potential for one listing.

    Returns view_potential score (1-10) or None on failure.
    """
    surrounding = []

    for bearing in BEARINGS:
        pt_lat, pt_lon = offset_point(lat, lon, bearing, SAMPLE_RADIUS_KM)
        elev = get_elevation(pt_lat, pt_lon)
        surrounding.append(elev)
        time.sleep(REQUEST_DELAY)

    # Need at least 4 valid samples for a meaningful score
    valid_count = sum(1 for e in surrounding if e is not None)
    if valid_count < 4:
        return None

    return calculate_view_potential(listing_elev, surrounding)


def enrich_listings(all_listings: bool = False, test_mode: bool = False):
    """Fetch view potential for listings that have elevation but no view score."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    if all_listings:
        query = """
            SELECT id, latitude, longitude, elevation_feet, address, city
            FROM listings
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
                  AND latitude != 0 AND longitude != 0
                  AND elevation_feet IS NOT NULL AND elevation_feet > 0
        """
    else:
        query = """
            SELECT id, latitude, longitude, elevation_feet, address, city
            FROM listings
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
                  AND latitude != 0 AND longitude != 0
                  AND elevation_feet IS NOT NULL AND elevation_feet > 0
                  AND view_potential IS NULL
        """

    rows = conn.execute(query).fetchall()

    if test_mode:
        rows = rows[:5]

    total = len(rows)
    print(f"Found {total} listings to enrich with view potential data")

    if total == 0:
        conn.close()
        return

    success = 0
    errors = 0

    for i, row in enumerate(rows, 1):
        lat, lon = row["latitude"], row["longitude"]
        elev = row["elevation_feet"]
        label = f"{row['address'] or 'Unknown'}, {row['city'] or ''}"

        score = enrich_listing_view(lat, lon, float(elev))

        if score is not None:
            conn.execute(
                "UPDATE listings SET view_potential = ? WHERE id = ?",
                (score, row["id"]),
            )
            success += 1
            print(f"  [{i}/{total}] {label}: elev={elev}ft, view={score}/10")
        else:
            errors += 1
            print(f"  [{i}/{total}] {label}: FAILED (not enough surrounding data)")

        # Commit every 50 records
        if i % 50 == 0:
            conn.commit()

    conn.commit()
    conn.close()

    print(f"\nDone: {success} enriched, {errors} failed out of {total}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich listings with view potential scores")
    parser.add_argument("--all", action="store_true", help="Re-enrich all listings")
    parser.add_argument("--test", action="store_true", help="Test with 5 listings only")
    args = parser.parse_args()

    enrich_listings(all_listings=args.all, test_mode=args.test)
