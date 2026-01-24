#!/usr/bin/env python3
"""
Migrate Redfin Properties to Dreams DB

One-time migration script to consolidate properties from redfin_imports.db into dreams.db.
Implements smart merge logic:
1. Match by MLS number (most reliable)
2. Match by normalized address
3. Insert new if no match

Usage:
    python scripts/migrate_redfin_to_dreams.py --dry-run  # Preview changes
    python scripts/migrate_redfin_to_dreams.py            # Execute migration
"""

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database paths
DREAMS_DB = PROJECT_ROOT / 'data' / 'dreams.db'
REDFIN_DB = PROJECT_ROOT / 'data' / 'redfin_imports.db'


class PropertyMigrator:
    """Migrates properties from redfin_imports.db to dreams.db."""

    # Columns to copy from redfin_imports to dreams
    COPY_COLUMNS = [
        'mls_number', 'original_mls_number', 'parcel_id', 'address', 'city', 'state', 'zip',
        'county', 'price', 'beds', 'baths', 'sqft', 'acreage', 'year_built', 'property_type',
        'subdivision', 'days_on_market', 'status', 'hoa_fee', 'mls_source', 'redfin_url',
        'latitude', 'longitude', 'listing_agent_name', 'listing_agent_phone',
        'listing_agent_email', 'listing_brokerage', 'page_views', 'favorites_count',
        'primary_photo', 'source', 'created_at', 'updated_at', 'sync_status',
        # PropStream fields
        'owner_first_name', 'owner_last_name', 'owner2_first_name', 'owner2_last_name',
        'owner_name', 'owner_name_2', 'owner_occupied', 'vacant', 'owner_mobile',
        'owner_landline', 'owner_email', 'mailing_address', 'mailing_city', 'mailing_state',
        'mailing_zip', 'owner_mailing_address', 'owner_mailing_city', 'owner_mailing_state',
        'owner_mailing_zip', 'do_not_mail', 'assessed_value', 'assessed_land_value',
        'assessed_building_value', 'assessed_total_value', 'last_sale_date',
        'last_sale_date_text', 'last_sale_amount', 'est_value', 'est_equity', 'est_ltv',
        'open_loans', 'loan_balance', 'condition_total', 'condition_interior',
        'condition_exterior', 'stories', 'has_hoa', 'propstream_source', 'alt_parcel_id',
        'parcel_acreage', 'legal_description', 'land_use_description',
        # OneMap fields
        'year_built_onemap', 'subdivision_onemap', 'county_onemap', 'onemap_enriched_at'
    ]

    def __init__(self, dreams_db: str, redfin_db: str, dry_run: bool = False):
        self.dreams_db = dreams_db
        self.redfin_db = redfin_db
        self.dry_run = dry_run
        self.stats = {
            'total_redfin': 0,
            'matched_by_mls': 0,
            'matched_by_address': 0,
            'inserted': 0,
            'updated': 0,
            'errors': 0,
        }

    def _normalize_address(self, address: str) -> str:
        """Normalize address for matching (street portion only)."""
        if not address:
            return ''
        # Extract street portion before city
        # Pattern: "123 Main St, Franklin, NC 28734" -> "123 Main St"
        parts = address.split(',')
        street = parts[0].strip() if parts else address
        # Normalize common variations
        street = street.upper()
        street = re.sub(r'\s+', ' ', street)
        street = re.sub(r'\bSTREET\b', 'ST', street)
        street = re.sub(r'\bDRIVE\b', 'DR', street)
        street = re.sub(r'\bROAD\b', 'RD', street)
        street = re.sub(r'\bLANE\b', 'LN', street)
        street = re.sub(r'\bTRAIL\b', 'TRL', street)
        street = re.sub(r'\bCIRCLE\b', 'CIR', street)
        street = re.sub(r'\bCOURT\b', 'CT', street)
        street = re.sub(r'\bAVENUE\b', 'AVE', street)
        return street

    def _find_dreams_property(self, cursor, data: Dict) -> Optional[Dict]:
        """Find matching property in dreams.db by MLS or address."""

        # 1. Try MLS number match
        mls_number = data.get('mls_number')
        if mls_number:
            cursor.execute('''
                SELECT id, mls_number, address, sources_json
                FROM properties
                WHERE mls_number = ? OR original_mls_number = ?
                LIMIT 1
            ''', (mls_number, mls_number))
            row = cursor.fetchone()
            if row:
                self.stats['matched_by_mls'] += 1
                return dict(row)

        # 2. Try address match
        address = data.get('address', '')
        normalized = self._normalize_address(address)
        if normalized and len(normalized) > 5:
            cursor.execute('''
                SELECT id, mls_number, address, sources_json
                FROM properties
                WHERE UPPER(address) LIKE ?
                LIMIT 1
            ''', (f"{normalized}%",))
            row = cursor.fetchone()
            if row:
                self.stats['matched_by_address'] += 1
                return dict(row)

        return None

    def _update_sources_json(self, existing: Optional[str], new_source: str) -> str:
        """Update sources_json array with new source."""
        try:
            sources = json.loads(existing) if existing else []
        except (json.JSONDecodeError, TypeError):
            sources = []

        if new_source and new_source not in sources:
            sources.append(new_source)

        return json.dumps(sources)

    def _build_update_sql(self, prop_data: Dict, existing_id: str) -> Tuple[str, List]:
        """Build UPDATE SQL for merging property data."""
        # Only update non-null values from redfin
        updates = []
        values = []

        for col in self.COPY_COLUMNS:
            val = prop_data.get(col)
            if val is not None:
                updates.append(f"{col} = COALESCE(?, {col})")
                values.append(val)

        # Update sources_json
        updates.append("sources_json = ?")
        values.append(prop_data.get('sources_json', '["redfin_csv"]'))

        # Update timestamp
        updates.append("updated_at = ?")
        values.append(datetime.now(timezone.utc).isoformat())

        values.append(existing_id)

        sql = f"UPDATE properties SET {', '.join(updates)} WHERE id = ?"
        return sql, values

    def _build_insert_sql(self, prop_data: Dict) -> Tuple[str, List]:
        """Build INSERT SQL for new property."""
        # Generate new ID
        prop_id = str(uuid.uuid4())

        # Prepare columns and values
        columns = ['id'] + [c for c in self.COPY_COLUMNS if prop_data.get(c) is not None]
        columns.append('sources_json')

        values = [prop_id] + [prop_data.get(c) for c in self.COPY_COLUMNS if prop_data.get(c) is not None]
        values.append(prop_data.get('sources_json', '["redfin_csv"]'))

        placeholders = ', '.join(['?'] * len(columns))
        sql = f"INSERT INTO properties ({', '.join(columns)}) VALUES ({placeholders})"

        return sql, values

    def migrate(self):
        """Execute the migration."""
        logger.info(f"Starting migration from {self.redfin_db} to {self.dreams_db}")

        if self.dry_run:
            logger.info("DRY RUN - No changes will be made")

        # Connect to both databases
        redfin_conn = sqlite3.connect(self.redfin_db)
        redfin_conn.row_factory = sqlite3.Row

        dreams_conn = sqlite3.connect(self.dreams_db)
        dreams_conn.row_factory = sqlite3.Row

        try:
            redfin_cursor = redfin_conn.cursor()
            dreams_cursor = dreams_conn.cursor()

            # Get all properties from redfin_imports
            redfin_cursor.execute('SELECT * FROM properties')
            redfin_properties = redfin_cursor.fetchall()
            self.stats['total_redfin'] = len(redfin_properties)

            logger.info(f"Found {self.stats['total_redfin']} properties in redfin_imports.db")

            for row in redfin_properties:
                prop_data = dict(row)

                try:
                    # Find existing in dreams.db
                    existing = self._find_dreams_property(dreams_cursor, prop_data)

                    # Update sources_json
                    if existing:
                        prop_data['sources_json'] = self._update_sources_json(
                            existing.get('sources_json'),
                            'redfin_csv'
                        )
                    else:
                        prop_data['sources_json'] = '["redfin_csv"]'

                    if existing:
                        # Update existing property
                        if not self.dry_run:
                            sql, values = self._build_update_sql(prop_data, existing['id'])
                            dreams_cursor.execute(sql, values)
                        self.stats['updated'] += 1
                        logger.debug(f"Updated: {prop_data.get('address')} (matched existing)")
                    else:
                        # Insert new property
                        if not self.dry_run:
                            sql, values = self._build_insert_sql(prop_data)
                            dreams_cursor.execute(sql, values)
                        self.stats['inserted'] += 1
                        logger.debug(f"Inserted: {prop_data.get('address')}")

                except Exception as e:
                    self.stats['errors'] += 1
                    logger.error(f"Error processing {prop_data.get('address')}: {e}")
                    continue

            if not self.dry_run:
                dreams_conn.commit()
                logger.info("Migration committed to database")

        finally:
            redfin_conn.close()
            dreams_conn.close()

        return self.stats

    def print_summary(self):
        """Print migration summary."""
        print("\n" + "=" * 60)
        print("MIGRATION SUMMARY")
        print("=" * 60)
        print(f"Total in redfin_imports.db:  {self.stats['total_redfin']}")
        print("-" * 60)
        print(f"Matched by MLS#:             {self.stats['matched_by_mls']}")
        print(f"Matched by address:          {self.stats['matched_by_address']}")
        print(f"Updated (merged):            {self.stats['updated']}")
        print(f"Inserted (new):              {self.stats['inserted']}")
        print(f"Errors:                      {self.stats['errors']}")
        print("=" * 60)

        if self.dry_run:
            print("\n[DRY RUN - No changes were made]")
        else:
            print("\n[Migration complete]")


def verify_migration(dreams_db: str):
    """Verify migration results."""
    conn = sqlite3.connect(dreams_db)
    cursor = conn.cursor()

    print("\n" + "=" * 60)
    print("VERIFICATION")
    print("=" * 60)

    # Total count
    cursor.execute("SELECT COUNT(*) FROM properties")
    total = cursor.fetchone()[0]
    print(f"Total properties in dreams.db: {total}")

    # By source
    cursor.execute("""
        SELECT source, COUNT(*) as count
        FROM properties
        GROUP BY source
        ORDER BY count DESC
    """)
    print("\nBy source:")
    for row in cursor.fetchall():
        print(f"  {row[0] or 'NULL'}: {row[1]}")

    # With sources_json
    cursor.execute("""
        SELECT COUNT(*) FROM properties
        WHERE sources_json IS NOT NULL AND sources_json != ''
    """)
    with_sources = cursor.fetchone()[0]
    print(f"\nWith sources_json tracking: {with_sources}")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description='Migrate redfin_imports.db to dreams.db')
    parser.add_argument('--dry-run', action='store_true', help='Preview without making changes')
    parser.add_argument('--verify', action='store_true', help='Verify migration results')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.verify:
        verify_migration(str(DREAMS_DB))
        return

    migrator = PropertyMigrator(
        dreams_db=str(DREAMS_DB),
        redfin_db=str(REDFIN_DB),
        dry_run=args.dry_run
    )

    migrator.migrate()
    migrator.print_summary()

    if not args.dry_run:
        verify_migration(str(DREAMS_DB))


if __name__ == '__main__':
    main()
