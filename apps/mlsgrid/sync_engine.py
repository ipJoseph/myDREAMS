"""
MLS Grid Sync Engine (Canopy MLS)

Orchestrates syncing MLS data from Canopy MLS via the MLS Grid RESO Web API
to the myDREAMS listings database. Follows the same pattern as the Navica
sync engine but handles OData-specific pagination and server-side
ModificationTimestamp filtering.

Usage:
    # CLI
    python -m apps.mlsgrid.sync_engine --test
    python -m apps.mlsgrid.sync_engine --full --status Active
    python -m apps.mlsgrid.sync_engine --incremental
    python -m apps.mlsgrid.sync_engine --full --dry-run

    # Programmatic
    from apps.mlsgrid.sync_engine import MLSGridSyncEngine
    engine = MLSGridSyncEngine()
    stats = engine.run_incremental_sync()
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'dreams.db'
STATE_FILE = PROJECT_ROOT / 'data' / 'mlsgrid_sync_state.json'
PHOTOS_DIR = PROJECT_ROOT / 'data' / 'photos' / 'mlsgrid'

# Add project root to path for imports
sys.path.insert(0, str(PROJECT_ROOT))

from apps.mlsgrid.client import MLSGridClient, MLSGridAuthError, MLSGridAPIError
from apps.navica.field_mapper import (
    map_reso_to_listing,
    map_reso_to_member,
    map_reso_to_office,
    map_reso_to_open_house,
    generate_listing_id,
    ensure_listing_columns,
    extract_photos,
    parse_timestamp,
)


MLS_SOURCE = 'CanopyMLS'


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


class MLSGridSyncEngine:
    """
    Sync engine for Canopy MLS data via MLS Grid.

    Manages the full lifecycle of syncing MLS data:
    1. Fetch data from MLS Grid API (full or incremental)
    2. Map RESO fields to myDREAMS schema (using shared field mapper)
    3. Upsert to listings table (with mls_source = 'CanopyMLS')
    4. Detect and record price/status changes
    5. Track sync state for incremental updates
    6. Log sync operations

    Key advantage over Navica: MLS Grid supports server-side
    ModificationTimestamp filtering, so incremental syncs only fetch
    records that actually changed. This is much more efficient.
    """

    def __init__(self, db_path: str = None):
        """
        Initialize sync engine.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.mls_source = MLS_SOURCE
        self.client = None
        self._photos_updated_count = 0

        # Ensure database tables exist (reuse Navica's table setup)
        self._ensure_tables()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(str(self.db_path), timeout=60)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def _ensure_tables(self):
        """Ensure required tables and indexes exist."""
        conn = self._get_connection()
        try:
            # Cache known listing columns for dynamic schema expansion
            cursor = conn.execute("PRAGMA table_info(listings)")
            self._known_listing_columns = {row[1] for row in cursor.fetchall()}

            # The Navica sync engine already creates the listings table schema.
            # We just need to make sure our indexes exist.
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_listings_mls
                ON listings(mls_source, mls_number)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_listings_status
                ON listings(status)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_listings_mod_ts
                ON listings(modification_timestamp)
            ''')

            # Create sync_log table if missing
            conn.execute('''
                CREATE TABLE IF NOT EXISTS sync_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sync_type TEXT,
                    source TEXT,
                    direction TEXT DEFAULT 'inbound',
                    records_processed INTEGER DEFAULT 0,
                    records_created INTEGER DEFAULT 0,
                    records_updated INTEGER DEFAULT 0,
                    records_failed INTEGER DEFAULT 0,
                    started_at TEXT,
                    completed_at TEXT,
                    error_message TEXT,
                    details TEXT
                )
            ''')

            # Create property_changes table if missing
            conn.execute('''
                CREATE TABLE IF NOT EXISTS property_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    property_id TEXT,
                    change_type TEXT,
                    old_value TEXT,
                    new_value TEXT,
                    change_percent REAL,
                    detected_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (property_id) REFERENCES listings(id)
                )
            ''')

            conn.commit()
        finally:
            conn.close()

    def _init_client(self):
        """Initialize the MLS Grid API client if not already done."""
        if self.client is None:
            self.client = MLSGridClient.from_env()

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
        """Detect price and status changes for a listing."""
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
                logger.debug(f"Could not record change: {e}")

    # ---------------------------------------------------------------
    # Upsert logic
    # ---------------------------------------------------------------

    # Fields related to photos that should be skipped during update
    # when PhotosChangeTimestamp has not changed. This prevents CDN URLs
    # from overwriting locally-downloaded photo paths during re-syncs.
    PHOTO_FIELDS = {
        'primary_photo', 'photos', 'photo_count', 'photo_source',
        'photo_verified_at', 'photo_review_status', 'media_keys',
    }

    def _upsert_listing(
        self,
        conn: sqlite3.Connection,
        listing: Dict,
        raw_prop: Dict = None,
        dry_run: bool = False,
    ) -> str:
        """
        Insert or update a listing in the database.

        Args:
            conn: Database connection
            listing: Mapped listing dict from field_mapper
            raw_prop: Raw RESO property dict (used for MlgCanView check)
            dry_run: If True, do not write to database

        Returns: 'created', 'updated', 'deleted', or 'skipped'
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

        # ----- Improvement 1: MlgCanView deletion detection -----
        if raw_prop and raw_prop.get('MlgCanView') is False:
            if existing_dict:
                if dry_run:
                    return 'deleted'
                now = datetime.now().isoformat()
                conn.execute(
                    "UPDATE listings SET status = 'DELETED', idx_opt_in = 0, "
                    "updated_at = ? WHERE id = ?",
                    [now, existing_dict['id']]
                )
                logger.info(
                    f"Deleted listing {mls_number}: MlgCanView=false "
                    f"(was {existing_dict.get('status')})"
                )
                # Record the status change
                if existing_dict.get('status') != 'DELETED':
                    self._record_changes(conn, [{
                        'listing_id': existing_dict['id'],
                        'mls_number': mls_number,
                        'change_type': 'status',
                        'old_value': existing_dict.get('status', 'UNKNOWN'),
                        'new_value': 'DELETED',
                        'pct_change': None,
                        'detected_at': now,
                    }])
            else:
                logger.debug(
                    f"Skipping deleted listing {mls_number}: not in local DB"
                )
            return 'deleted'

        # Detect changes before upsert
        changes = self._detect_changes(conn, listing, existing_dict)

        if dry_run:
            return 'created' if not existing else 'updated'

        # Record detected changes
        if changes:
            self._record_changes(conn, changes)

        now = datetime.now().isoformat()

        if existing:
            # ----- Improvement 3: PhotosChangeTimestamp tracking -----
            # Compare new photos_change_timestamp with stored value.
            # If unchanged, skip photo fields to preserve local photo paths.
            skip_photo_fields = False
            new_photo_ts = listing.get('photos_change_timestamp')
            old_photo_ts = existing_dict.get('photos_change_timestamp')
            has_local_photo = bool(existing_dict.get('photo_local_path'))
            if new_photo_ts and old_photo_ts and new_photo_ts == old_photo_ts and has_local_photo:
                skip_photo_fields = True
                logger.debug(
                    f"Photos unchanged for {mls_number} "
                    f"(ts={new_photo_ts}), preserving local paths"
                )
            elif new_photo_ts and old_photo_ts and new_photo_ts == old_photo_ts and not has_local_photo:
                logger.debug(
                    f"Photos unchanged for {mls_number} but no local file, refreshing URLs"
                )

            # Update existing: only update non-None values
            update_data = {
                k: v for k, v in listing.items()
                if v is not None and k not in ('id', 'captured_at')
            }

            # Remove photo fields if timestamps match
            if skip_photo_fields:
                for field in self.PHOTO_FIELDS:
                    update_data.pop(field, None)

            update_data['updated_at'] = now

            if update_data:
                set_clause = ", ".join([f"{k} = ?" for k in update_data.keys()])
                values = list(update_data.values())
                values.append(existing['id'])

                conn.execute(
                    f"UPDATE listings SET {set_clause} WHERE id = ?",
                    values
                )

            # Track whether photos were actually updated
            if not skip_photo_fields and listing.get('photo_count'):
                self._photos_updated_count += 1

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

            # New listings always have photos updated
            if listing.get('photo_count'):
                self._photos_updated_count += 1

            return 'created'

    def _download_listing_photos(self, mls_number: str, media_list: list) -> bool:
        """Download all photos from Media array during sync.

        Called after upsert for new/photo-changed listings. Uses the fresh
        MediaURLs from the replication response (zero additional API calls).
        Downloads primary + all gallery photos, updates both photo_local_path
        and the photos JSON column with local paths.

        Returns True if at least one photo was downloaded or already exists.
        """
        if not media_list or not mls_number:
            return False

        PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

        primary_url, all_urls, count = extract_photos(media_list)
        if not all_urls:
            return False

        import requests as req
        from urllib.parse import urlparse

        local_paths = []
        any_downloaded = False

        for idx, photo_url in enumerate(all_urls):
            path_lower = urlparse(photo_url).path.lower()
            ext = '.png' if path_lower.endswith('.png') else \
                  '.webp' if path_lower.endswith('.webp') else '.jpg'

            if idx == 0:
                filename = f"{mls_number}{ext}"
            else:
                filename = f"{mls_number}_{idx:02d}{ext}"

            filepath = PHOTOS_DIR / filename

            # Skip if already on disk
            if filepath.exists() and filepath.stat().st_size > 0:
                local_paths.append(f"/api/public/photos/mlsgrid/{filename}")
                continue

            try:
                resp = req.get(photo_url, timeout=30, stream=True)
                resp.raise_for_status()

                with open(filepath, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)

                if filepath.stat().st_size > 0:
                    local_paths.append(f"/api/public/photos/mlsgrid/{filename}")
                    any_downloaded = True
                else:
                    filepath.unlink(missing_ok=True)

            except Exception as e:
                logger.debug(f"Photo download failed for {mls_number} [{idx}]: {e}")

        if local_paths:
            import json as _json
            conn = self._get_connection()
            try:
                conn.execute(
                    "UPDATE listings SET photo_local_path = ?, photos = ? "
                    "WHERE mls_source = ? AND mls_number = ?",
                    [str(PHOTOS_DIR / f"{mls_number}.jpg"), _json.dumps(local_paths),
                     self.mls_source, mls_number]
                )
                conn.commit()
            finally:
                conn.close()

        return any_downloaded or bool(local_paths)

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
            'mlsgrid_canopy',
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
        dry_run: bool = False,
        max_records: int = None,
    ) -> Dict[str, Any]:
        """
        Run a full sync (all matching records from scratch).

        Args:
            status: Filter by StandardStatus (Active, Pending, Closed, etc.)
            property_types: Filter by PropertyType
            dry_run: Preview without database changes
            max_records: Limit total records fetched

        Returns:
            Stats dict with counts and timing
        """
        self._init_client()

        stats = {
            'sync_type': 'full',
            'mls_source': self.mls_source,
            'started_at': datetime.now().isoformat(),
            'fetched': 0,
            'created': 0,
            'updated': 0,
            'deleted': 0,
            'skipped': 0,
            'photos_updated': 0,
            'price_changes': 0,
            'status_changes': 0,
            'errors': 0,
        }
        self._photos_updated_count = 0

        logger.info(f"Starting full sync (status={status})")

        try:
            # Full sync: MlgCanView=true only (no deletion signals needed)
            properties = self.client.fetch_properties(
                status=status,
                property_types=property_types,
                max_records=max_records,
                include_deleted=False,
            )
        except MLSGridAPIError as e:
            logger.error(f"Failed to fetch properties: {e}")
            stats['errors'] += 1
            return stats

        stats['fetched'] = len(properties)
        logger.info(f"Fetched {len(properties)} properties from MLS Grid")

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

                    # Ensure schema has all columns this listing needs
                    if set(listing.keys()) - self._known_listing_columns:
                        self._known_listing_columns = ensure_listing_columns(
                            conn, listing, self._known_listing_columns
                        )
                        conn.commit()

                    result = self._upsert_listing(
                        conn, listing, raw_prop=prop, dry_run=dry_run
                    )

                    if result == 'created':
                        stats['created'] += 1
                    elif result == 'updated':
                        stats['updated'] += 1
                    elif result == 'deleted':
                        stats['deleted'] += 1
                    else:
                        stats['skipped'] += 1

                    # Commit every 10 records (was 100) and yield briefly
                    # so other writers (public contact form, event
                    # tracking) can grab the lock. With the public site
                    # now accepting real-time submissions, we need the
                    # sync to be a polite citizen of the DB.
                    if not dry_run and (i + 1) % 10 == 0:
                        conn.commit()
                        import time as _time_mod
                        _time_mod.sleep(0.05)  # 50ms yield for other writers

                    if (i + 1) % 100 == 0:
                        logger.info(f"Processed {i + 1}/{len(properties)}...")

                except Exception as e:
                    logger.error(f"Error processing {prop.get('ListingId')}: {e}")
                    stats['errors'] += 1

            stats['photos_updated'] = self._photos_updated_count

            if not dry_run:
                conn.commit()

                # Save sync state
                self._save_sync_state({
                    'last_sync': datetime.now(timezone.utc).isoformat(),
                    'sync_type': 'full',
                    'records_synced': len(properties),
                    'status_filter': status,
                })

                # Log sync
                self._log_sync(conn, 'mlsgrid_full_sync', stats)
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

        MLS Grid supports server-side ModificationTimestamp filtering,
        which is much more efficient than Navica's client-side approach.

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
            'mls_source': self.mls_source,
            'started_at': datetime.now().isoformat(),
            'fetched': 0,
            'created': 0,
            'updated': 0,
            'deleted': 0,
            'skipped': 0,
            'photos_updated': 0,
            'price_changes': 0,
            'status_changes': 0,
            'errors': 0,
        }
        self._photos_updated_count = 0

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
            # Incremental sync: include_deleted=True so we receive MlgCanView=false
            # signals for listings that were deleted, pulled, or opted out.
            # Without this, stale listings linger as ACTIVE in our DB.
            properties = self.client.fetch_properties(
                status=status,
                modified_since=modified_since,
                max_records=max_records,
                include_deleted=True,
            )
        except MLSGridAPIError as e:
            logger.error(f"Failed to fetch properties: {e}")
            stats['errors'] += 1
            return stats

        stats['fetched'] = len(properties)
        logger.info(f"Fetched {len(properties)} changed properties")

        if not properties:
            logger.info("No changes since last sync")
            if not dry_run:
                self._save_sync_state({
                    'last_sync': datetime.now(timezone.utc).isoformat(),
                    'sync_type': 'incremental',
                    'records_synced': 0,
                })
            return stats

        photos_downloaded = 0
        conn = self._get_connection()
        try:
            for i, prop in enumerate(properties):
                try:
                    listing = map_reso_to_listing(prop, self.mls_source)

                    # Ensure schema has all columns this listing needs
                    if set(listing.keys()) - self._known_listing_columns:
                        self._known_listing_columns = ensure_listing_columns(
                            conn, listing, self._known_listing_columns
                        )
                        conn.commit()

                    result = self._upsert_listing(
                        conn, listing, raw_prop=prop, dry_run=dry_run
                    )

                    # Download all photos for new or photo-changed listings.
                    # Media data is already in the replication response
                    # ($expand=Media), so this costs zero additional API calls.
                    # CDN downloads are parallel-safe and don't count against
                    # API rate limits.
                    if result in ('created', 'updated') and not dry_run:
                        media = prop.get('Media', [])
                        if media and self._download_listing_photos(
                            listing.get('mls_number'), media
                        ):
                            photos_downloaded += 1

                    if result == 'created':
                        stats['created'] += 1
                    elif result == 'updated':
                        stats['updated'] += 1
                    elif result == 'deleted':
                        stats['deleted'] += 1
                    else:
                        stats['skipped'] += 1

                    # Commit every 10 records (was 100) so other writers
                    # (public contact form, event tracking) can grab the
                    # lock during brief gaps.
                    if not dry_run and (i + 1) % 10 == 0:
                        conn.commit()

                    if (i + 1) % 100 == 0:
                        logger.info(f"Processed {i + 1}/{len(properties)}...")

                except Exception as e:
                    logger.error(f"Error processing {prop.get('ListingId')}: {e}")
                    stats['errors'] += 1

            stats['photos_updated'] = self._photos_updated_count
            stats['photos_downloaded'] = photos_downloaded

            if not dry_run:
                conn.commit()

                self._save_sync_state({
                    'last_sync': datetime.now(timezone.utc).isoformat(),
                    'sync_type': 'incremental',
                    'records_synced': len(properties),
                })

                self._log_sync(conn, 'mlsgrid_incremental_sync', stats)
                conn.commit()

        finally:
            conn.close()

        stats['completed_at'] = datetime.now().isoformat()
        stats['api_stats'] = self.client.get_stats()
        if photos_downloaded:
            logger.info(f"Downloaded {photos_downloaded} primary photos during sync")
        return stats

    def sync_members(self, dry_run: bool = False) -> Dict[str, int]:
        """Sync agent/member records from Canopy MLS."""
        self._init_client()

        stats = {'fetched': 0, 'created': 0, 'updated': 0, 'errors': 0}

        try:
            members = self.client.fetch_agents(member_status='Active')
        except MLSGridAPIError as e:
            logger.error(f"Failed to fetch members: {e}")
            return stats

        stats['fetched'] = len(members)
        logger.info(f"Fetched {len(members)} member records from MLS Grid")

        if not members or dry_run:
            return stats

        conn = self._get_connection()
        try:
            for member_raw in members:
                try:
                    member = map_reso_to_member(member_raw)
                    self._upsert_agent(conn, member)
                    stats['created'] += 1
                except Exception as e:
                    logger.error(f"Error processing member: {e}")
                    stats['errors'] += 1

            conn.commit()
        finally:
            conn.close()

        return stats

    def test_connection(self) -> bool:
        """Test MLS Grid API connection."""
        self._init_client()
        return self.client.test_connection()


def print_stats(stats: Dict):
    """Print sync statistics."""
    print("\n" + "=" * 55)
    print("MLS GRID SYNC SUMMARY")
    print("=" * 55)
    print(f"  Sync type:      {stats.get('sync_type', 'unknown')}")
    print(f"  MLS source:     {stats.get('mls_source', 'unknown')}")
    print(f"  Fetched:        {stats.get('fetched', 0):,}")
    print(f"  Created:        {stats.get('created', 0):,}")
    print(f"  Updated:        {stats.get('updated', 0):,}")
    print(f"  Deleted:        {stats.get('deleted', 0):,}")
    print(f"  Skipped:        {stats.get('skipped', 0):,}")
    print(f"  Photos updated: {stats.get('photos_updated', 0):,}")
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
    """CLI entry point for MLS Grid sync."""
    parser = argparse.ArgumentParser(
        description="Sync Canopy MLS data from MLS Grid RESO API to myDREAMS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Test connection
    python -m apps.mlsgrid.sync_engine --test

    # Full sync of active listings
    python -m apps.mlsgrid.sync_engine --full --status Active

    # Incremental sync (only changes since last run)
    python -m apps.mlsgrid.sync_engine --incremental

    # Preview without database changes
    python -m apps.mlsgrid.sync_engine --full --dry-run

    # Sync agents
    python -m apps.mlsgrid.sync_engine --sync-members
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
    parser.add_argument('--status',
                        choices=['Active', 'Pending', 'Closed', 'Expired', 'Withdrawn', 'ActiveUnderContract', 'ComingSoon', 'Canceled'],
                        help='Filter by listing status')
    parser.add_argument('--types', nargs='+',
                        choices=['Residential', 'Land', 'Farm', 'Commercial Sale',
                                 'Residential Income', 'Manufactured In Park'],
                        help='Filter by property types')
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
    has_action = any([args.test, args.full, args.incremental, args.sync_members])
    if not has_action:
        parser.print_help()
        print("\nError: Must specify an action (--test, --full, --incremental, --sync-members)")
        return 1

    load_env()

    engine = MLSGridSyncEngine()

    # Test mode
    if args.test:
        success = engine.test_connection()
        return 0 if success else 1

    # Member sync
    if args.sync_members:
        stats = engine.sync_members(dry_run=args.dry_run)
        print(f"Members synced: {stats}")
        return 0

    # Property sync
    if args.full:
        stats = engine.run_full_sync(
            status=args.status,
            property_types=args.types,
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
