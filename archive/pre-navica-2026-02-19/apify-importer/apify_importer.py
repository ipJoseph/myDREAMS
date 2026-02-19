#!/usr/bin/env python3
"""
Apify Redfin Importer

Fetches property listings from Redfin via the tri_angle/redfin-search Apify actor
and updates the dreams.db database. Tracks price and status changes.

Usage:
    # Import all WNC counties
    python apify_importer.py --all-counties

    # Import specific county
    python apify_importer.py --county Buncombe

    # Dry run (no database changes)
    python apify_importer.py --county Buncombe --dry-run

    # Limit results per county
    python apify_importer.py --all-counties --max-items 100
"""

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import APIFY_TOKEN, DB_PATH, WNC_COUNTIES

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ApifyRedfin:
    """Client for running Redfin scraper on Apify."""

    ACTOR_ID = 'tri_angle~redfin-search'
    BASE_URL = 'https://api.apify.com/v2'

    def __init__(self, token: str):
        self.token = token
        self.headers = {'Authorization': f'Bearer {token}'}

    def scrape_county(self, county: str, max_items: int = 500,
                      wait_secs: int = 600) -> List[dict]:
        """Scrape properties for a WNC county."""
        county_info = WNC_COUNTIES.get(county)
        if not county_info:
            logger.error(f"Unknown county: {county}")
            return []

        # Build Redfin search URL for the county
        # Format: https://www.redfin.com/county/{region_id}/NC/{County}-County
        search_url = f"https://www.redfin.com/county/{county_info['redfin_region']}/NC/{county}-County"

        input_data = {
            'searchUrls': [{'url': search_url}],
            'maxItems': max_items,
        }

        logger.info(f"Scraping {county} County (max {max_items} items)...")

        # Start actor run
        url = f"{self.BASE_URL}/acts/{self.ACTOR_ID}/runs"
        response = requests.post(url, json=input_data, headers=self.headers)

        if response.status_code != 201:
            logger.error(f"Failed to start actor: {response.text}")
            return []

        run_data = response.json()['data']
        run_id = run_data['id']
        logger.info(f"Actor run started: {run_id}")

        # Wait for completion
        status_url = f"{self.BASE_URL}/actor-runs/{run_id}"
        start_time = time.time()

        while time.time() - start_time < wait_secs:
            response = requests.get(status_url, headers=self.headers)
            status = response.json()['data']['status']

            if status == 'SUCCEEDED':
                logger.info(f"Actor run completed successfully")
                break
            elif status in ['FAILED', 'ABORTED', 'TIMED-OUT']:
                logger.error(f"Actor run failed with status: {status}")
                return []

            time.sleep(10)
        else:
            logger.error(f"Actor run timed out after {wait_secs}s")
            return []

        # Get results
        dataset_id = run_data['defaultDatasetId']
        dataset_url = f"{self.BASE_URL}/datasets/{dataset_id}/items"
        response = requests.get(dataset_url, headers=self.headers)

        results = response.json()
        logger.info(f"Retrieved {len(results)} properties from {county} County")

        return results


class RedfimImporter:
    """Imports Redfin data from Apify into dreams.db."""

    def __init__(self, db_path: str = DB_PATH, dry_run: bool = False):
        self.db_path = db_path
        self.dry_run = dry_run
        self.stats = {
            'properties_fetched': 0,
            'properties_inserted': 0,
            'properties_updated': 0,
            'properties_unchanged': 0,
            'price_changes': 0,
            'status_changes': 0,
            'listings_delisted': 0,
            'errors': 0,
        }

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _extract_value(self, data: dict, *keys) -> any:
        """Extract value from nested dict structure.

        Redfin returns data like: {"price": {"value": 500000, "level": 1}}
        This extracts the actual value.
        """
        for key in keys:
            val = data.get(key)
            if val is not None:
                if isinstance(val, dict):
                    return val.get('value')
                return val
        return None

    def _parse_property(self, raw: dict) -> Optional[Dict]:
        """Parse raw Redfin scraper data into our schema."""
        # Extract address
        address = self._extract_value(raw, 'streetLine')
        if not address:
            return None

        city = raw.get('city', '')
        state = raw.get('state', '')
        zip_code = raw.get('zip', '')

        # Only process NC properties
        if state and state.upper() != 'NC':
            return None

        # Extract numeric values from nested dicts
        price = self._extract_value(raw, 'price')
        sqft = self._extract_value(raw, 'sqFt')
        lot_sqft = self._extract_value(raw, 'lotSize')
        year_built = self._extract_value(raw, 'yearBuilt')
        dom = self._extract_value(raw, 'dom')
        mls_id = self._extract_value(raw, 'mlsId')

        # Get lat/long
        lat_long = raw.get('latLong', {})
        if isinstance(lat_long, dict):
            lat_long_val = lat_long.get('value', {})
            latitude = lat_long_val.get('latitude') if isinstance(lat_long_val, dict) else None
            longitude = lat_long_val.get('longitude') if isinstance(lat_long_val, dict) else None
        else:
            latitude = longitude = None

        # Calculate acreage from lot sqft
        acreage = round(lot_sqft / 43560, 2) if lot_sqft else None

        # Map status
        status_raw = raw.get('mlsStatus', 'Active')
        status_map = {
            'Active': 'ACTIVE',
            'Pending': 'PENDING',
            'Contingent': 'CONTINGENT',
            'Sold': 'SOLD',
            'Coming Soon': 'COMING_SOON',
        }
        status = status_map.get(status_raw, status_raw.upper() if status_raw else 'ACTIVE')

        # Build full address
        full_address = f"{address}, {city}, {state} {zip_code}".strip(', ')

        return {
            'address': full_address,
            'street': address,
            'city': city,
            'state': state or 'NC',
            'zip': zip_code,
            'price': int(price) if price else None,
            'beds': raw.get('beds'),
            'baths': raw.get('baths'),
            'sqft': int(sqft) if sqft else None,
            'acreage': acreage,
            'year_built': int(year_built) if year_built else None,
            'status': status,
            'days_on_market': int(dom) if dom else None,
            'mls_number': str(mls_id) if mls_id else None,
            'redfin_id': str(raw.get('propertyId')) if raw.get('propertyId') else None,
            'redfin_url': raw.get('url'),
            'latitude': latitude,
            'longitude': longitude,
            'primary_photo': raw.get('url'),  # Redfin doesn't return photo URLs in search
            'property_type': self._map_property_type(raw.get('propertyType')),
            'listing_remarks': raw.get('listingRemarks'),
        }

    def _map_property_type(self, type_code: int) -> str:
        """Map Redfin property type code to string."""
        type_map = {
            1: 'House',
            2: 'Condo',
            3: 'Townhouse',
            4: 'Multi-Family',
            5: 'Land',
            6: 'Other',
        }
        return type_map.get(type_code, 'House')

    def _normalize_address(self, address: str) -> str:
        """Normalize address for matching."""
        addr = address.upper().strip()
        # Remove punctuation
        addr = re.sub(r'[.,#]', '', addr)
        # Standardize common abbreviations
        replacements = [
            (r'\bSTREET\b', 'ST'),
            (r'\bROAD\b', 'RD'),
            (r'\bDRIVE\b', 'DR'),
            (r'\bLANE\b', 'LN'),
            (r'\bCOURT\b', 'CT'),
            (r'\bCIRCLE\b', 'CIR'),
            (r'\bTRAIL\b', 'TRL'),
            (r'\bAVENUE\b', 'AVE'),
            (r'\bBOULEVARD\b', 'BLVD'),
            (r'\bPLACE\b', 'PL'),
            (r'\bNORTH\b', 'N'),
            (r'\bSOUTH\b', 'S'),
            (r'\bEAST\b', 'E'),
            (r'\bWEST\b', 'W'),
        ]
        for pattern, replacement in replacements:
            addr = re.sub(pattern, replacement, addr)
        # Collapse whitespace
        addr = re.sub(r'\s+', ' ', addr)
        return addr

    def _find_existing(self, conn, data: Dict) -> Optional[Dict]:
        """Find existing property, prioritizing redfin_id.

        Matching priority:
        1. redfin_id - Unique Redfin property identifier (guaranteed unique)
        2. MLS number - Only for records that don't have a redfin_id yet
           (legacy imports before we had redfin_id)
        """
        cursor = conn.cursor()

        # PRIMARY: Match by redfin_id (guaranteed unique per Redfin property)
        if data.get('redfin_id'):
            cursor.execute(
                'SELECT * FROM properties WHERE redfin_id = ?',
                (data['redfin_id'],)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)

        # SECONDARY: Match by MLS number (for properties imported before we had redfin_id)
        if data.get('mls_number'):
            cursor.execute(
                'SELECT * FROM properties WHERE mls_number = ? AND redfin_id IS NULL',
                (data['mls_number'],)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)

        # No match - this is a new property
        return None

    def _log_change(self, conn, property_id: str, address: str,
                    change_type: str, old_value: any, new_value: any):
        """Log a property change."""
        cursor = conn.cursor()

        change_amount = None
        if change_type == 'price' and old_value and new_value:
            try:
                change_amount = int(new_value) - int(old_value)
            except (ValueError, TypeError):
                pass

        cursor.execute('''
            INSERT INTO property_changes (
                id, property_id, property_address, change_type,
                old_value, new_value, change_amount, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            str(uuid.uuid4()),
            property_id,
            address,
            change_type,
            str(old_value) if old_value else None,
            str(new_value) if new_value else None,
            change_amount,
            'redfin'
        ))

        logger.info(f"Change detected: {address} - {change_type}: {old_value} -> {new_value}")

    def _update_property(self, conn, existing: Dict, data: Dict):
        """Update existing property and track changes."""
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        changes = []

        # Check for price change
        old_price = existing.get('price')
        new_price = data.get('price')
        if old_price and new_price and old_price != new_price:
            self._log_change(conn, existing['id'], data['address'],
                           'price', old_price, new_price)
            self.stats['price_changes'] += 1
            changes.append('price')

        # Check for status change
        old_status = existing.get('status')
        new_status = data.get('status')
        if old_status and new_status and old_status != new_status:
            self._log_change(conn, existing['id'], data['address'],
                           'status', old_status, new_status)
            self.stats['status_changes'] += 1
            changes.append('status')

        # Clear delisted_at if property reappears in feed
        if existing.get('delisted_at'):
            changes.append('relisted')

        # Update fields
        update_fields = [
            'price', 'status', 'beds', 'baths', 'sqft', 'acreage',
            'year_built', 'days_on_market', 'latitude', 'longitude',
            'redfin_id', 'redfin_url', 'mls_number'
        ]

        updates = []
        params = []

        for field in update_fields:
            new_val = data.get(field)
            if new_val is not None:
                updates.append(f"{field} = ?")
                params.append(new_val)

        if updates:
            updates.append("updated_at = ?")
            params.append(now)
            updates.append("source = ?")
            params.append('redfin')
            # Track when we last saw this listing in the feed
            updates.append("listing_last_seen_at = ?")
            params.append(now)
            # Clear delisted_at if property reappears
            updates.append("delisted_at = ?")
            params.append(None)
            params.append(existing['id'])

            query = f"UPDATE properties SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)

        return len(changes) > 0

    def _insert_property(self, conn, data: Dict) -> str:
        """Insert new property with provenance tracking."""
        cursor = conn.cursor()
        prop_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute('''
            INSERT INTO properties (
                id, address, city, state, zip, price, beds, baths,
                sqft, acreage, year_built, status, days_on_market,
                mls_number, redfin_id, redfin_url, latitude, longitude,
                property_type, source, created_at, updated_at,
                first_seen_at, first_seen_source, listing_last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            prop_id, data['address'], data['city'], data['state'], data['zip'],
            data['price'], data['beds'], data['baths'],
            data['sqft'], data['acreage'], data['year_built'],
            data['status'], data['days_on_market'],
            data['mls_number'], data['redfin_id'], data['redfin_url'],
            data['latitude'], data['longitude'],
            data['property_type'], 'redfin', now, now,
            now, 'redfin', now  # first_seen_at, first_seen_source, listing_last_seen_at
        ))

        return prop_id

    def _get_county_from_zip(self, zip_code: str) -> Optional[str]:
        """Get county name from ZIP code."""
        try:
            from wnc_zip_county import get_county
            return get_county(zip_code)
        except ImportError:
            return None

    def mark_stale_listings(self, conn, max_days: int = 3) -> int:
        """Mark listings not seen in recent imports as potentially delisted.

        Properties that haven't appeared in a Redfin feed for `max_days` days
        are assumed to be off-market (sold, withdrawn, or expired).

        Args:
            conn: Database connection
            max_days: Days of absence before marking as delisted (default 3)

        Returns:
            Number of listings marked as OFF_MARKET
        """
        cursor = conn.cursor()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_days)).isoformat()

        cursor.execute('''
            UPDATE properties
            SET delisted_at = CURRENT_TIMESTAMP,
                status = 'OFF_MARKET'
            WHERE source = 'redfin'
              AND listing_last_seen_at < ?
              AND delisted_at IS NULL
              AND status IN ('ACTIVE', 'COMING_SOON', 'CONTINGENT', 'PENDING')
        ''', (cutoff,))

        count = cursor.rowcount
        if count > 0:
            logger.info(f"Marked {count} stale listings as OFF_MARKET")
        return count

    def import_properties(self, raw_properties: List[dict], county: str = None) -> Dict:
        """Import properties from raw Apify results."""
        conn = self._get_connection()

        try:
            for raw in raw_properties:
                self.stats['properties_fetched'] += 1

                try:
                    data = self._parse_property(raw)
                    if not data:
                        continue

                    # Add county if provided
                    if county:
                        data['county'] = county
                    elif data.get('zip'):
                        data['county'] = self._get_county_from_zip(data['zip'])

                    if self.dry_run:
                        logger.debug(f"[DRY RUN] Would process: {data['address']}")
                        continue

                    existing = self._find_existing(conn, data)

                    if existing:
                        changed = self._update_property(conn, existing, data)
                        if changed:
                            self.stats['properties_updated'] += 1
                        else:
                            self.stats['properties_unchanged'] += 1
                    else:
                        self._insert_property(conn, data)
                        self.stats['properties_inserted'] += 1
                        logger.debug(f"Inserted: {data['address']}")

                except Exception as e:
                    logger.error(f"Error processing property: {e}")
                    self.stats['errors'] += 1

            if not self.dry_run:
                conn.commit()
                logger.info("Changes committed to database")

                # After committing updates, check for stale listings
                stale_count = self.mark_stale_listings(conn)
                self.stats['listings_delisted'] = stale_count
                if stale_count > 0:
                    conn.commit()

        finally:
            conn.close()

        return self.stats


def main():
    parser = argparse.ArgumentParser(description='Import Redfin data via Apify')
    parser.add_argument('--county', type=str, help='Specific county to import')
    parser.add_argument('--all-counties', action='store_true', help='Import all WNC counties')
    parser.add_argument('--max-items', type=int, default=500,
                       help='Max properties per county (default 500)')
    parser.add_argument('--dry-run', action='store_true', help='Parse but do not import')
    parser.add_argument('--db', default=DB_PATH, help='Database path')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not APIFY_TOKEN:
        logger.error("APIFY_TOKEN not set. Add to .env or set environment variable.")
        sys.exit(1)

    # Determine which counties to scrape
    if args.all_counties:
        counties = list(WNC_COUNTIES.keys())
    elif args.county:
        counties = [args.county]
    else:
        parser.print_help()
        print("\nSpecify --county NAME or --all-counties")
        sys.exit(1)

    # Initialize clients
    apify = ApifyRedfin(APIFY_TOKEN)
    importer = RedfimImporter(db_path=args.db, dry_run=args.dry_run)

    # Process each county
    total_stats = {
        'properties_fetched': 0,
        'properties_inserted': 0,
        'properties_updated': 0,
        'properties_unchanged': 0,
        'price_changes': 0,
        'status_changes': 0,
        'listings_delisted': 0,
        'errors': 0,
    }

    for county in counties:
        print(f"\n{'='*60}")
        print(f"Processing: {county} County")
        print('='*60)

        # Scrape from Apify
        raw_properties = apify.scrape_county(county, max_items=args.max_items)

        if raw_properties:
            # Import to database
            stats = importer.import_properties(raw_properties, county=county)

            # Accumulate stats
            for key in total_stats:
                total_stats[key] += stats.get(key, 0)
        else:
            logger.warning(f"No properties retrieved for {county} County")

    # Print summary
    print("\n" + "="*60)
    print("APIFY REDFIN IMPORT SUMMARY")
    print("="*60)
    print(f"Counties processed:    {len(counties)}")
    print(f"Properties fetched:    {total_stats['properties_fetched']}")
    print(f"Properties inserted:   {total_stats['properties_inserted']}")
    print(f"Properties updated:    {total_stats['properties_updated']}")
    print(f"Properties unchanged:  {total_stats['properties_unchanged']}")
    print(f"Price changes:         {total_stats['price_changes']}")
    print(f"Status changes:        {total_stats['status_changes']}")
    print(f"Listings delisted:     {total_stats['listings_delisted']}")
    print(f"Errors:                {total_stats['errors']}")
    print("="*60)

    if args.dry_run:
        print("\n[DRY RUN - No changes made]")


if __name__ == '__main__':
    main()
