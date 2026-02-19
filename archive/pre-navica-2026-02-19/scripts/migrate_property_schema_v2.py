#!/usr/bin/env python3
"""
Property Schema Migration v2

Adds new tables and columns for the property system architecture reset:
- contact_listings: Junction table for lead-property relationships
- listing_photos: Audit trail for photo verification
- enrichment_queue: Priority queue for photo/data enrichment
- Spatial columns on parcels (flood, elevation, views, wildfire)
- Photo verification columns on listings

Run with: python scripts/migrate_property_schema_v2.py

DEV ONLY - do not run in production without review.
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'


def add_column_if_not_exists(conn, table: str, column: str, col_type: str):
    """Add a column to a table if it doesn't already exist."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    existing_cols = {row[1] for row in cursor.fetchall()}

    if column not in existing_cols:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            print(f"  Added {table}.{column}")
            return True
        except sqlite3.OperationalError as e:
            print(f"  Error adding {table}.{column}: {e}")
            return False
    return False


def create_contact_listings_table(conn: sqlite3.Connection):
    """Create the contact_listings junction table."""

    print("\nCreating contact_listings table...")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS contact_listings (
            id TEXT PRIMARY KEY,
            contact_id TEXT NOT NULL,
            listing_id TEXT NOT NULL,

            -- Relationship type
            relationship TEXT NOT NULL DEFAULT 'portfolio',
            -- 'portfolio' - Added to client's search packet
            -- 'favorite' - Client favorited on IDX
            -- 'viewed' - Client viewed on IDX
            -- 'showing_scheduled' - Showing scheduled
            -- 'showing_done' - Showing completed
            -- 'offer_made' - Offer submitted
            -- 'offer_accepted' - Offer accepted
            -- 'purchased' - Closed
            -- 'rejected' - Client rejected

            -- Client feedback
            client_rating INTEGER,           -- 1-5 stars
            client_notes TEXT,               -- Client's comments
            agent_notes TEXT,                -- Agent's notes

            -- Workflow tracking
            added_at TEXT DEFAULT CURRENT_TIMESTAMP,
            shown_at TEXT,
            offer_at TEXT,
            closed_at TEXT,

            -- Match data (if from automated matching)
            match_score REAL,
            match_breakdown TEXT,            -- JSON breakdown of score

            -- Timestamps
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (contact_id) REFERENCES leads(id),
            FOREIGN KEY (listing_id) REFERENCES listings(id),
            UNIQUE(contact_id, listing_id, relationship)
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_contact_listings_contact ON contact_listings(contact_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contact_listings_listing ON contact_listings(listing_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contact_listings_relationship ON contact_listings(relationship)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contact_listings_added ON contact_listings(added_at DESC)")

    print("  contact_listings table created")


def create_listing_photos_table(conn: sqlite3.Connection):
    """Create the listing_photos audit table."""

    print("\nCreating listing_photos table...")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS listing_photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id TEXT NOT NULL,

            -- Photo data
            photo_url TEXT NOT NULL,
            photo_source TEXT NOT NULL,       -- 'mls', 'redfin', 'zillow', 'realtor', 'manual'
            photo_index INTEGER DEFAULT 0,    -- Order in gallery (0 = primary)

            -- Verification
            confidence_score REAL,            -- 0-100 verification confidence
            verification_factors TEXT,        -- JSON: {address_match: 95, price_match: 100, ...}
            verified_at TEXT,
            verified_by TEXT,                 -- 'auto' or agent name

            -- Status
            status TEXT DEFAULT 'verified',   -- 'verified', 'pending_review', 'rejected'
            rejection_reason TEXT,

            -- Timestamps
            fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (listing_id) REFERENCES listings(id)
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_listing_photos_listing ON listing_photos(listing_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_listing_photos_source ON listing_photos(photo_source)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_listing_photos_status ON listing_photos(status)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_listing_photos_unique ON listing_photos(listing_id, photo_url)")

    print("  listing_photos table created")


def create_enrichment_queue_table(conn: sqlite3.Connection):
    """Create the enrichment_queue table for prioritized enrichment."""

    print("\nCreating enrichment_queue table...")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS enrichment_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id TEXT NOT NULL,

            -- Priority
            priority INTEGER DEFAULT 50,      -- Higher = more urgent (0-100)
            priority_reason TEXT,             -- Why it's prioritized
            -- Priority reasons:
            -- 'active_portfolio' - In client's active packet
            -- 'hot_lead_favorite' - Favorited by hot lead
            -- 'new_listing' - Recently added
            -- 'background' - Batch processing

            -- Enrichment type
            enrichment_type TEXT NOT NULL,    -- 'photos', 'redfin', 'zillow', 'spatial'

            -- Status tracking
            status TEXT DEFAULT 'pending',    -- 'pending', 'processing', 'completed', 'failed'
            attempts INTEGER DEFAULT 0,
            last_attempt_at TEXT,
            last_error TEXT,
            completed_at TEXT,

            -- Rate limiting
            source TEXT,                      -- Target source for rate limiting

            -- Timestamps
            queued_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (listing_id) REFERENCES listings(id),
            UNIQUE(listing_id, enrichment_type)
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_enrichment_queue_priority ON enrichment_queue(priority DESC, queued_at ASC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_enrichment_queue_status ON enrichment_queue(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_enrichment_queue_type ON enrichment_queue(enrichment_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_enrichment_queue_source ON enrichment_queue(source, last_attempt_at)")

    print("  enrichment_queue table created")


def add_parcel_spatial_columns(conn: sqlite3.Connection):
    """Add spatial enrichment columns to parcels table."""

    print("\nAdding spatial columns to parcels...")

    spatial_columns = [
        ("flood_zone", "TEXT"),                 # FEMA zone: X, A, AE, VE, etc.
        ("flood_zone_subtype", "TEXT"),         # Zone subtype
        ("flood_factor", "INTEGER"),            # Risk score 1-10
        ("flood_sfha", "INTEGER DEFAULT 0"),    # Special Flood Hazard Area (1=yes)
        ("elevation_feet", "INTEGER"),          # Elevation in feet
        ("slope_percent", "REAL"),              # Terrain slope percentage
        ("aspect", "TEXT"),                     # Facing direction: N, NE, E, etc.
        ("view_potential", "INTEGER"),          # Mountain view score 1-10
        ("wildfire_risk", "TEXT"),              # Risk category
        ("wildfire_score", "INTEGER"),          # Risk score 1-10
        ("spatial_enriched_at", "TEXT"),        # When spatial data was last updated
    ]

    added = 0
    for col_name, col_type in spatial_columns:
        if add_column_if_not_exists(conn, "parcels", col_name, col_type):
            added += 1

    # Add spatial indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_parcels_lat_lng ON parcels(latitude, longitude)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_parcels_flood ON parcels(flood_zone)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_parcels_elevation ON parcels(elevation_feet)")

    print(f"  Added {added} spatial columns to parcels")


def add_listing_photo_columns(conn: sqlite3.Connection):
    """Add photo verification columns to listings table."""

    print("\nAdding photo verification columns to listings...")

    photo_columns = [
        ("photo_source", "TEXT"),               # 'mls', 'redfin', 'zillow', 'manual'
        ("photo_confidence", "REAL"),           # Overall confidence score (0-100)
        ("photo_verified_at", "TEXT"),          # When photos were verified
        ("photo_verified_by", "TEXT"),          # 'auto' or agent name
        ("photo_review_status", "TEXT"),        # 'verified', 'pending_review', 'rejected'
        ("photo_count", "INTEGER DEFAULT 0"),   # Number of photos
    ]

    added = 0
    for col_name, col_type in photo_columns:
        if add_column_if_not_exists(conn, "listings", col_name, col_type):
            added += 1

    print(f"  Added {added} photo columns to listings")


def add_listing_address_columns(conn: sqlite3.Connection):
    """Add denormalized address columns to listings for faster queries."""

    print("\nAdding address columns to listings...")

    address_columns = [
        ("address", "TEXT"),                    # Denormalized from parcel
        ("city", "TEXT"),
        ("state", "TEXT DEFAULT 'NC'"),
        ("zip", "TEXT"),
        ("county", "TEXT"),
        ("latitude", "REAL"),
        ("longitude", "REAL"),
        ("acreage", "REAL"),
    ]

    added = 0
    for col_name, col_type in address_columns:
        if add_column_if_not_exists(conn, "listings", col_name, col_type):
            added += 1

    print(f"  Added {added} address columns to listings")


def denormalize_listing_addresses(conn: sqlite3.Connection):
    """Copy address data from parcels to listings for fast queries."""

    print("\nDenormalizing addresses to listings...")

    # Count listings without addresses
    cursor = conn.execute("""
        SELECT COUNT(*) FROM listings
        WHERE parcel_id IS NOT NULL
        AND (address IS NULL OR address = '')
    """)
    count = cursor.fetchone()[0]

    if count == 0:
        print("  No listings need address denormalization")
        return

    # Update listings with parcel addresses
    conn.execute("""
        UPDATE listings SET
            address = (SELECT address FROM parcels WHERE parcels.id = listings.parcel_id),
            city = (SELECT city FROM parcels WHERE parcels.id = listings.parcel_id),
            state = (SELECT state FROM parcels WHERE parcels.id = listings.parcel_id),
            zip = (SELECT zip FROM parcels WHERE parcels.id = listings.parcel_id),
            county = (SELECT county FROM parcels WHERE parcels.id = listings.parcel_id),
            latitude = (SELECT latitude FROM parcels WHERE parcels.id = listings.parcel_id),
            longitude = (SELECT longitude FROM parcels WHERE parcels.id = listings.parcel_id),
            acreage = (SELECT acreage FROM parcels WHERE parcels.id = listings.parcel_id)
        WHERE parcel_id IS NOT NULL
        AND (address IS NULL OR address = '')
    """)

    conn.commit()

    # Count updated
    cursor = conn.execute("""
        SELECT COUNT(*) FROM listings
        WHERE address IS NOT NULL AND address != ''
    """)
    updated = cursor.fetchone()[0]

    print(f"  Denormalized addresses for {count} listings (total with address: {updated})")


def verify_schema(conn: sqlite3.Connection):
    """Verify the schema updates were successful."""

    print("\n" + "=" * 60)
    print("VERIFICATION")
    print("=" * 60)

    # Check tables exist
    tables = ['parcels', 'listings', 'contact_listings', 'listing_photos', 'enrichment_queue']
    for table in tables:
        cursor = conn.execute(f"SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='{table}'")
        exists = cursor.fetchone()[0] > 0
        print(f"  {table}: {'EXISTS' if exists else 'MISSING'}")

        if exists:
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"    → {count} rows")

    # Check new columns on parcels
    print("\n  parcels spatial columns:")
    cursor = conn.execute("PRAGMA table_info(parcels)")
    cols = {row[1] for row in cursor.fetchall()}
    spatial_cols = ['flood_zone', 'elevation_feet', 'view_potential', 'wildfire_risk']
    for col in spatial_cols:
        print(f"    {col}: {'✓' if col in cols else '✗'}")

    # Check new columns on listings
    print("\n  listings photo columns:")
    cursor = conn.execute("PRAGMA table_info(listings)")
    cols = {row[1] for row in cursor.fetchall()}
    photo_cols = ['photo_source', 'photo_confidence', 'photo_verified_at', 'photo_review_status']
    for col in photo_cols:
        print(f"    {col}: {'✓' if col in cols else '✗'}")


def main():
    print("=" * 60)
    print("PROPERTY SCHEMA MIGRATION v2")
    print("=" * 60)
    print(f"Database: {DB_PATH}")
    print()
    print("This migration adds:")
    print("  - contact_listings junction table")
    print("  - listing_photos audit table")
    print("  - enrichment_queue table")
    print("  - Spatial columns on parcels")
    print("  - Photo verification columns on listings")
    print("  - Denormalized address columns on listings")
    print()

    if '--yes' not in sys.argv:
        response = input("Continue? [y/N] ")
        if response.lower() != 'y':
            print("Aborted.")
            return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        # Create new tables
        create_contact_listings_table(conn)
        create_listing_photos_table(conn)
        create_enrichment_queue_table(conn)

        # Add new columns
        add_parcel_spatial_columns(conn)
        add_listing_photo_columns(conn)
        add_listing_address_columns(conn)

        conn.commit()

        # Denormalize addresses
        denormalize_listing_addresses(conn)

        # Verify
        verify_schema(conn)

        print("\n" + "=" * 60)
        print("MIGRATION COMPLETE")
        print("=" * 60)

    except Exception as e:
        print(f"\nERROR: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
