#!/usr/bin/env python3
"""
Property Monitoring Script

Monitors active properties for changes and updates:
- Price changes
- Status changes (active → pending → sold)
- Days on Market
- Views/Favorites (from Redfin scraping)
- Photos

Designed to run as a cron job (e.g., daily at 6am).

Usage:
    python monitor_properties.py                    # Monitor all active properties
    python monitor_properties.py --county Macon     # Monitor specific county
    python monitor_properties.py --check-only       # Check for changes without updating
    python monitor_properties.py --alerts           # Send alerts for significant changes

Cron example (daily at 6am):
    0 6 * * * cd /home/bigeug/myDREAMS/apps/buyer-workflow && /home/bigeug/myDREAMS/.venv/bin/python monitor_properties.py >> /home/bigeug/myDREAMS/logs/monitor.log 2>&1
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database path
DB_PATH = os.getenv('DREAMS_DB_PATH', str(PROJECT_ROOT / 'data' / 'dreams.db'))

# NC OneMap API for additional data
ONEMAP_URL = "https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/MapServer/1/query"


class PropertyMonitor:
    """Monitors properties for changes and updates data."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.stats = {
            'checked': 0,
            'updated': 0,
            'price_changes': 0,
            'status_changes': 0,
            'errors': 0,
        }
        self.changes = []

    def _get_connection(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_monitor_tables(self, conn):
        """Ensure monitoring tables exist."""
        cursor = conn.cursor()

        # Property monitors table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS property_monitors (
                id TEXT PRIMARY KEY,
                property_id TEXT NOT NULL UNIQUE,
                monitor_price INTEGER DEFAULT 1,
                monitor_status INTEGER DEFAULT 1,
                monitor_dom INTEGER DEFAULT 1,
                monitor_photos INTEGER DEFAULT 1,
                monitor_views INTEGER DEFAULT 1,
                last_price INTEGER,
                last_status TEXT,
                last_dom INTEGER,
                last_photo_count INTEGER,
                last_views INTEGER,
                last_favorites INTEGER,
                last_checked_at TEXT,
                last_changed_at TEXT,
                check_frequency TEXT DEFAULT 'daily',
                is_active INTEGER DEFAULT 1,
                alert_on_price_drop INTEGER DEFAULT 1,
                alert_on_status_change INTEGER DEFAULT 1,
                price_drop_threshold REAL DEFAULT 0.05
            )
        ''')

        # Property changes log
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS property_changes (
                id TEXT PRIMARY KEY,
                property_id TEXT NOT NULL,
                change_type TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                change_percent REAL,
                detected_at TEXT DEFAULT CURRENT_TIMESTAMP,
                source TEXT,
                notification_sent INTEGER DEFAULT 0,
                notified_leads TEXT
            )
        ''')

        conn.commit()

    def get_properties_to_monitor(self, conn, county: str = None, limit: int = None) -> List[Dict]:
        """Get list of properties that need monitoring."""
        query = '''
            SELECT p.*, pm.last_price, pm.last_status, pm.last_dom,
                   pm.last_checked_at, pm.is_active as monitor_active
            FROM properties p
            LEFT JOIN property_monitors pm ON p.id = pm.property_id
            WHERE p.status IN ('active', 'Active', 'pending', 'Pending', 'contingent', 'Contingent')
        '''
        params = []

        if county:
            query += ' AND LOWER(p.county) = LOWER(?)'
            params.append(county)

        # Prioritize properties not checked recently
        query += '''
            ORDER BY
                CASE WHEN pm.last_checked_at IS NULL THEN 0 ELSE 1 END,
                pm.last_checked_at ASC
        '''

        if limit:
            query += f' LIMIT {limit}'

        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def update_from_redfin(self, property_data: Dict) -> Optional[Dict]:
        """
        Fetch updated data from Redfin for a property.
        Returns dict of changed fields or None if no changes.
        """
        redfin_url = property_data.get('redfin_url')
        if not redfin_url:
            return None

        # For now, we can't scrape Redfin directly without browser automation
        # This would need to use the redfin_page_scraper in a separate process
        # For the cron job, we'll track what we have and detect changes on next import
        return None

    def check_property(self, conn, prop: Dict) -> List[Dict]:
        """
        Check a property for changes.
        Returns list of detected changes.
        """
        changes = []
        prop_id = prop['id']
        now = datetime.utcnow().isoformat()

        # Get or create monitor record
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM property_monitors WHERE property_id = ?', (prop_id,))
        monitor = cursor.fetchone()

        if not monitor:
            # Create monitor record
            cursor.execute('''
                INSERT INTO property_monitors (id, property_id, last_price, last_status, last_dom, last_checked_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (str(uuid.uuid4()), prop_id, prop.get('price'), prop.get('status'),
                  prop.get('days_on_market'), now))
            return changes

        monitor = dict(monitor)

        # Check for price changes
        if monitor.get('last_price') and prop.get('price'):
            old_price = monitor['last_price']
            new_price = prop['price']
            if old_price != new_price:
                change_pct = (new_price - old_price) / old_price if old_price else 0
                changes.append({
                    'property_id': prop_id,
                    'change_type': 'price',
                    'old_value': str(old_price),
                    'new_value': str(new_price),
                    'change_percent': change_pct,
                    'is_drop': new_price < old_price,
                })
                self.stats['price_changes'] += 1
                logger.info(f"Price change: {prop.get('address')} ${old_price:,} → ${new_price:,} ({change_pct*100:+.1f}%)")

        # Check for status changes
        if monitor.get('last_status') and prop.get('status'):
            old_status = monitor['last_status']
            new_status = prop['status']
            if old_status.lower() != new_status.lower():
                changes.append({
                    'property_id': prop_id,
                    'change_type': 'status',
                    'old_value': old_status,
                    'new_value': new_status,
                })
                self.stats['status_changes'] += 1
                logger.info(f"Status change: {prop.get('address')} {old_status} → {new_status}")

        # Update monitor record
        cursor.execute('''
            UPDATE property_monitors
            SET last_price = ?, last_status = ?, last_dom = ?,
                last_checked_at = ?, last_changed_at = CASE WHEN ? > 0 THEN ? ELSE last_changed_at END
            WHERE property_id = ?
        ''', (prop.get('price'), prop.get('status'), prop.get('days_on_market'),
              now, len(changes), now, prop_id))

        # Log changes
        for change in changes:
            cursor.execute('''
                INSERT INTO property_changes (id, property_id, change_type, old_value, new_value, change_percent, detected_at, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'monitor')
            ''', (str(uuid.uuid4()), change['property_id'], change['change_type'],
                  change['old_value'], change['new_value'], change.get('change_percent'), now))

        return changes

    def update_dom(self, conn):
        """Update days on market for all active properties based on list_date."""
        cursor = conn.cursor()
        today = datetime.now().date()

        # Update DOM based on list_date
        cursor.execute('''
            UPDATE properties
            SET days_on_market = julianday('now') - julianday(list_date),
                updated_at = ?
            WHERE list_date IS NOT NULL
              AND status IN ('active', 'Active')
        ''', (datetime.utcnow().isoformat(),))

        updated = cursor.rowcount
        logger.info(f"Updated DOM for {updated} properties")
        return updated

    def find_missing_photos(self, conn, county: str = None) -> List[Dict]:
        """Find properties missing photos."""
        query = '''
            SELECT id, address, city, county, redfin_url
            FROM properties
            WHERE (primary_photo IS NULL OR primary_photo = '')
              AND status IN ('active', 'Active')
        '''
        params = []

        if county:
            query += ' AND LOWER(county) = LOWER(?)'
            params.append(county)

        query += ' LIMIT 100'

        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def run_monitoring(self, county: str = None, limit: int = None, check_only: bool = False) -> Dict:
        """Run the full monitoring process."""
        conn = self._get_connection()

        try:
            self._ensure_monitor_tables(conn)

            # Get properties to check
            properties = self.get_properties_to_monitor(conn, county=county, limit=limit)
            logger.info(f"Checking {len(properties)} properties")

            # Check each property
            for prop in properties:
                self.stats['checked'] += 1
                try:
                    changes = self.check_property(conn, prop)
                    if changes:
                        self.changes.extend(changes)
                        self.stats['updated'] += 1
                except Exception as e:
                    logger.error(f"Error checking {prop.get('address')}: {e}")
                    self.stats['errors'] += 1

            # Update DOM for all properties
            self.update_dom(conn)

            # Find properties missing photos
            missing_photos = self.find_missing_photos(conn, county)
            if missing_photos:
                logger.info(f"Found {len(missing_photos)} properties missing photos")

            if not check_only:
                conn.commit()
                logger.info("Changes committed")

            return {
                'stats': self.stats,
                'changes': self.changes,
                'missing_photos': len(missing_photos),
            }

        finally:
            conn.close()

    def get_recent_changes(self, days: int = 7, county: str = None) -> List[Dict]:
        """Get recent property changes."""
        conn = self._get_connection()

        try:
            query = '''
                SELECT pc.*, p.address, p.city, p.county, p.price
                FROM property_changes pc
                JOIN properties p ON pc.property_id = p.id
                WHERE pc.detected_at >= datetime('now', ?)
            '''
            params = [f'-{days} days']

            if county:
                query += ' AND LOWER(p.county) = LOWER(?)'
                params.append(county)

            query += ' ORDER BY pc.detected_at DESC'

            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

        finally:
            conn.close()


def main():
    parser = argparse.ArgumentParser(description='Monitor properties for changes')
    parser.add_argument('--county', help='Only monitor specific county')
    parser.add_argument('--limit', type=int, help='Max properties to check')
    parser.add_argument('--check-only', action='store_true', help='Check without saving changes')
    parser.add_argument('--recent', type=int, metavar='DAYS', help='Show recent changes (last N days)')
    parser.add_argument('--db', default=DB_PATH, help='Database path')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    monitor = PropertyMonitor(db_path=args.db)

    if args.recent:
        changes = monitor.get_recent_changes(days=args.recent, county=args.county)
        print(f"\n{'='*60}")
        print(f"PROPERTY CHANGES (last {args.recent} days)")
        print('='*60)
        for change in changes:
            print(f"\n{change['address']}, {change['city']}")
            print(f"  {change['change_type'].upper()}: {change['old_value']} → {change['new_value']}")
            if change.get('change_percent'):
                print(f"  Change: {change['change_percent']*100:+.1f}%")
            print(f"  Detected: {change['detected_at']}")
        if not changes:
            print("No changes detected")
        print('='*60)
        return

    # Run monitoring
    result = monitor.run_monitoring(
        county=args.county,
        limit=args.limit,
        check_only=args.check_only
    )

    print(f"\n{'='*60}")
    print("MONITORING COMPLETE")
    print('='*60)
    print(f"Properties Checked:  {result['stats']['checked']}")
    print(f"Properties Updated:  {result['stats']['updated']}")
    print(f"Price Changes:       {result['stats']['price_changes']}")
    print(f"Status Changes:      {result['stats']['status_changes']}")
    print(f"Missing Photos:      {result['missing_photos']}")
    print(f"Errors:              {result['stats']['errors']}")
    print('='*60)

    if args.check_only:
        print("\n[CHECK ONLY - No changes saved]")

    # Print significant changes
    if result['changes']:
        print("\nSIGNIFICANT CHANGES:")
        for change in result['changes']:
            print(f"  - {change['change_type']}: {change['old_value']} → {change['new_value']}")


if __name__ == '__main__':
    main()
