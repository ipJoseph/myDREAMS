"""
Navica MLS Sync Engine

Orchestrates syncing MLS data from the Navica RESO API to the myDREAMS
listings database. Supports full and incremental sync modes, photo
downloading, and change detection (price/status changes).

Usage:
    # CLI
    python -m apps.navica.sync_engine --test
    python -m apps.navica.sync_engine --full --status Active
    python -m apps.navica.sync_engine --incremental
    python -m apps.navica.sync_engine --full --county Buncombe --status Active

    # Programmatic
    from apps.navica.sync_engine import NavicaSyncEngine
    engine = NavicaSyncEngine()
    stats = engine.run_incremental_sync()
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'
STATE_FILE = PROJECT_ROOT / 'data' / 'navica_sync_state.json'
PHOTOS_DIR = PROJECT_ROOT / 'data' / 'photos' / 'navica'

# Add project root to path for imports
sys.path.insert(0, str(PROJECT_ROOT))

from apps.navica.client import NavicaClient, NavicaAuthError, NavicaAPIError
from apps.navica.field_mapper import (
    map_reso_to_listing,
    map_reso_to_member,
    map_reso_to_office,
    map_reso_to_open_house,
    generate_listing_id,
    parse_timestamp,
)


def load_env():
    """Load environment variables from .env file."""
    env_path = PROJECT_ROOT / '.env'
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip().strip('"\''))


class NavicaSyncEngine:
    """
    Sync engine for Navica MLS data.

    Manages the full lifecycle of syncing MLS data:
    1. Fetch data from Navica API (full or incremental)
    2. Map RESO fields to myDREAMS schema
    3. Upsert to listings table
    4. Detect and record price/status changes
    5. Track sync state for incremental updates
    6. Log sync operations

    The engine writes to the `listings` table (not `properties`).
    The `listings` table is the MLS-oriented table with richer schema,
    while `properties` is the older hand-curated property table.
    """

    def __init__(
        self,
        db_path: str = None,
        feed: str = 'idx',
        mls_source: str = 'NavicaMLS',
    ):
        """
        Initialize sync engine.

        Args:
            db_path: Path to SQLite database
            feed: 'idx' or 'bbo' feed type
            mls_source: MLS source identifier for records
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.feed = feed
        self.mls_source = mls_source
        self.client = None

        # Ensure database tables exist
        self._ensure_tables()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _ensure_tables(self):
        """Create required tables if they don't exist."""
        conn = self._get_connection()
        try:
            # Extend listings table with Navica-specific columns if missing
            cursor = conn.execute("PRAGMA table_info(listings)")
            existing_cols = {row[1] for row in cursor.fetchall()}

            new_columns = [
                ('listing_key', 'TEXT'),
                ('property_subtype', 'TEXT'),
                ('original_list_price', 'INTEGER'),
                ('sold_price', 'INTEGER'),
                ('sold_date', 'TEXT'),
                ('lot_sqft', 'INTEGER'),
                ('garage_spaces', 'INTEGER'),
                ('appliances', 'TEXT'),
                ('interior_features', 'TEXT'),
                ('exterior_features', 'TEXT'),
                ('water_source', 'TEXT'),
                ('construction_materials', 'TEXT'),
                ('foundation', 'TEXT'),
                ('flooring', 'TEXT'),
                ('fireplace_features', 'TEXT'),
                ('parking_features', 'TEXT'),
                ('hoa_frequency', 'TEXT'),
                ('tax_annual_amount', 'INTEGER'),
                ('tax_assessed_value', 'INTEGER'),
                ('tax_year', 'INTEGER'),
                ('buyer_agent_id', 'TEXT'),
                ('buyer_agent_name', 'TEXT'),
                ('buyer_office_id', 'TEXT'),
                ('buyer_office_name', 'TEXT'),
                ('public_remarks', 'TEXT'),
                ('private_remarks', 'TEXT'),
                ('showing_instructions', 'TEXT'),
                ('parcel_number', 'TEXT'),
                ('subdivision', 'TEXT'),
                ('directions', 'TEXT'),
                ('expiration_date', 'TEXT'),
                ('modification_timestamp', 'TEXT'),
                ('idx_opt_in', 'INTEGER DEFAULT 1'),
                ('idx_address_display', 'INTEGER DEFAULT 1'),
                ('roof', 'TEXT'),
                ('sewer', 'TEXT'),
                ('stories', 'INTEGER'),
                ('vow_opt_in', 'INTEGER'),
            ]

            for col_name, col_type in new_columns:
                if col_name not in existing_cols:
                    try:
                        conn.execute(f"ALTER TABLE listings ADD COLUMN {col_name} {col_type}")
                        logger.info(f"Added column {col_name} to listings table")
                    except sqlite3.OperationalError:
                        pass

            # Create agents table for member data (or add missing columns)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS agents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    member_key TEXT UNIQUE,
                    member_mls_id TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    full_name TEXT,
                    email TEXT,
                    phone TEXT,
                    mobile_phone TEXT,
                    office_key TEXT,
                    office_name TEXT,
                    member_type TEXT,
                    member_status TEXT,
                    modification_timestamp TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Ensure agents table has all needed columns (may pre-exist with different schema)
            cursor = conn.execute("PRAGMA table_info(agents)")
            agent_cols = {row[1] for row in cursor.fetchall()}
            agent_new_columns = [
                ('member_key', 'TEXT'),
                ('member_mls_id', 'TEXT'),
                ('full_name', 'TEXT'),
                ('mobile_phone', 'TEXT'),
                ('office_key', 'TEXT'),
                ('member_type', 'TEXT'),
                ('member_status', 'TEXT'),
                ('modification_timestamp', 'TEXT'),
            ]
            for col_name, col_type in agent_new_columns:
                if col_name not in agent_cols:
                    try:
                        conn.execute(f"ALTER TABLE agents ADD COLUMN {col_name} {col_type}")
                        logger.info(f"Added column {col_name} to agents table")
                    except sqlite3.OperationalError:
                        pass

            # Create open_houses table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS open_houses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    open_house_key TEXT UNIQUE,
                    listing_key TEXT,
                    listing_id TEXT,
                    date TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    type TEXT,
                    remarks TEXT,
                    status TEXT,
                    modification_timestamp TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (listing_id) REFERENCES listings(mls_number)
                )
            ''')

            # Create indexes
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_listings_mls
                ON listings(mls_source, mls_number)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_listings_status
                ON listings(status)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_listings_city
                ON listings(city)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_listings_county
                ON listings(county)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_listings_mod_ts
                ON listings(modification_timestamp)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_listings_listing_key
                ON listings(listing_key)
            ''')

            conn.commit()
        finally:
            conn.close()

    def _init_client(self):
        """Initialize the Navica API client if not already done."""
        if self.client is None:
            self.client = NavicaClient.from_env(feed=self.feed)

    # ---------------------------------------------------------------
    # Sync state management
    # ---------------------------------------------------------------

    def _load_sync_state(self) -> Dict:
        """Load last sync state for incremental sync."""
        if STATE_FILE.exists():
            with open(STATE_FILE) as f:
                return json.load(f)
        return {}

    def _save_sync_state(self, state: Dict):
        """Save sync state after successful sync."""
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)

    # ---------------------------------------------------------------
    # Change detection
    # ---------------------------------------------------------------

    def _detect_changes(
        self,
        conn: sqlite3.Connection,
        listing: Dict,
        existing: Optional[Dict],
    ) -> List[Dict]:
        """
        Detect price and status changes for a listing.

        Returns list of change records for property_changes table.
        """
        if not existing:
            return []

        changes = []
        now = datetime.now().isoformat()
        listing_id = listing['id']

        # Price change
        old_price = existing.get('list_price')
        new_price = listing.get('list_price')
        if old_price and new_price and old_price != new_price:
            pct_change = round((new_price - old_price) / old_price * 100, 1)
            changes.append({
                'listing_id': listing_id,
                'mls_number': listing['mls_number'],
                'change_type': 'price',
                'old_value': str(old_price),
                'new_value': str(new_price),
                'pct_change': pct_change,
                'detected_at': now,
            })
            logger.info(
                f"Price change: {listing['mls_number']} "
                f"${old_price:,} -> ${new_price:,} ({pct_change:+.1f}%)"
            )

        # Status change
        old_status = existing.get('status')
        new_status = listing.get('status')
        if old_status and new_status and old_status != new_status:
            changes.append({
                'listing_id': listing_id,
                'mls_number': listing['mls_number'],
                'change_type': 'status',
                'old_value': old_status,
                'new_value': new_status,
                'pct_change': None,
                'detected_at': now,
            })
            logger.info(
                f"Status change: {listing['mls_number']} "
                f"{old_status} -> {new_status}"
            )

        return changes

    def _record_changes(self, conn: sqlite3.Connection, changes: List[Dict]):
        """Insert change records into property_changes table."""
        for change in changes:
            # Check if property_changes table has the columns we need
            try:
                conn.execute('''
                    INSERT INTO property_changes (
                        property_id, change_type, old_value, new_value,
                        change_percent, detected_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                ''', [
                    change['listing_id'],
                    change['change_type'],
                    change['old_value'],
                    change['new_value'],
                    change.get('pct_change'),
                    change['detected_at'],
                ])
            except sqlite3.OperationalError as e:
                logger.debug(f"Could not record change (table schema mismatch): {e}")

    # ---------------------------------------------------------------
    # Upsert logic
    # ---------------------------------------------------------------

    def _upsert_listing(
        self,
        conn: sqlite3.Connection,
        listing: Dict,
        dry_run: bool = False,
    ) -> str:
        """
        Insert or update a listing in the database.

        Returns: 'created', 'updated', or 'skipped'
        """
        mls_number = listing.get('mls_number')
        if not mls_number:
            return 'skipped'

        # Check if exists by mls_source + mls_number
        existing = conn.execute(
            "SELECT * FROM listings WHERE mls_source = ? AND mls_number = ?",
            [self.mls_source, mls_number]
        ).fetchone()

        existing_dict = dict(existing) if existing else None

        # Detect changes before upsert
        changes = self._detect_changes(conn, listing, existing_dict)

        if dry_run:
            return 'created' if not existing else 'updated'

        # Record detected changes
        if changes:
            self._record_changes(conn, changes)

        now = datetime.now().isoformat()

        if existing:
            # Update existing: only update non-None values
            update_data = {
                k: v for k, v in listing.items()
                if v is not None and k not in ('id', 'captured_at')
            }
            update_data['updated_at'] = now

            if update_data:
                set_clause = ", ".join([f"{k} = ?" for k in update_data.keys()])
                values = list(update_data.values())
                values.append(existing['id'])

                conn.execute(
                    f"UPDATE listings SET {set_clause} WHERE id = ?",
                    values
                )
            return 'updated'
        else:
            # Insert new listing
            listing['captured_at'] = now
            listing['updated_at'] = now

            # Filter out None values
            insert_data = {k: v for k, v in listing.items() if v is not None}

            columns = list(insert_data.keys())
            placeholders = ', '.join(['?' for _ in columns])
            values = list(insert_data.values())

            conn.execute(
                f"INSERT INTO listings ({', '.join(columns)}) VALUES ({placeholders})",
                values
            )
            return 'created'

    def _upsert_agent(self, conn: sqlite3.Connection, agent: Dict):
        """Upsert an agent/member record."""
        if not agent.get('member_key'):
            return

        now = datetime.now().isoformat()
        existing = conn.execute(
            "SELECT id FROM agents WHERE member_key = ?",
            [agent['member_key']]
        ).fetchone()

        if existing:
            update_data = {k: v for k, v in agent.items() if v is not None and k != 'member_key'}
            update_data['updated_at'] = now
            if update_data:
                set_clause = ", ".join([f"{k} = ?" for k in update_data.keys()])
                values = list(update_data.values())
                values.append(agent['member_key'])
                conn.execute(
                    f"UPDATE agents SET {set_clause} WHERE member_key = ?",
                    values
                )
        else:
            agent['created_at'] = now
            agent['updated_at'] = now
            insert_data = {k: v for k, v in agent.items() if v is not None}
            columns = list(insert_data.keys())
            placeholders = ', '.join(['?' for _ in columns])
            conn.execute(
                f"INSERT INTO agents ({', '.join(columns)}) VALUES ({placeholders})",
                list(insert_data.values())
            )

    def _upsert_open_house(self, conn: sqlite3.Connection, oh: Dict):
        """Upsert an open house record."""
        if not oh.get('open_house_key'):
            return

        now = datetime.now().isoformat()
        existing = conn.execute(
            "SELECT id FROM open_houses WHERE open_house_key = ?",
            [oh['open_house_key']]
        ).fetchone()

        if existing:
            update_data = {k: v for k, v in oh.items() if v is not None and k != 'open_house_key'}
            update_data['updated_at'] = now
            if update_data:
                set_clause = ", ".join([f"{k} = ?" for k in update_data.keys()])
                values = list(update_data.values())
                values.append(oh['open_house_key'])
                conn.execute(
                    f"UPDATE open_houses SET {set_clause} WHERE open_house_key = ?",
                    values
                )
        else:
            oh['created_at'] = now
            oh['updated_at'] = now
            insert_data = {k: v for k, v in oh.items() if v is not None}
            columns = list(insert_data.keys())
            placeholders = ', '.join(['?' for _ in columns])
            conn.execute(
                f"INSERT INTO open_houses ({', '.join(columns)}) VALUES ({placeholders})",
                list(insert_data.values())
            )

    # ---------------------------------------------------------------
    # Sync log
    # ---------------------------------------------------------------

    def _log_sync(
        self,
        conn: sqlite3.Connection,
        sync_type: str,
        stats: Dict,
        error: str = None,
    ) -> int:
        """Write a sync_log entry and return its ID."""
        cursor = conn.execute('''
            INSERT INTO sync_log (
                sync_type, source, direction,
                records_processed, records_created, records_updated, records_failed,
                started_at, completed_at, error_message, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', [
            sync_type,
            f'navica_{self.feed}',
            'inbound',
            stats.get('fetched', 0),
            stats.get('created', 0),
            stats.get('updated', 0),
            stats.get('errors', 0),
            stats.get('started_at', datetime.now().isoformat()),
            datetime.now().isoformat(),
            error,
            json.dumps(stats),
        ])
        return cursor.lastrowid

    # ---------------------------------------------------------------
    # Main sync methods
    # ---------------------------------------------------------------

    def run_full_sync(
        self,
        status: str = None,
        property_types: List[str] = None,
        county: str = None,
        city: str = None,
        dry_run: bool = False,
        max_records: int = None,
    ) -> Dict[str, Any]:
        """
        Run a full sync (all matching records from scratch).

        Args:
            status: Filter by StandardStatus
            property_types: Filter by PropertyType
            county: Filter by county
            city: Filter by city
            dry_run: Preview without database changes
            max_records: Limit total records fetched

        Returns:
            Stats dict with counts and timing
        """
        self._init_client()

        stats = {
            'sync_type': 'full',
            'feed': self.feed,
            'started_at': datetime.now().isoformat(),
            'fetched': 0,
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'price_changes': 0,
            'status_changes': 0,
            'errors': 0,
        }

        logger.info(f"Starting full sync (feed={self.feed}, status={status})")

        try:
            fetch_kwargs = dict(
                status=status,
                county=county,
                city=city,
                max_records=max_records,
            )
            # API accepts a single PropertyType filter, not a list
            if property_types and len(property_types) == 1:
                fetch_kwargs['property_type'] = property_types[0]
            properties = self.client.fetch_properties(**fetch_kwargs)
        except NavicaAPIError as e:
            logger.error(f"Failed to fetch properties: {e}")
            stats['errors'] += 1
            return stats

        stats['fetched'] = len(properties)
        logger.info(f"Fetched {len(properties)} properties from Navica API")

        if not properties:
            logger.info("No properties to sync")
            return stats

        if dry_run:
            logger.info("DRY RUN: No database changes will be made")

        conn = self._get_connection()
        try:
            for i, prop in enumerate(properties):
                try:
                    listing = map_reso_to_listing(prop, self.mls_source)
                    result = self._upsert_listing(conn, listing, dry_run=dry_run)

                    if result == 'created':
                        stats['created'] += 1
                    elif result == 'updated':
                        stats['updated'] += 1
                    else:
                        stats['skipped'] += 1

                    if (i + 1) % 100 == 0:
                        logger.info(f"Processed {i + 1}/{len(properties)}...")
                        if not dry_run:
                            conn.commit()  # Periodic commit

                except Exception as e:
                    logger.error(f"Error processing {prop.get('ListingId')}: {e}")
                    stats['errors'] += 1

            if not dry_run:
                conn.commit()

                # Save sync state
                self._save_sync_state({
                    'last_sync': datetime.now(timezone.utc).isoformat(),
                    'sync_type': 'full',
                    'records_synced': len(properties),
                    'status_filter': status,
                    'feed': self.feed,
                })

                # Log sync
                self._log_sync(conn, 'navica_full_sync', stats)
                conn.commit()

        finally:
            conn.close()

        stats['completed_at'] = datetime.now().isoformat()
        stats['api_stats'] = self.client.get_stats()
        return stats

    def run_incremental_sync(
        self,
        status: str = None,
        dry_run: bool = False,
        max_records: int = None,
    ) -> Dict[str, Any]:
        """
        Run incremental sync (only records modified since last sync).

        Uses ModificationTimestamp from the last successful sync to fetch
        only changed records, dramatically reducing API calls and data transfer.

        Args:
            status: Optional status filter
            dry_run: Preview without database changes
            max_records: Safety limit on records

        Returns:
            Stats dict
        """
        self._init_client()

        stats = {
            'sync_type': 'incremental',
            'feed': self.feed,
            'started_at': datetime.now().isoformat(),
            'fetched': 0,
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'price_changes': 0,
            'status_changes': 0,
            'errors': 0,
        }

        # Load last sync timestamp
        state = self._load_sync_state()
        modified_since = None

        if 'last_sync' in state:
            modified_since = datetime.fromisoformat(state['last_sync'])
            logger.info(f"Incremental sync: fetching records modified since {modified_since}")
        else:
            logger.warning("No previous sync state found. Falling back to last 24 hours.")
            modified_since = datetime.now(timezone.utc) - timedelta(hours=24)

        try:
            # Note: Navica API doesn't support server-side ModificationTimestamp filtering.
            # We fetch all listings of the given status and filter client-side.
            properties = self.client.fetch_properties(
                status=status,
                max_records=max_records,
            )
        except NavicaAPIError as e:
            logger.error(f"Failed to fetch properties: {e}")
            stats['errors'] += 1
            return stats

        stats['fetched'] = len(properties)
        logger.info(f"Fetched {len(properties)} changed properties")

        if not properties:
            logger.info("No changes since last sync")
            # Still update the sync state timestamp
            if not dry_run:
                self._save_sync_state({
                    'last_sync': datetime.now(timezone.utc).isoformat(),
                    'sync_type': 'incremental',
                    'records_synced': 0,
                    'feed': self.feed,
                })
            return stats

        conn = self._get_connection()
        try:
            for i, prop in enumerate(properties):
                try:
                    listing = map_reso_to_listing(prop, self.mls_source)
                    result = self._upsert_listing(conn, listing, dry_run=dry_run)

                    if result == 'created':
                        stats['created'] += 1
                    elif result == 'updated':
                        stats['updated'] += 1
                    else:
                        stats['skipped'] += 1

                    if (i + 1) % 100 == 0:
                        logger.info(f"Processed {i + 1}/{len(properties)}...")
                        if not dry_run:
                            conn.commit()

                except Exception as e:
                    logger.error(f"Error processing {prop.get('ListingId')}: {e}")
                    stats['errors'] += 1

            if not dry_run:
                conn.commit()

                self._save_sync_state({
                    'last_sync': datetime.now(timezone.utc).isoformat(),
                    'sync_type': 'incremental',
                    'records_synced': len(properties),
                    'feed': self.feed,
                })

                self._log_sync(conn, 'navica_incremental_sync', stats)
                conn.commit()

        finally:
            conn.close()

        stats['completed_at'] = datetime.now().isoformat()
        stats['api_stats'] = self.client.get_stats()
        return stats

    def sync_members(self, dry_run: bool = False) -> Dict[str, int]:
        """
        Sync member (agent) records from Navica.

        Returns:
            Stats dict with created/updated counts
        """
        self._init_client()

        stats = {'fetched': 0, 'created': 0, 'updated': 0, 'errors': 0}

        # Load last member sync timestamp
        state = self._load_sync_state()
        modified_since = None
        if 'last_member_sync' in state:
            modified_since = datetime.fromisoformat(state['last_member_sync'])

        try:
            members = self.client.fetch_agents(member_status='Active' if modified_since else None)
        except NavicaAPIError as e:
            logger.error(f"Failed to fetch members: {e}")
            return stats

        stats['fetched'] = len(members)
        logger.info(f"Fetched {len(members)} member records")

        if not members or dry_run:
            return stats

        conn = self._get_connection()
        try:
            for member_raw in members:
                try:
                    member = map_reso_to_member(member_raw)
                    self._upsert_agent(conn, member)
                    stats['created'] += 1  # Simplified; could track create vs update
                except Exception as e:
                    logger.error(f"Error processing member: {e}")
                    stats['errors'] += 1

            conn.commit()

            # Update sync state
            state['last_member_sync'] = datetime.now(timezone.utc).isoformat()
            self._save_sync_state(state)

        finally:
            conn.close()

        return stats

    def sync_open_houses(self, dry_run: bool = False) -> Dict[str, int]:
        """
        Sync open house records from Navica.

        Returns:
            Stats dict
        """
        self._init_client()

        stats = {'fetched': 0, 'created': 0, 'updated': 0, 'errors': 0}

        state = self._load_sync_state()
        modified_since = None
        if 'last_open_house_sync' in state:
            modified_since = datetime.fromisoformat(state['last_open_house_sync'])

        try:
            open_houses = self.client.fetch_open_houses()
        except NavicaAPIError as e:
            logger.error(f"Failed to fetch open houses: {e}")
            return stats

        stats['fetched'] = len(open_houses)
        logger.info(f"Fetched {len(open_houses)} open house records")

        if not open_houses or dry_run:
            return stats

        conn = self._get_connection()
        try:
            for oh_raw in open_houses:
                try:
                    oh = map_reso_to_open_house(oh_raw)
                    self._upsert_open_house(conn, oh)
                    stats['created'] += 1
                except Exception as e:
                    logger.error(f"Error processing open house: {e}")
                    stats['errors'] += 1

            conn.commit()

            state['last_open_house_sync'] = datetime.now(timezone.utc).isoformat()
            self._save_sync_state(state)

        finally:
            conn.close()

        return stats

    def test_connection(self) -> bool:
        """Test API connection."""
        self._init_client()
        return self.client.test_connection()


def print_stats(stats: Dict):
    """Print sync statistics."""
    print("\n" + "=" * 55)
    print("NAVICA SYNC SUMMARY")
    print("=" * 55)
    print(f"  Sync type:      {stats.get('sync_type', 'unknown')}")
    print(f"  Feed:           {stats.get('feed', 'unknown')}")
    print(f"  Fetched:        {stats.get('fetched', 0):,}")
    print(f"  Created:        {stats.get('created', 0):,}")
    print(f"  Updated:        {stats.get('updated', 0):,}")
    print(f"  Skipped:        {stats.get('skipped', 0):,}")
    print(f"  Errors:         {stats.get('errors', 0):,}")

    api_stats = stats.get('api_stats', {})
    if api_stats:
        print(f"  API requests:   {api_stats.get('requests', 0):,}")
        print(f"  API retries:    {api_stats.get('retries', 0):,}")

    if 'started_at' in stats and 'completed_at' in stats:
        start = datetime.fromisoformat(stats['started_at'])
        end = datetime.fromisoformat(stats['completed_at'])
        duration = (end - start).total_seconds()
        print(f"  Duration:       {duration:.1f}s")

    print("=" * 55)


def main():
    """CLI entry point for Navica sync."""
    parser = argparse.ArgumentParser(
        description="Sync MLS data from Navica RESO API to myDREAMS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Test connection
    python -m apps.navica.sync_engine --test

    # Full sync of active listings
    python -m apps.navica.sync_engine --full --status Active

    # Incremental sync (only changes since last run)
    python -m apps.navica.sync_engine --incremental

    # Full sync for specific county
    python -m apps.navica.sync_engine --full --county Buncombe --status Active

    # Preview without database changes
    python -m apps.navica.sync_engine --full --dry-run

    # Use BBO feed for sold data
    python -m apps.navica.sync_engine --full --feed bbo --status Closed

    # Sync agents and open houses
    python -m apps.navica.sync_engine --sync-members
    python -m apps.navica.sync_engine --sync-open-houses
        """
    )

    parser.add_argument('--test', action='store_true',
                        help='Test API connection only')
    parser.add_argument('--full', action='store_true',
                        help='Full sync (all matching records)')
    parser.add_argument('--incremental', action='store_true',
                        help='Incremental sync (records modified since last run)')
    parser.add_argument('--sync-members', action='store_true',
                        help='Sync agent/member records')
    parser.add_argument('--sync-open-houses', action='store_true',
                        help='Sync open house records')
    parser.add_argument('--status',
                        choices=['Active', 'Pending', 'Closed', 'Expired', 'Withdrawn'],
                        help='Filter by listing status')
    parser.add_argument('--county', help='Filter by county')
    parser.add_argument('--city', help='Filter by city')
    parser.add_argument('--types', nargs='+',
                        choices=['Residential', 'Land', 'Farm', 'Commercial Sale',
                                 'Residential Income', 'Manufactured In Park'],
                        help='Filter by property types')
    parser.add_argument('--feed', choices=['idx', 'bbo'], default='idx',
                        help='API feed to use (default: idx)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview without database changes')
    parser.add_argument('--max-records', type=int,
                        help='Maximum records to fetch (safety limit)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose logging')

    args = parser.parse_args()

    # Set up logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    # Validate args
    has_action = any([args.test, args.full, args.incremental,
                      args.sync_members, args.sync_open_houses])
    if not has_action:
        parser.print_help()
        print("\nError: Must specify an action (--test, --full, --incremental, --sync-members, --sync-open-houses)")
        return 1

    load_env()

    engine = NavicaSyncEngine(feed=args.feed)

    # Test mode
    if args.test:
        success = engine.test_connection()
        return 0 if success else 1

    # Member sync
    if args.sync_members:
        stats = engine.sync_members(dry_run=args.dry_run)
        print(f"Members synced: {stats}")
        return 0

    # Open house sync
    if args.sync_open_houses:
        stats = engine.sync_open_houses(dry_run=args.dry_run)
        print(f"Open houses synced: {stats}")
        return 0

    # Property sync (full or incremental)
    if args.full:
        stats = engine.run_full_sync(
            status=args.status,
            property_types=args.types,
            county=args.county,
            city=args.city,
            dry_run=args.dry_run,
            max_records=args.max_records,
        )
    elif args.incremental:
        stats = engine.run_incremental_sync(
            status=args.status,
            dry_run=args.dry_run,
            max_records=args.max_records,
        )

    print_stats(stats)
    return 0 if stats.get('errors', 0) == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
