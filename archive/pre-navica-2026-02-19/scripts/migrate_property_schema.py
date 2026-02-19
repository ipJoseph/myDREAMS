#!/usr/bin/env python3
"""
Property Schema Migration

Migrates from monolithic 'properties' table to normalized schema:
- parcels (physical land)
- listings (MLS events)
- agents (from MLS roster)

Run with: python scripts/migrate_property_schema.py

DEV ONLY - do not run in production without review.
"""

import csv
import hashlib
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'
AGENT_CSV = Path('/home/bigeug/Downloads/events.csv')

def generate_id(prefix: str, *args) -> str:
    """Generate a deterministic ID from input values."""
    data = '|'.join(str(a) for a in args if a)
    hash_val = hashlib.md5(data.encode()).hexdigest()[:12]
    return f"{prefix}_{hash_val}"


def create_tables(conn: sqlite3.Connection):
    """Create new normalized tables."""

    print("Creating new tables...")

    # Parcels table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS parcels (
            id TEXT PRIMARY KEY,

            -- Identity
            apn TEXT,
            alt_apn TEXT,
            county TEXT,
            state TEXT DEFAULT 'NC',

            -- Location
            address TEXT,
            address_raw TEXT,
            city TEXT,
            zip TEXT,
            latitude REAL,
            longitude REAL,

            -- Physical
            acreage REAL,
            legal_description TEXT,
            land_use TEXT,

            -- Owner (from PropStream)
            owner_name TEXT,
            owner_name_2 TEXT,
            owner_occupied TEXT,
            owner_phone TEXT,
            owner_email TEXT,
            mailing_address TEXT,
            mailing_city TEXT,
            mailing_state TEXT,
            mailing_zip TEXT,

            -- Tax/Assessment
            assessed_value INTEGER,
            assessed_land_value INTEGER,
            assessed_building_value INTEGER,
            tax_annual INTEGER,

            -- Sales history
            last_sale_date TEXT,
            last_sale_amount INTEGER,

            -- Meta
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_parcels_apn ON parcels(apn)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_parcels_county ON parcels(county)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_parcels_city ON parcels(city)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_parcels_apn_county ON parcels(apn, county) WHERE apn IS NOT NULL")

    # Listings table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id TEXT PRIMARY KEY,
            parcel_id TEXT,

            -- MLS Identity
            mls_source TEXT,
            mls_number TEXT,

            -- Listing details
            status TEXT,
            list_price INTEGER,
            list_date TEXT,
            sold_price INTEGER,
            sold_date TEXT,
            days_on_market INTEGER,

            -- Property details
            beds INTEGER,
            baths REAL,
            sqft INTEGER,
            year_built INTEGER,
            property_type TEXT,
            style TEXT,

            -- Features
            views TEXT,
            amenities TEXT,
            heating TEXT,
            cooling TEXT,
            garage TEXT,
            hoa_fee INTEGER,

            -- Media
            photos TEXT,
            primary_photo TEXT,
            virtual_tour_url TEXT,

            -- Links
            mls_url TEXT,
            idx_url TEXT,
            redfin_url TEXT,
            redfin_id TEXT,
            zillow_url TEXT,
            zillow_id TEXT,

            -- Agent (denormalized for quick access)
            listing_agent_id TEXT,
            listing_agent_name TEXT,
            listing_agent_phone TEXT,
            listing_agent_email TEXT,
            listing_office_id TEXT,
            listing_office_name TEXT,

            -- For client work
            added_for TEXT,
            added_by TEXT,
            notes TEXT,

            -- Meta
            source TEXT,
            captured_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (parcel_id) REFERENCES parcels(id)
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_listings_parcel ON listings(parcel_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_listings_status ON listings(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_listings_mls ON listings(mls_source, mls_number)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(list_price)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_listings_city ON listings(parcel_id)")  # Will join to parcels
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_listings_mls_unique ON listings(mls_source, mls_number) WHERE mls_source IS NOT NULL AND mls_number IS NOT NULL")

    # Agents table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,

            -- Identity
            mls_source TEXT,
            mls_agent_id TEXT,
            mls_office_id TEXT,

            -- Contact
            name TEXT NOT NULL,
            first_name TEXT,
            last_name TEXT,
            phone TEXT,
            email TEXT,
            website TEXT,
            photo_url TEXT,

            -- Role
            agent_type TEXT,
            office_name TEXT,

            -- Address
            address TEXT,
            city TEXT,
            state TEXT,
            zip TEXT,

            -- Meta
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_agents_mls ON agents(mls_source, mls_agent_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agents_name ON agents(name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agents_email ON agents(email)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_mls_unique ON agents(mls_source, mls_agent_id) WHERE mls_source IS NOT NULL AND mls_agent_id IS NOT NULL")

    conn.commit()
    print("  Tables created successfully")


def import_csar_agents(conn: sqlite3.Connection):
    """Import agents from CSAR MLS roster."""

    if not AGENT_CSV.exists():
        print(f"  Agent CSV not found: {AGENT_CSV}")
        return 0

    print(f"Importing CSAR agents from {AGENT_CSV}...")

    imported = 0
    skipped = 0

    with open(AGENT_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            try:
                # Parse the messy column names from the scrape
                name = row.get('text-center', '').strip()
                if not name or name == 'text-center':
                    continue

                agent_id = row.get('agentAgentID', '').strip()
                office_id = row.get('jsOfficeDialog', '').strip()
                agent_type = row.get('agentOfficeType', '').strip()

                # Address fields
                addr1 = row.get('agentAddress', '').strip()
                addr2 = row.get('agentAddress 2', '').strip()

                # Parse city/state/zip from addr2 if it looks like "City, ST ZIP"
                city, state, zip_code = '', '', ''
                if addr2 and ',' in addr2:
                    parts = addr2.split(',')
                    city = parts[0].strip()
                    if len(parts) > 1:
                        state_zip = parts[1].strip().split()
                        if state_zip:
                            state = state_zip[0]
                        if len(state_zip) > 1:
                            zip_code = state_zip[1]

                # Contact info
                phone = row.get('col-12 2', '').strip()
                email = row.get('col-12 3', '').strip()
                website = row.get('col-12 href 2', '').strip()
                photo_url = row.get('rosterResultsImage src', '').strip()

                # Skip placeholder photos
                if 'no_agent.gif' in photo_url:
                    photo_url = None

                # Parse name into first/last
                name_parts = name.replace(' (MLS Only)', '').replace(' - BC', '').split()
                first_name = name_parts[0] if name_parts else ''
                last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''

                # Generate ID
                agent_db_id = generate_id('agt', 'CSAR', agent_id)

                conn.execute("""
                    INSERT OR REPLACE INTO agents (
                        id, mls_source, mls_agent_id, mls_office_id,
                        name, first_name, last_name, phone, email, website, photo_url,
                        agent_type, address, city, state, zip, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    agent_db_id, 'CSAR', agent_id, office_id,
                    name, first_name, last_name, phone, email, website, photo_url,
                    agent_type, addr1, city, state, zip_code,
                    datetime.now().isoformat()
                ))
                imported += 1

            except Exception as e:
                print(f"  Error importing agent: {e}")
                skipped += 1
                continue

    conn.commit()
    print(f"  Imported {imported} agents, skipped {skipped}")
    return imported


def migrate_properties(conn: sqlite3.Connection):
    """Migrate existing properties to parcels + listings."""

    print("Migrating existing properties...")

    cursor = conn.execute("SELECT COUNT(*) FROM properties")
    total = cursor.fetchone()[0]
    print(f"  Found {total} properties to migrate")

    cursor = conn.execute("SELECT * FROM properties")
    columns = [desc[0] for desc in cursor.description]

    parcels_created = 0
    listings_created = 0

    for row in cursor:
        prop = dict(zip(columns, row))

        try:
            # Create or find parcel
            parcel_id = None

            # Determine parcel identity
            apn = prop.get('parcel_id') or prop.get('alt_parcel_id')
            county = prop.get('county') or prop.get('county_onemap') or 'Unknown'
            address = prop.get('address', '')
            city = prop.get('city', '')

            if apn and county:
                parcel_id = generate_id('prc', apn, county)
            elif address and city:
                parcel_id = generate_id('prc', address, city)
            else:
                parcel_id = generate_id('prc', prop.get('id', ''))

            # Check if parcel exists
            existing = conn.execute(
                "SELECT id FROM parcels WHERE id = ?", (parcel_id,)
            ).fetchone()

            if not existing:
                conn.execute("""
                    INSERT INTO parcels (
                        id, apn, alt_apn, county, state,
                        address, address_raw, city, zip, latitude, longitude,
                        acreage, legal_description, land_use,
                        owner_name, owner_name_2, owner_occupied, owner_phone, owner_email,
                        mailing_address, mailing_city, mailing_state, mailing_zip,
                        assessed_value, assessed_land_value, assessed_building_value, tax_annual,
                        last_sale_date, last_sale_amount
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    parcel_id,
                    prop.get('parcel_id'),
                    prop.get('alt_parcel_id'),
                    county,
                    prop.get('state', 'NC'),
                    address,
                    address,  # address_raw same for now
                    city,
                    prop.get('zip'),
                    prop.get('latitude'),
                    prop.get('longitude'),
                    prop.get('acreage') or prop.get('parcel_acreage'),
                    prop.get('legal_description'),
                    prop.get('land_use_description') or prop.get('property_type'),
                    prop.get('owner_name') or f"{prop.get('owner_first_name', '')} {prop.get('owner_last_name', '')}".strip() or None,
                    prop.get('owner_name_2') or f"{prop.get('owner2_first_name', '')} {prop.get('owner2_last_name', '')}".strip() or None,
                    prop.get('owner_occupied'),
                    prop.get('owner_mobile') or prop.get('owner_landline'),
                    prop.get('owner_email'),
                    prop.get('mailing_address') or prop.get('owner_mailing_address'),
                    prop.get('mailing_city') or prop.get('owner_mailing_city'),
                    prop.get('mailing_state') or prop.get('owner_mailing_state'),
                    prop.get('mailing_zip') or prop.get('owner_mailing_zip'),
                    prop.get('assessed_value') or prop.get('assessed_total_value'),
                    prop.get('assessed_land_value'),
                    prop.get('assessed_building_value'),
                    prop.get('tax_annual_amount'),
                    prop.get('last_sale_date') or prop.get('last_sale_date_text'),
                    prop.get('last_sale_amount')
                ))
                parcels_created += 1

            # Create listing
            mls_source = prop.get('mls_source') or 'Unknown'
            mls_number = prop.get('mls_number') or prop.get('original_mls_number') or prop.get('idx_mls_number')

            listing_id = generate_id('lst', mls_source, mls_number) if mls_number else generate_id('lst', prop.get('id', ''))

            conn.execute("""
                INSERT OR REPLACE INTO listings (
                    id, parcel_id, mls_source, mls_number,
                    status, list_price, list_date, days_on_market,
                    beds, baths, sqft, year_built, property_type, style,
                    views, amenities, heating, cooling, garage, hoa_fee,
                    photos, primary_photo, virtual_tour_url,
                    mls_url, idx_url, redfin_url, redfin_id, zillow_url, zillow_id,
                    listing_agent_name, listing_agent_phone, listing_agent_email, listing_office_name,
                    added_for, added_by, notes, source, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                listing_id, parcel_id, mls_source, mls_number,
                prop.get('status'),
                prop.get('price'),
                prop.get('list_date'),
                prop.get('days_on_market'),
                prop.get('beds'),
                prop.get('baths'),
                prop.get('sqft'),
                prop.get('year_built'),
                prop.get('property_type'),
                prop.get('style'),
                prop.get('views'),
                prop.get('amenities'),
                prop.get('heating'),
                prop.get('cooling'),
                prop.get('garage'),
                prop.get('hoa_fee'),
                prop.get('photo_urls'),
                prop.get('primary_photo'),
                prop.get('virtual_tour_url'),
                prop.get('mls_url'),
                prop.get('idx_url'),
                prop.get('redfin_url'),
                prop.get('redfin_id'),
                prop.get('zillow_url'),
                prop.get('zillow_id'),
                prop.get('listing_agent_name'),
                prop.get('listing_agent_phone'),
                prop.get('listing_agent_email'),
                prop.get('listing_brokerage'),
                prop.get('added_for'),
                prop.get('added_by') or prop.get('captured_by'),
                prop.get('notes'),
                prop.get('source'),
                datetime.now().isoformat()
            ))
            listings_created += 1

        except Exception as e:
            print(f"  Error migrating property {prop.get('id')}: {e}")
            continue

    conn.commit()
    print(f"  Created {parcels_created} parcels, {listings_created} listings")
    return parcels_created, listings_created


def verify_migration(conn: sqlite3.Connection):
    """Verify the migration was successful."""

    print("\nVerification:")

    stats = {}
    for table in ['properties', 'parcels', 'listings', 'agents']:
        try:
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
            stats[table] = cursor.fetchone()[0]
        except:
            stats[table] = 'N/A'

    print(f"  Original properties: {stats['properties']}")
    print(f"  New parcels: {stats['parcels']}")
    print(f"  New listings: {stats['listings']}")
    print(f"  Agents: {stats['agents']}")

    # Sample data
    print("\nSample parcel:")
    cursor = conn.execute("SELECT id, apn, county, address, city FROM parcels LIMIT 1")
    row = cursor.fetchone()
    if row:
        print(f"  {row}")

    print("\nSample listing:")
    cursor = conn.execute("SELECT id, mls_source, mls_number, status, list_price FROM listings LIMIT 1")
    row = cursor.fetchone()
    if row:
        print(f"  {row}")

    print("\nSample agent:")
    cursor = conn.execute("SELECT id, name, phone, email FROM agents LIMIT 1")
    row = cursor.fetchone()
    if row:
        print(f"  {row}")


def main():
    print("=" * 60)
    print("PROPERTY SCHEMA MIGRATION")
    print("=" * 60)
    print(f"Database: {DB_PATH}")
    print()

    # Backup reminder
    print("WARNING: This will modify the database.")
    print("Ensure you have a backup before proceeding.")
    print()

    if '--yes' not in sys.argv:
        response = input("Continue? [y/N] ")
        if response.lower() != 'y':
            print("Aborted.")
            return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        create_tables(conn)
        import_csar_agents(conn)
        migrate_properties(conn)
        verify_migration(conn)

        print("\n" + "=" * 60)
        print("MIGRATION COMPLETE")
        print("=" * 60)
        print("\nThe old 'properties' table is preserved.")
        print("Once verified, you can drop it with:")
        print("  ALTER TABLE properties RENAME TO properties_backup;")

    except Exception as e:
        print(f"\nERROR: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
