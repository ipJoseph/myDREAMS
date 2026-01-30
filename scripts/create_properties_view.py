#!/usr/bin/env python3
"""
Create a 'properties_v2' view that maps listings to the old properties schema.

This provides backwards compatibility for dashboard queries while we transition
to the new normalized schema (parcels + listings).

Run with: python scripts/create_properties_view.py
"""

import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'


def create_view(conn: sqlite3.Connection):
    """Create the properties_v2 view."""

    # Drop existing view if any
    conn.execute("DROP VIEW IF EXISTS properties_v2")

    # Create view that maps listings (joined with parcels) to properties schema
    conn.execute("""
        CREATE VIEW properties_v2 AS
        SELECT
            -- Identity (from listings)
            l.id,
            l.mls_number,
            l.mls_source,
            l.parcel_id,
            l.zillow_id,
            l.redfin_id,
            NULL as realtor_id,

            -- Address (denormalized on listings, fallback to parcels)
            COALESCE(l.address, p.address) as address,
            COALESCE(l.city, p.city) as city,
            COALESCE(l.state, p.state, 'NC') as state,
            COALESCE(l.zip, p.zip) as zip,
            COALESCE(l.county, p.county) as county,
            COALESCE(l.latitude, p.latitude) as latitude,
            COALESCE(l.longitude, p.longitude) as longitude,

            -- Price/listing info
            l.list_price as price,
            l.beds,
            l.baths,
            l.sqft,
            COALESCE(l.acreage, p.acreage) as acreage,
            l.year_built,
            l.property_type,
            l.style,

            -- Status
            l.status,
            l.days_on_market,
            l.list_date,
            NULL as initial_price,
            NULL as price_history,
            NULL as status_history,

            -- Agent info
            l.listing_agent_name,
            l.listing_agent_phone,
            l.listing_agent_email,
            l.listing_office_name as listing_brokerage,

            -- Financial (from parcels)
            l.hoa_fee,
            p.assessed_value as tax_assessed_value,
            p.tax_annual as tax_annual_amount,
            NULL as zestimate,
            NULL as rent_zestimate,

            -- Features
            l.views,
            NULL as water_features,
            l.amenities,
            l.heating,
            l.cooling,
            l.garage,
            NULL as sewer,
            NULL as roof,
            NULL as stories,
            NULL as subdivision,

            -- Spatial (from parcels)
            p.flood_zone,
            p.flood_zone_subtype,
            p.flood_factor,
            p.flood_sfha,
            p.elevation_feet,
            p.slope_percent,
            p.aspect,
            p.view_potential,
            p.wildfire_risk,
            p.wildfire_score,
            p.spatial_enriched_at,

            -- URLs/media
            l.zillow_url,
            NULL as realtor_url,
            l.redfin_url,
            l.mls_url,
            l.idx_url,
            l.photos as photo_urls,
            l.primary_photo,
            l.virtual_tour_url,

            -- Client work
            l.added_for,
            l.added_by,
            l.notes,
            l.source,
            NULL as captured_by,

            -- Photo verification
            l.photo_source,
            l.photo_confidence,
            l.photo_verified_at,
            l.photo_review_status,
            l.photo_count,

            -- Timestamps
            l.captured_at as created_at,
            l.updated_at,
            NULL as last_monitored_at

        FROM listings l
        LEFT JOIN parcels p ON l.parcel_id = p.id
    """)

    conn.commit()
    print("Created properties_v2 view")


def verify_view(conn: sqlite3.Connection):
    """Verify the view works correctly."""
    print("\nVerification:")

    # Count records
    cursor = conn.execute("SELECT COUNT(*) FROM properties_v2")
    count = cursor.fetchone()[0]
    print(f"  properties_v2 rows: {count}")

    # Check a sample row
    cursor = conn.execute("""
        SELECT id, address, city, county, price, beds, baths, status
        FROM properties_v2
        WHERE address IS NOT NULL
        LIMIT 1
    """)
    row = cursor.fetchone()
    if row:
        print(f"  Sample: {row[1]}, {row[2]}, {row[3]} - ${row[4]:,} {row[5]}bd/{row[6]}ba ({row[7]})")

    # Check spatial data availability
    cursor = conn.execute("""
        SELECT COUNT(*) FROM properties_v2
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    """)
    geo_count = cursor.fetchone()[0]
    print(f"  With coordinates: {geo_count}")

    cursor = conn.execute("""
        SELECT COUNT(*) FROM properties_v2
        WHERE flood_zone IS NOT NULL
    """)
    flood_count = cursor.fetchone()[0]
    print(f"  With flood data: {flood_count}")


def main():
    print("=" * 60)
    print("CREATE PROPERTIES VIEW")
    print("=" * 60)
    print(f"Database: {DB_PATH}")
    print()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        create_view(conn)
        verify_view(conn)
        print("\nView created successfully.")
        print("\nThe dashboard can now query 'properties_v2' instead of 'properties'")
        print("to use the new normalized schema (parcels + listings).")
    except Exception as e:
        print(f"Error: {e}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
