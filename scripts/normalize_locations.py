#!/usr/bin/env python3
"""
One-time migration: normalize county and city names in the listings table.

Fixes state-suffixed counties (e.g., CherokeeNC -> Cherokee) and
variant city names (e.g., "Canton, Nc" -> "Canton").

Safe to run multiple times (idempotent).
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / 'data' / 'dreams.db'

# County normalization map
COUNTY_FIXES = {
    'BeaufortNC': 'Beaufort',
    'BeaufortSC': 'Beaufort',
    'CherokeeNC': 'Cherokee',
    'CherokeeSC': 'Cherokee',
    'ChathamNC': 'Chatham',
    'UnionSC': 'Union',
    'Rabun County Ga': 'Rabun',
}

# City normalization map
CITY_FIXES = {
    'Canton, Nc': 'Canton',
    'Cherokee (Jackson Co.)': 'Cherokee',
    'Clayton, Ga': 'Clayton',
    'Franklin City Limits': 'Franklin',
    'Mt Croghan': 'Mount Croghan',
    'Mt Ulla': 'Mount Ulla',
    'Robbinsville (Graham)': 'Robbinsville',
}


def main():
    dry_run = '--dry-run' in sys.argv

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA busy_timeout = 5000")

    total_county = 0
    total_city = 0
    total_mt = 0

    # Fix known county variants
    for old, new in COUNTY_FIXES.items():
        cursor = conn.execute(
            "SELECT COUNT(*) FROM listings WHERE county = ?", [old]
        )
        count = cursor.fetchone()[0]
        if count > 0:
            print(f"  County: '{old}' -> '{new}' ({count} rows)")
            if not dry_run:
                conn.execute(
                    "UPDATE listings SET county = ? WHERE county = ?",
                    [new, old]
                )
            total_county += count

    # Fix known city variants
    for old, new in CITY_FIXES.items():
        cursor = conn.execute(
            "SELECT COUNT(*) FROM listings WHERE city = ?", [old]
        )
        count = cursor.fetchone()[0]
        if count > 0:
            print(f"  City: '{old}' -> '{new}' ({count} rows)")
            if not dry_run:
                conn.execute(
                    "UPDATE listings SET city = ? WHERE city = ?",
                    [new, old]
                )
            total_city += count

    # Fix "Mt " -> "Mount " prefix for all cities
    cursor = conn.execute(
        "SELECT DISTINCT city FROM listings WHERE city LIKE 'Mt %'"
    )
    mt_cities = [row[0] for row in cursor.fetchall()]
    for old_city in mt_cities:
        if old_city in CITY_FIXES:
            continue  # Already handled above
        new_city = 'Mount ' + old_city[3:]
        cursor = conn.execute(
            "SELECT COUNT(*) FROM listings WHERE city = ?", [old_city]
        )
        count = cursor.fetchone()[0]
        if count > 0:
            print(f"  City: '{old_city}' -> '{new_city}' ({count} rows)")
            if not dry_run:
                conn.execute(
                    "UPDATE listings SET city = ? WHERE city = ?",
                    [new_city, old_city]
                )
            total_mt += count

    if not dry_run:
        conn.commit()

    conn.close()

    mode = "DRY RUN" if dry_run else "APPLIED"
    print(f"\n{mode}: {total_county} county rows, {total_city + total_mt} city rows normalized")


if __name__ == '__main__':
    main()
