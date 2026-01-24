#!/usr/bin/env python3
"""
PropStream Excel Importer

Imports property data from PropStream Excel exports and merges with existing
Redfin data. PropStream provides valuable fields we can't get from Redfin:
- APN (Parcel ID)
- Owner information
- Mailing addresses
- Estimated values and equity
- Property condition ratings

Usage:
    python propstream_importer.py ~/Downloads/propstream.macon.county.xlsx
    python propstream_importer.py ~/Downloads/*.xlsx --dry-run
"""

import argparse
import glob
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import uuid

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import pandas as pd
except ImportError:
    print("Error: pandas required. Install with: pip install pandas openpyxl")
    sys.exit(1)

from wnc_zip_county import get_county

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database path - unified to dreams.db
DB_PATH = os.getenv('DREAMS_DB_PATH', str(PROJECT_ROOT / 'data' / 'dreams.db'))

# PropStream column mapping to our schema
PROPSTREAM_MAP = {
    'Address': 'address',
    'Unit #': 'unit',
    'City': 'city',
    'State': 'state',
    'Zip': 'zip',
    'County': 'county',
    'APN': 'parcel_id',
    'Property Type': 'property_type',
    'Bedrooms': 'beds',
    'Total Bathrooms': 'baths',
    'Building Sqft': 'sqft',
    'Lot Size Sqft': 'lot_sqft',
    'Year Built': 'year_built',
    'HOA Present': 'has_hoa',
    'Number of Stories': 'stories',
    # Owner info
    'Owner 1 First Name': 'owner_first_name',
    'Owner 1 Last Name': 'owner_last_name',
    'Owner 2 First Name': 'owner2_first_name',
    'Owner 2 Last Name': 'owner2_last_name',
    'Owner Occupied': 'owner_occupied',
    'Vacant': 'vacant',
    # Contact
    'Mobile': 'owner_mobile',
    'Landline': 'owner_landline',
    'Email': 'owner_email',
    # Mailing
    'Mailing Address': 'mailing_address',
    'Mailing City': 'mailing_city',
    'Mailing State': 'mailing_state',
    'Mailing Zip': 'mailing_zip',
    'Do Not Mail': 'do_not_mail',
    # Financial
    'Total Assessed Value': 'assessed_value',
    'Last Sale Date': 'last_sale_date',
    'Last Sale Amount': 'last_sale_amount',
    'Est. Value': 'est_value',
    'Est. Equity': 'est_equity',
    'Est. Loan-to-Value': 'est_ltv',
    'Total Open Loans': 'open_loans',
    'Est. Remaining balance of Open Loans': 'loan_balance',
    # Condition
    'Total Condition': 'condition_total',
    'Interior Condition': 'condition_interior',
    'Exterior Condition': 'condition_exterior',
    # MLS (may already have from Redfin, but PropStream has agent details)
    'MLS Status': 'mls_status',
    'MLS Date': 'mls_date',
    'MLS Amount': 'mls_amount',
    'MLS Agent Name': 'listing_agent_name',
    'MLS Agent Phone': 'listing_agent_phone',
    'MLS Agent E-Mail': 'listing_agent_email',
    'MLS Brokerage Name': 'listing_brokerage',
    # Additional fields (expanded mapping)
    'Prior Sale Date': 'prior_sale_date',
    'Prior Sale Amount': 'prior_sale_amount',
    'Bathroom Condition': 'condition_bathroom',
    'Kitchen Condition': 'condition_kitchen',
    'Foreclosure Factor': 'foreclosure_factor',
    'Lien Type': 'lien_type',
    'Lien Date': 'lien_date',
    'Lien Amount': 'lien_amount',
}


class PropStreamImporter:
    """Imports PropStream Excel exports into the database."""

    def __init__(self, db_path: str = DB_PATH, dry_run: bool = False):
        self.db_path = db_path
        self.dry_run = dry_run
        self.stats = {
            'rows_processed': 0,
            'rows_imported': 0,
            'rows_updated': 0,
            'rows_skipped': 0,
            'apn_added': 0,
            'owner_added': 0,
            'agent_added': 0,
            'errors': 0,
        }

    def _get_connection(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self, conn):
        """Ensure all PropStream fields exist in schema."""
        cursor = conn.cursor()

        # New columns to add for PropStream data
        new_columns = [
            ('owner_first_name', 'TEXT'),
            ('owner_last_name', 'TEXT'),
            ('owner2_first_name', 'TEXT'),
            ('owner2_last_name', 'TEXT'),
            ('owner_occupied', 'TEXT'),
            ('vacant', 'TEXT'),
            ('owner_mobile', 'TEXT'),
            ('owner_landline', 'TEXT'),
            ('owner_email', 'TEXT'),
            ('mailing_address', 'TEXT'),
            ('mailing_city', 'TEXT'),
            ('mailing_state', 'TEXT'),
            ('mailing_zip', 'TEXT'),
            ('do_not_mail', 'TEXT'),
            ('assessed_value', 'INTEGER'),
            ('last_sale_date', 'TEXT'),
            ('last_sale_amount', 'INTEGER'),
            ('est_value', 'INTEGER'),
            ('est_equity', 'INTEGER'),
            ('est_ltv', 'REAL'),
            ('open_loans', 'INTEGER'),
            ('loan_balance', 'INTEGER'),
            ('condition_total', 'TEXT'),
            ('condition_interior', 'TEXT'),
            ('condition_exterior', 'TEXT'),
            ('stories', 'INTEGER'),
            ('has_hoa', 'TEXT'),
            ('propstream_source', 'TEXT'),
            # Additional PropStream fields
            ('prior_sale_date', 'TEXT'),
            ('prior_sale_amount', 'INTEGER'),
            ('condition_bathroom', 'TEXT'),
            ('condition_kitchen', 'TEXT'),
            ('foreclosure_factor', 'TEXT'),
            ('lien_type', 'TEXT'),
            ('lien_date', 'TEXT'),
            ('lien_amount', 'INTEGER'),
        ]

        # Get existing columns
        cursor.execute("PRAGMA table_info(properties)")
        existing = {row[1] for row in cursor.fetchall()}

        # Add missing columns
        for col_name, col_type in new_columns:
            if col_name not in existing:
                try:
                    cursor.execute(f'ALTER TABLE properties ADD COLUMN {col_name} {col_type}')
                    logger.info(f"Added column: {col_name}")
                except sqlite3.OperationalError:
                    pass  # Column already exists

        conn.commit()

    def _normalize_address(self, address: str, city: str, state: str, zip_code: str) -> str:
        """Create normalized address for matching."""
        addr = str(address or '').strip().upper()
        city = str(city or '').strip().upper()
        state = str(state or 'NC').strip().upper()
        zip_code = str(zip_code or '').strip()[:5]

        # Remove common variations
        addr = re.sub(r'\s+', ' ', addr)
        addr = re.sub(r'\.', '', addr)
        addr = re.sub(r'\bSTREET\b', 'ST', addr)
        addr = re.sub(r'\bROAD\b', 'RD', addr)
        addr = re.sub(r'\bDRIVE\b', 'DR', addr)
        addr = re.sub(r'\bLANE\b', 'LN', addr)
        addr = re.sub(r'\bCIRCLE\b', 'CIR', addr)
        addr = re.sub(r'\bTRAIL\b', 'TRL', addr)

        return f"{addr}, {city}, {state} {zip_code}"

    def _parse_row(self, row: pd.Series) -> Optional[Dict]:
        """Parse a PropStream row into property data."""
        address = row.get('Address')
        if pd.isna(address) or not str(address).strip():
            return None

        data = {}

        # Map PropStream columns to our schema
        for ps_col, our_col in PROPSTREAM_MAP.items():
            value = row.get(ps_col)
            if pd.notna(value):
                # Clean up the value
                if isinstance(value, str):
                    value = value.strip()
                    if value == '':
                        value = None
                elif isinstance(value, float):
                    # Convert numeric columns appropriately
                    if our_col in ['beds', 'baths', 'sqft', 'lot_sqft', 'year_built',
                                   'assessed_value', 'last_sale_amount', 'est_value',
                                   'est_equity', 'loan_balance', 'open_loans', 'stories']:
                        value = int(value) if not pd.isna(value) else None
                data[our_col] = value

        # Calculate acreage from lot_sqft
        if data.get('lot_sqft'):
            data['acreage'] = round(data['lot_sqft'] / 43560, 2)

        # Derive county from ZIP if not provided
        if not data.get('county') or data['county'] == 'Unknown':
            data['county'] = get_county(str(data.get('zip', '')))

        # Create normalized address for matching
        data['full_address'] = self._normalize_address(
            data.get('address', ''),
            data.get('city', ''),
            data.get('state', 'NC'),
            data.get('zip', '')
        )

        # Format dates
        for date_field in ['last_sale_date', 'mls_date', 'prior_sale_date', 'lien_date']:
            if data.get(date_field):
                try:
                    if isinstance(data[date_field], str):
                        # Parse string date
                        data[date_field] = data[date_field][:10]  # Keep YYYY-MM-DD
                    else:
                        # Convert datetime
                        data[date_field] = pd.to_datetime(data[date_field]).strftime('%Y-%m-%d')
                except:
                    pass

        # Parse numeric fields
        for int_field in ['prior_sale_amount', 'lien_amount']:
            if data.get(int_field):
                try:
                    data[int_field] = int(float(data[int_field]))
                except (ValueError, TypeError):
                    data[int_field] = None

        return data

    def _find_existing_property(self, conn, data: Dict) -> Optional[Dict]:
        """Find existing property by APN or address (smart merge logic)."""
        cursor = conn.cursor()

        # 1. Try APN first (most reliable, permanent identifier)
        if data.get('parcel_id'):
            cursor.execute('''
                SELECT id, parcel_id, address, mls_number, sources_json
                FROM properties WHERE parcel_id = ? LIMIT 1
            ''', (data['parcel_id'],))
            row = cursor.fetchone()
            if row:
                return dict(row)

        # 2. Try to find by normalized address
        street_addr = str(data.get('address', '')).strip()
        city = str(data.get('city', '')).strip()

        if street_addr and len(street_addr) > 5:
            cursor.execute('''
                SELECT id, parcel_id, address, mls_number, sources_json
                FROM properties
                WHERE UPPER(address) LIKE UPPER(?)
                AND UPPER(city) = UPPER(?)
                LIMIT 1
            ''', (f"%{street_addr}%", city))
            row = cursor.fetchone()
            if row:
                return dict(row)

        return None

    def _insert_property(self, conn, data: Dict) -> str:
        """Insert new property from PropStream."""
        import json
        prop_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        cursor = conn.cursor()

        # Build full address
        full_addr = f"{data.get('address', '')}, {data.get('city', '')}, {data.get('state', 'NC')} {data.get('zip', '')}"

        cursor.execute('''
            INSERT INTO properties (
                id, address, city, state, zip, county, parcel_id,
                property_type, beds, baths, sqft, acreage, year_built,
                owner_first_name, owner_last_name, owner2_first_name, owner2_last_name,
                owner_occupied, vacant, owner_mobile, owner_landline, owner_email,
                mailing_address, mailing_city, mailing_state, mailing_zip, do_not_mail,
                assessed_value, last_sale_date, last_sale_amount,
                est_value, est_equity, est_ltv, open_loans, loan_balance,
                condition_total, condition_interior, condition_exterior,
                condition_bathroom, condition_kitchen,
                prior_sale_date, prior_sale_amount,
                foreclosure_factor, lien_type, lien_date, lien_amount,
                listing_agent_name, listing_agent_phone, listing_agent_email, listing_brokerage,
                stories, has_hoa, status,
                source, sources_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            prop_id, full_addr, data.get('city'), data.get('state', 'NC'), data.get('zip'),
            data.get('county'), data.get('parcel_id'),
            data.get('property_type'), data.get('beds'), data.get('baths'),
            data.get('sqft'), data.get('acreage'), data.get('year_built'),
            data.get('owner_first_name'), data.get('owner_last_name'),
            data.get('owner2_first_name'), data.get('owner2_last_name'),
            data.get('owner_occupied'), data.get('vacant'),
            data.get('owner_mobile'), data.get('owner_landline'), data.get('owner_email'),
            data.get('mailing_address'), data.get('mailing_city'),
            data.get('mailing_state'), data.get('mailing_zip'), data.get('do_not_mail'),
            data.get('assessed_value'), data.get('last_sale_date'), data.get('last_sale_amount'),
            data.get('est_value'), data.get('est_equity'), data.get('est_ltv'),
            data.get('open_loans'), data.get('loan_balance'),
            data.get('condition_total'), data.get('condition_interior'), data.get('condition_exterior'),
            data.get('condition_bathroom'), data.get('condition_kitchen'),
            data.get('prior_sale_date'), data.get('prior_sale_amount'),
            data.get('foreclosure_factor'), data.get('lien_type'),
            data.get('lien_date'), data.get('lien_amount'),
            data.get('listing_agent_name'), data.get('listing_agent_phone'),
            data.get('listing_agent_email'), data.get('listing_brokerage'),
            data.get('stories'), data.get('has_hoa'), data.get('mls_status'),
            'propstream', json.dumps(['propstream']), now
        ))

        return prop_id

    def _update_sources_json(self, existing_json: Optional[str], new_source: str) -> str:
        """Update sources_json to include new source."""
        import json
        try:
            sources = json.loads(existing_json) if existing_json else []
        except (json.JSONDecodeError, TypeError):
            sources = []
        if new_source and new_source not in sources:
            sources.append(new_source)
        return json.dumps(sources)

    def _update_property(self, conn, existing: Dict, data: Dict):
        """Update existing property with PropStream data."""
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        updates = []
        params = []

        # Fields to update (only if PropStream has data and existing doesn't)
        merge_fields = [
            ('parcel_id', 'parcel_id'),
            ('owner_first_name', 'owner_first_name'),
            ('owner_last_name', 'owner_last_name'),
            ('owner2_first_name', 'owner2_first_name'),
            ('owner2_last_name', 'owner2_last_name'),
            ('owner_occupied', 'owner_occupied'),
            ('vacant', 'vacant'),
            ('owner_mobile', 'owner_mobile'),
            ('owner_landline', 'owner_landline'),
            ('owner_email', 'owner_email'),
            ('mailing_address', 'mailing_address'),
            ('mailing_city', 'mailing_city'),
            ('mailing_state', 'mailing_state'),
            ('mailing_zip', 'mailing_zip'),
            ('assessed_value', 'assessed_value'),
            ('last_sale_date', 'last_sale_date'),
            ('last_sale_amount', 'last_sale_amount'),
            ('est_value', 'est_value'),
            ('est_equity', 'est_equity'),
            ('condition_total', 'condition_total'),
            ('condition_interior', 'condition_interior'),
            ('condition_exterior', 'condition_exterior'),
            ('condition_bathroom', 'condition_bathroom'),
            ('condition_kitchen', 'condition_kitchen'),
            ('prior_sale_date', 'prior_sale_date'),
            ('prior_sale_amount', 'prior_sale_amount'),
            ('foreclosure_factor', 'foreclosure_factor'),
            ('lien_type', 'lien_type'),
            ('lien_date', 'lien_date'),
            ('lien_amount', 'lien_amount'),
            ('stories', 'stories'),
            ('has_hoa', 'has_hoa'),
        ]

        for db_field, data_field in merge_fields:
            new_value = data.get(data_field)
            if new_value is not None:
                existing_value = existing.get(db_field)
                if existing_value is None or existing_value == '':
                    updates.append(f"{db_field} = ?")
                    params.append(new_value)

                    # Track what was added
                    if db_field == 'parcel_id':
                        self.stats['apn_added'] += 1
                    elif db_field.startswith('owner'):
                        self.stats['owner_added'] += 1

        # Always update agent info if PropStream has it (may be more current)
        agent_fields = [
            ('listing_agent_name', 'listing_agent_name'),
            ('listing_agent_phone', 'listing_agent_phone'),
            ('listing_agent_email', 'listing_agent_email'),
            ('listing_brokerage', 'listing_brokerage'),
        ]

        for db_field, data_field in agent_fields:
            new_value = data.get(data_field)
            if new_value is not None:
                existing_value = existing.get(db_field)
                if existing_value is None or existing_value == '':
                    updates.append(f"{db_field} = ?")
                    params.append(new_value)
                    if db_field == 'listing_agent_name':
                        self.stats['agent_added'] += 1

        if updates:
            updates.append("propstream_source = ?")
            params.append('propstream_excel')
            # Update sources_json
            new_sources_json = self._update_sources_json(existing.get('sources_json'), 'propstream')
            updates.append("sources_json = ?")
            params.append(new_sources_json)
            updates.append("updated_at = ?")
            params.append(now)
            params.append(existing['id'])

            query = f"UPDATE properties SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)

    def import_excel(self, file_path: str) -> Dict:
        """Import a PropStream Excel file."""
        logger.info(f"Importing: {file_path}")

        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return self.stats

        try:
            df = pd.read_excel(file_path)
        except Exception as e:
            logger.error(f"Error reading Excel file: {e}")
            return self.stats

        conn = self._get_connection()
        try:
            # Ensure schema has all PropStream fields
            self._ensure_schema(conn)

            for idx, row in df.iterrows():
                self.stats['rows_processed'] += 1

                try:
                    data = self._parse_row(row)
                    if not data:
                        self.stats['rows_skipped'] += 1
                        continue

                    if self.dry_run:
                        logger.info(f"[DRY RUN] Would import: {data.get('address')} (APN: {data.get('parcel_id')})")
                        self.stats['rows_imported'] += 1
                        continue

                    # Check for existing property
                    existing = self._find_existing_property(conn, data)

                    if existing:
                        self._update_property(conn, existing, data)
                        self.stats['rows_updated'] += 1
                        logger.debug(f"Updated: {data.get('address')}")
                    else:
                        self._insert_property(conn, data)
                        self.stats['rows_imported'] += 1
                        logger.debug(f"Inserted: {data.get('address')}")

                except Exception as e:
                    logger.error(f"Error processing row {idx}: {e}")
                    self.stats['errors'] += 1
                    continue

            if not self.dry_run:
                conn.commit()
                logger.info("Changes committed to database")

        finally:
            conn.close()

        return self.stats

    def import_multiple(self, file_paths: List[str]) -> Dict:
        """Import multiple Excel files."""
        for path in file_paths:
            self.import_excel(path)
        return self.stats


def main():
    parser = argparse.ArgumentParser(description='Import PropStream Excel files')
    parser.add_argument('files', nargs='+', help='Excel file(s) to import')
    parser.add_argument('--dry-run', action='store_true', help='Parse but do not import')
    parser.add_argument('--db', default=DB_PATH, help='Database path')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    importer = PropStreamImporter(db_path=args.db, dry_run=args.dry_run)

    # Handle glob patterns
    all_files = []
    for pattern in args.files:
        matches = glob.glob(pattern)
        if matches:
            all_files.extend(matches)
        else:
            all_files.append(pattern)

    stats = importer.import_multiple(all_files)

    print("\n" + "=" * 50)
    print("PROPSTREAM IMPORT SUMMARY")
    print("=" * 50)
    print(f"Rows processed:  {stats['rows_processed']}")
    print(f"Rows imported:   {stats['rows_imported']}")
    print(f"Rows updated:    {stats['rows_updated']}")
    print(f"Rows skipped:    {stats['rows_skipped']}")
    print(f"APNs added:      {stats['apn_added']}")
    print(f"Owner info added:{stats['owner_added']}")
    print(f"Agent info added:{stats['agent_added']}")
    print(f"Errors:          {stats['errors']}")
    print("=" * 50)

    if args.dry_run:
        print("\n[DRY RUN - No changes made]")


if __name__ == '__main__':
    main()
