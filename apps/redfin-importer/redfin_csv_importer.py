#!/usr/bin/env python3
"""
Redfin CSV Importer

Imports properties from Redfin CSV export files into the DREAMS SQLite database.
Handles:
- Core field extraction (11 fields from CSV)
- County derivation from ZIP code
- Deduplication by address (merges MLS numbers)
- Queuing URLs for page scraping (agent info, engagement)

Usage:
    python redfin_csv_importer.py ~/Downloads/redfin_macon_county.csv
    python redfin_csv_importer.py ~/Downloads/*.csv --dry-run
"""

import argparse
import csv
import logging
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from wnc_zip_county import get_county

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database path
DB_PATH = os.getenv('REDFIN_DB_PATH', str(PROJECT_ROOT / 'data' / 'redfin_imports.db'))


class RedfinCSVImporter:
    """Imports Redfin CSV files into DREAMS database."""

    # Mapping: Redfin CSV column → our field name
    COLUMN_MAP = {
        'ADDRESS': 'address',
        'CITY': 'city',
        'STATE OR PROVINCE': 'state',
        'ZIP OR POSTAL CODE': 'zip',
        'PRICE': 'price',
        'BEDS': 'beds',
        'BATHS': 'baths',
        'SQUARE FEET': 'sqft',
        'LOT SIZE': 'lot_sqft',
        'YEAR BUILT': 'year_built',
        'PROPERTY TYPE': 'property_type',
        'DAYS ON MARKET': 'days_on_market',
        'STATUS': 'status',
        'HOA/MONTH': 'hoa_fee',
        'MLS#': 'mls_number',
        'SOURCE': 'mls_source',
        'URL (SEE https://www.redfin.com/buy-a-home/comparative-market-analysis FOR INFO ON PRICING)': 'redfin_url',
        'LATITUDE': 'latitude',
        'LONGITUDE': 'longitude',
        'LOCATION': 'subdivision',
        '$/SQUARE FEET': 'price_per_sqft',
    }

    def __init__(self, db_path: str = DB_PATH, dry_run: bool = False):
        self.db_path = db_path
        self.dry_run = dry_run
        self.stats = {
            'rows_processed': 0,
            'rows_imported': 0,
            'rows_updated': 0,
            'rows_skipped': 0,
            'mls_merged': 0,
            'errors': 0,
        }

    def _get_connection(self):
        """Get database connection."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _normalize_address(self, address: str, city: str, state: str, zip_code: str) -> str:
        """Create normalized full address for deduplication."""
        # Clean components
        addr = (address or '').strip()
        city = (city or '').strip()
        state = (state or 'NC').strip().upper()
        zip_code = (zip_code or '').strip()[:5]

        return f"{addr}, {city}, {state} {zip_code}"

    def _parse_price(self, value: str) -> Optional[int]:
        """Parse price string to integer."""
        if not value:
            return None
        try:
            # Remove $, commas, etc.
            clean = ''.join(c for c in str(value) if c.isdigit())
            return int(clean) if clean else None
        except (ValueError, TypeError):
            return None

    def _parse_float(self, value: str) -> Optional[float]:
        """Parse string to float."""
        if not value:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _parse_int(self, value: str) -> Optional[int]:
        """Parse string to int."""
        if not value:
            return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None

    def _parse_row(self, row: Dict) -> Optional[Dict]:
        """Parse a CSV row into property data."""
        # Skip header row or disclaimer rows
        address = row.get('ADDRESS', '')
        if not address or address.startswith('In accordance') or address == 'ADDRESS':
            return None

        # Extract and transform fields
        data = {
            'address': address.strip(),
            'city': row.get('CITY', '').strip(),
            'state': row.get('STATE OR PROVINCE', 'NC').strip() or 'NC',
            'zip': row.get('ZIP OR POSTAL CODE', '').strip()[:5],
            'price': self._parse_price(row.get('PRICE')),
            'beds': self._parse_int(row.get('BEDS')),
            'baths': self._parse_float(row.get('BATHS')),
            'sqft': self._parse_int(row.get('SQUARE FEET')),
            'acreage': None,  # Calculate from lot size
            'year_built': self._parse_int(row.get('YEAR BUILT')),
            'property_type': row.get('PROPERTY TYPE', '').strip(),
            'days_on_market': self._parse_int(row.get('DAYS ON MARKET')),
            'status': self._normalize_status(row.get('STATUS', '')),
            'hoa_fee': self._parse_int(row.get('HOA/MONTH')),
            'mls_number': row.get('MLS#', '').strip(),
            'mls_source': row.get('SOURCE', '').strip(),
            'redfin_url': row.get('URL (SEE https://www.redfin.com/buy-a-home/comparative-market-analysis FOR INFO ON PRICING)', '').strip(),
            'latitude': self._parse_float(row.get('LATITUDE')),
            'longitude': self._parse_float(row.get('LONGITUDE')),
            'subdivision': row.get('LOCATION', '').strip(),
        }

        # Calculate acreage from lot size (sqft to acres)
        lot_sqft = self._parse_int(row.get('LOT SIZE'))
        if lot_sqft:
            data['acreage'] = round(lot_sqft / 43560, 2)

        # Derive county from ZIP
        data['county'] = get_county(data['zip'])

        # Create full address for matching
        data['full_address'] = self._normalize_address(
            data['address'], data['city'], data['state'], data['zip']
        )

        return data

    def _normalize_status(self, status: str) -> str:
        """Normalize status values."""
        status = (status or '').strip().lower()
        status_map = {
            'active': 'Active',
            'for sale': 'Active',
            'pending': 'Pending',
            'contingent': 'Contingent',
            'sold': 'Sold',
            'off market': 'Off Market',
            'coming soon': 'Coming Soon',
        }
        return status_map.get(status, status.title() if status else 'Unknown')

    def _find_existing_property(self, conn, data: Dict) -> Optional[Dict]:
        """Find existing property by address or MLS number."""
        cursor = conn.cursor()

        # Try to find by normalized address (street portion)
        street_addr = data['address']
        cursor.execute('''
            SELECT * FROM properties
            WHERE address LIKE ?
            LIMIT 1
        ''', (f"{street_addr}%",))
        row = cursor.fetchone()
        if row:
            return dict(row)

        # Try to find by MLS number
        if data['mls_number']:
            cursor.execute('''
                SELECT * FROM properties
                WHERE mls_number = ? OR original_mls_number = ?
                LIMIT 1
            ''', (data['mls_number'], data['mls_number']))
            row = cursor.fetchone()
            if row:
                return dict(row)

        return None

    def _insert_property(self, conn, data: Dict) -> str:
        """Insert new property, return ID."""
        prop_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO properties (
                id, address, city, state, zip, county, price, beds, baths, sqft,
                acreage, year_built, property_type, days_on_market, status,
                hoa_fee, mls_number, mls_source, redfin_url, latitude, longitude,
                subdivision, source, created_at, updated_at, sync_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            prop_id, data['full_address'], data['city'], data['state'], data['zip'],
            data['county'], data['price'], data['beds'], data['baths'], data['sqft'],
            data['acreage'], data['year_built'], data['property_type'],
            data['days_on_market'], data['status'], data['hoa_fee'],
            data['mls_number'], data['mls_source'], data['redfin_url'],
            data['latitude'], data['longitude'], data['subdivision'],
            'redfin_csv', now, now, 'pending'
        ))

        return prop_id

    def _update_property(self, conn, existing: Dict, data: Dict) -> bool:
        """Update existing property with new data. Returns True if MLS was merged."""
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        mls_merged = False

        # Check if we need to merge MLS numbers
        existing_mls = existing.get('mls_number', '')
        new_mls = data['mls_number']

        if new_mls and existing_mls and new_mls != existing_mls:
            # Different MLS numbers - store both
            # Keep original as primary, store new one in notes or secondary field
            logger.info(f"Merging MLS: {existing_mls} + {new_mls} for {data['address']}")
            mls_merged = True
            # Store in original_mls_number if not already set
            if not existing.get('original_mls_number'):
                cursor.execute('''
                    UPDATE properties SET original_mls_number = ? WHERE id = ?
                ''', (new_mls, existing['id']))

        # Update fields that might have changed
        cursor.execute('''
            UPDATE properties SET
                price = COALESCE(?, price),
                days_on_market = COALESCE(?, days_on_market),
                status = COALESCE(?, status),
                latitude = COALESCE(?, latitude),
                longitude = COALESCE(?, longitude),
                mls_source = COALESCE(?, mls_source),
                redfin_url = COALESCE(?, redfin_url),
                subdivision = COALESCE(?, subdivision),
                county = COALESCE(?, county),
                updated_at = ?
            WHERE id = ?
        ''', (
            data['price'], data['days_on_market'], data['status'],
            data['latitude'], data['longitude'], data['mls_source'],
            data['redfin_url'], data['subdivision'], data['county'],
            now, existing['id']
        ))

        return mls_merged

    def _queue_for_scraping(self, conn, prop_id: str, url: str):
        """Queue URL for page scraping (agent info, engagement)."""
        # Create scrape queue table if not exists
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS redfin_scrape_queue (
                id TEXT PRIMARY KEY,
                property_id TEXT NOT NULL,
                url TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                scraped_at TEXT,
                error TEXT,
                FOREIGN KEY (property_id) REFERENCES properties(id)
            )
        ''')

        # Add to queue if not already there
        cursor.execute('''
            INSERT OR IGNORE INTO redfin_scrape_queue (id, property_id, url, status, created_at)
            VALUES (?, ?, ?, 'pending', ?)
        ''', (str(uuid.uuid4()), prop_id, url, datetime.utcnow().isoformat()))

    def import_csv(self, csv_path: str) -> Dict:
        """Import a single CSV file."""
        logger.info(f"Importing: {csv_path}")

        if not os.path.exists(csv_path):
            logger.error(f"File not found: {csv_path}")
            return self.stats

        with open(csv_path, 'r', encoding='utf-8') as f:
            # Redfin CSV has a disclaimer as first row, skip it
            reader = csv.DictReader(f)

            conn = self._get_connection()
            try:
                for row in reader:
                    self.stats['rows_processed'] += 1

                    try:
                        data = self._parse_row(row)
                        if not data:
                            self.stats['rows_skipped'] += 1
                            continue

                        if self.dry_run:
                            logger.info(f"[DRY RUN] Would import: {data['full_address']} (MLS: {data['mls_number']})")
                            self.stats['rows_imported'] += 1
                            continue

                        # Check for existing
                        existing = self._find_existing_property(conn, data)

                        if existing:
                            mls_merged = self._update_property(conn, existing, data)
                            self.stats['rows_updated'] += 1
                            if mls_merged:
                                self.stats['mls_merged'] += 1
                            prop_id = existing['id']
                            logger.debug(f"Updated: {data['full_address']}")
                        else:
                            prop_id = self._insert_property(conn, data)
                            self.stats['rows_imported'] += 1
                            logger.debug(f"Inserted: {data['full_address']}")

                        # Queue for scraping if we have a URL
                        if data['redfin_url']:
                            self._queue_for_scraping(conn, prop_id, data['redfin_url'])

                    except Exception as e:
                        logger.error(f"Error processing row: {e}")
                        self.stats['errors'] += 1
                        continue

                if not self.dry_run:
                    conn.commit()
                    logger.info("Changes committed to database")

            finally:
                conn.close()

        return self.stats

    def import_multiple(self, csv_paths: List[str]) -> Dict:
        """Import multiple CSV files."""
        for path in csv_paths:
            self.import_csv(path)
        return self.stats


def main():
    parser = argparse.ArgumentParser(description='Import Redfin CSV files into DREAMS database')
    parser.add_argument('files', nargs='+', help='CSV file(s) to import')
    parser.add_argument('--dry-run', action='store_true', help='Parse but do not import')
    parser.add_argument('--db', default=DB_PATH, help='Database path')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    importer = RedfinCSVImporter(db_path=args.db, dry_run=args.dry_run)

    # Handle glob patterns
    import glob
    all_files = []
    for pattern in args.files:
        matches = glob.glob(pattern)
        if matches:
            all_files.extend(matches)
        else:
            all_files.append(pattern)

    stats = importer.import_multiple(all_files)

    print("\n" + "=" * 50)
    print("IMPORT SUMMARY")
    print("=" * 50)
    print(f"Rows processed:  {stats['rows_processed']}")
    print(f"Rows imported:   {stats['rows_imported']}")
    print(f"Rows updated:    {stats['rows_updated']}")
    print(f"Rows skipped:    {stats['rows_skipped']}")
    print(f"MLS merged:      {stats['mls_merged']}")
    print(f"Errors:          {stats['errors']}")
    print("=" * 50)

    if args.dry_run:
        print("\n[DRY RUN - No changes made]")


if __name__ == '__main__':
    main()
