#!/usr/bin/env python3
"""
NC OneMap Parcel Enricher

Uses the free NC OneMap ArcGIS REST API to enrich property records with:
- APN (Parcel ID)
- Owner Name
- Mailing Address
- Assessed Values (Land, Building, Total)
- Deed Book/Page
- Sale Date/Price
- Acreage

API Endpoint: https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/FeatureServer/1/query

Usage:
    python nc_onemap_enricher.py --test 35.1826 -83.3914  # Test single lat/long
    python nc_onemap_enricher.py --enrich-all             # Enrich all properties missing APN
    python nc_onemap_enricher.py --county Macon           # Enrich properties in specific county
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import requests

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database path - use redfin_imports.db
DB_PATH = os.getenv('REDFIN_DB_PATH', str(PROJECT_ROOT / 'data' / 'redfin_imports.db'))

# NC OneMap API endpoint (MapServer layer 1 = polygons)
ONEMAP_URL = "https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/MapServer/1/query"


class NCOneMapEnricher:
    """Enriches property records with NC OneMap parcel data."""

    # Fields we want from NC OneMap (lowercase as returned by API)
    ONEMAP_FIELDS = [
        'parno',           # Parcel Number (APN)
        'altparno',        # Alternate Parcel Number
        'ownname',         # Owner Name
        'ownname2',        # Second Owner Name
        'ownfrst',         # Owner First Name
        'ownlast',         # Owner Last Name
        'mailadd',         # Mailing Address
        'mcity',           # Mailing City
        'mstate',          # Mailing State
        'mzip',            # Mailing ZIP
        'siteadd',         # Site Address
        'scity',           # Site City
        'sstate',          # Site State
        'szip',            # Site ZIP
        'gisacres',        # GIS Acres
        'landval',         # Land Value
        'improvval',       # Improved/Building Value
        'parval',          # Total Parcel Value
        'legdecfull',      # Full Legal Description
        'saledate',        # Last Sale Date
        'saledatetx',      # Last Sale Date Text
        'structyear',      # Structure Year
        'struct',          # Structure Indicator
        'subdivisio',      # Subdivision Name
        'cntyname',        # County Name
        'parusedesc',      # Tax Parcel Use Description
    ]

    # Mapping: OneMap field → our database field
    FIELD_MAP = {
        'parno': 'parcel_id',
        'altparno': 'alt_parcel_id',
        'ownname': 'owner_name',
        'ownname2': 'owner_name_2',
        'mailadd': 'owner_mailing_address',
        'mcity': 'owner_mailing_city',
        'mstate': 'owner_mailing_state',
        'mzip': 'owner_mailing_zip',
        'gisacres': 'parcel_acreage',
        'landval': 'assessed_land_value',
        'improvval': 'assessed_building_value',
        'parval': 'assessed_total_value',
        'legdecfull': 'legal_description',
        'saledate': 'last_sale_date',
        'saledatetx': 'last_sale_date_text',
        'structyear': 'year_built_onemap',
        'subdivisio': 'subdivision_onemap',
        'cntyname': 'county_onemap',
        'parusedesc': 'land_use_description',
    }

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.session = requests.Session()
        self.stats = {
            'queried': 0,
            'enriched': 0,
            'not_found': 0,
            'errors': 0,
        }

    def _get_connection(self):
        """Get database connection."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_columns(self, conn):
        """Ensure all enrichment columns exist in properties table."""
        cursor = conn.cursor()

        # Get existing columns
        cursor.execute("PRAGMA table_info(properties)")
        existing = {row['name'] for row in cursor.fetchall()}

        # Add missing columns
        new_columns = {
            'parcel_id': 'TEXT',
            'alt_parcel_id': 'TEXT',
            'owner_name': 'TEXT',
            'owner_name_2': 'TEXT',
            'owner_mailing_address': 'TEXT',
            'owner_mailing_city': 'TEXT',
            'owner_mailing_state': 'TEXT',
            'owner_mailing_zip': 'TEXT',
            'parcel_acreage': 'REAL',
            'assessed_land_value': 'INTEGER',
            'assessed_building_value': 'INTEGER',
            'assessed_total_value': 'INTEGER',
            'legal_description': 'TEXT',
            'last_sale_date': 'TEXT',
            'last_sale_date_text': 'TEXT',
            'year_built_onemap': 'INTEGER',
            'subdivision_onemap': 'TEXT',
            'county_onemap': 'TEXT',
            'land_use_description': 'TEXT',
            'onemap_enriched_at': 'TEXT',
        }

        for col, col_type in new_columns.items():
            if col not in existing:
                cursor.execute(f'ALTER TABLE properties ADD COLUMN {col} {col_type}')
                logger.info(f"Added column: {col}")

        conn.commit()

    def query_by_point(self, lat: float, lon: float) -> Optional[Dict]:
        """Query NC OneMap for parcel at given lat/long point."""
        self.stats['queried'] += 1

        # ArcGIS REST API query - geometry is a point
        params = {
            'where': '1=1',
            'geometry': f'{lon},{lat}',
            'geometryType': 'esriGeometryPoint',
            'inSR': '4326',  # WGS84 (standard lat/long)
            'spatialRel': 'esriSpatialRelIntersects',
            'outFields': ','.join(self.ONEMAP_FIELDS),
            'returnGeometry': 'false',
            'f': 'json',
        }

        try:
            response = self.session.get(ONEMAP_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if 'features' in data and len(data['features']) > 0:
                attrs = data['features'][0]['attributes']
                return self._map_fields(attrs)
            else:
                logger.debug(f"No parcel found at {lat}, {lon}")
                self.stats['not_found'] += 1
                return None

        except Exception as e:
            logger.error(f"Error querying NC OneMap: {e}")
            self.stats['errors'] += 1
            return None

    def _map_fields(self, attrs: Dict) -> Dict:
        """Map NC OneMap fields to our database fields."""
        result = {}

        for onemap_field, our_field in self.FIELD_MAP.items():
            value = attrs.get(onemap_field)
            if value is not None and value != '':
                # Clean up string values
                if isinstance(value, str):
                    value = value.strip()
                result[our_field] = value

        return result

    def enrich_property(self, conn, property_id: str, lat: float, lon: float) -> bool:
        """Enrich a single property with NC OneMap data."""
        data = self.query_by_point(lat, lon)

        if not data:
            return False

        # Build UPDATE statement
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        set_clauses = []
        values = []

        for field, value in data.items():
            set_clauses.append(f'{field} = ?')
            values.append(value)

        set_clauses.append('onemap_enriched_at = ?')
        values.append(now)

        values.append(property_id)

        sql = f'''
            UPDATE properties
            SET {', '.join(set_clauses)}
            WHERE id = ?
        '''

        cursor.execute(sql, values)
        self.stats['enriched'] += 1

        logger.info(f"Enriched property {property_id}: APN={data.get('parcel_id')}, Owner={data.get('owner_name')}")
        return True

    def enrich_all(self, county: str = None, limit: int = None):
        """Enrich all properties missing parcel data."""
        conn = self._get_connection()

        try:
            self._ensure_columns(conn)

            # Build query for properties with lat/long but no parcel_id
            sql = '''
                SELECT id, latitude, longitude, address, county
                FROM properties
                WHERE latitude IS NOT NULL
                  AND longitude IS NOT NULL
                  AND (parcel_id IS NULL OR parcel_id = '')
            '''
            params = []

            if county:
                sql += ' AND LOWER(county) = LOWER(?)'
                params.append(county)

            sql += ' ORDER BY created_at DESC'

            if limit:
                sql += f' LIMIT {limit}'

            cursor = conn.cursor()
            cursor.execute(sql, params)
            properties = cursor.fetchall()

            logger.info(f"Found {len(properties)} properties to enrich")

            for prop in properties:
                try:
                    self.enrich_property(
                        conn,
                        prop['id'],
                        prop['latitude'],
                        prop['longitude']
                    )
                    conn.commit()

                    # Rate limiting - be respectful
                    time.sleep(0.5)

                except Exception as e:
                    logger.error(f"Error enriching {prop['address']}: {e}")
                    self.stats['errors'] += 1

        finally:
            conn.close()

        return self.stats


def test_query(lat: float, lon: float):
    """Test a single point query."""
    enricher = NCOneMapEnricher()
    result = enricher.query_by_point(lat, lon)

    if result:
        print("\n" + "=" * 60)
        print("NC ONEMAP PARCEL DATA")
        print("=" * 60)
        for key, value in result.items():
            print(f"{key:30} {value}")
        print("=" * 60)
    else:
        print("No parcel found at this location")

    return result


def main():
    parser = argparse.ArgumentParser(description='Enrich properties with NC OneMap parcel data')
    parser.add_argument('--test', nargs=2, type=float, metavar=('LAT', 'LON'),
                        help='Test query at specific lat/long')
    parser.add_argument('--enrich-all', action='store_true',
                        help='Enrich all properties missing parcel data')
    parser.add_argument('--county', help='Only enrich properties in this county')
    parser.add_argument('--limit', type=int, help='Max properties to enrich')
    parser.add_argument('--db', default=DB_PATH, help='Database path')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.test:
        lat, lon = args.test
        test_query(lat, lon)
    elif args.enrich_all:
        enricher = NCOneMapEnricher(db_path=args.db)
        stats = enricher.enrich_all(county=args.county, limit=args.limit)

        print("\n" + "=" * 50)
        print("ENRICHMENT SUMMARY")
        print("=" * 50)
        print(f"Queried:    {stats['queried']}")
        print(f"Enriched:   {stats['enriched']}")
        print(f"Not Found:  {stats['not_found']}")
        print(f"Errors:     {stats['errors']}")
        print("=" * 50)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
