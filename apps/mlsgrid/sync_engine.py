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

        # Ensure database tables exist.
        # On PostgreSQL, schema is managed by scripts/migrate_to_postgres.py.
        # On SQLite, _ensure_tables() creates tables if missing.
        from src.core.pg_adapter import is_postgres
        if not is_postgres():
            self._ensure_tables()
        else:
            # Just cache known listing columns
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'listings'"
                )
                self._known_listing_columns = {row[0] for row in cursor.fetchall()}
            finally:
                conn.close()

    def _get_connection(self):
        """Get a database connection (PostgreSQL if DATABASE_URL set, else SQLite)."""
        from src.core.pg_adapter import get_db
        return get_db(str(self.db_path))

    def _ensure_tables(self):
        """Ensure required tables and indexes exist."""
        conn = self._get_connection()
        try:
            # Cache known listing columns for dynamic schema expansion
            from src.core.pg_adapter import is_postgres
            if is_postgres():
                cursor = conn.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'listings'"
                )
                self._known_listing_columns = {row[0] for row in cursor.fetchall()}
            else:
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
                    id SERIAL PRIMARY KEY,
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
                    id SERIAL PRIMARY KEY,
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
        conn,
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

    def _record_changes(self, conn, changes: List[Dict]):
        """Insert change records into property_changes table.

        Part of the caller's transaction — does NOT commit or rollback on
        its own. Previously this method committed per-change, which
        silently destroyed the outer loop's per-row SAVEPOINT and caused
        "savepoint does not exist" errors on every row with a change
        (run_full_sync and run_incremental_sync, 2026-04-24). The
        commit/rollback also defeats the invariant-7 per-row atomicity
        guarantee that the enclosing savepoint provides — a failed change
        record should roll back with the whole row, not commit piecemeal.

        On exception we simply propagate; the outer savepoint rollback
        handles the cleanup and the outer commit handles durability.
        Debug-level logging keeps the original visibility.
        """
        for change in changes:
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
        conn,
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
            # Compare new photos_change_timestamp with stored value. If
            # unchanged AND the stored photos array is actually complete,
            # skip photo fields to preserve local photo paths.
            #
            # The "complete" check matters because the 2026-04-20 PRD
            # incident left 1,869 listings with photos=[primary] only
            # (gallery lost during a prior migration bug). With only the
            # timestamp check, those rows would never refresh — the
            # optimisation dutifully preserved a broken state forever.
            skip_photo_fields = False
            new_photo_ts = listing.get('photos_change_timestamp')
            old_photo_ts = existing_dict.get('photos_change_timestamp')
            # PHOTO_PIPELINE_SPEC gallery_status is the source of truth
            # for "is this row's photo state trustworthy." photo_local_path
            # is deprecated and will be retired.
            is_photo_ready = existing_dict.get('gallery_status') == 'ready'

            existing_photos_len = 0
            existing_photos_raw = existing_dict.get('photos')
            if existing_photos_raw:
                try:
                    import json as _json_pp
                    if isinstance(existing_photos_raw, str):
                        existing_photos_len = len(_json_pp.loads(existing_photos_raw))
                    elif isinstance(existing_photos_raw, list):
                        existing_photos_len = len(existing_photos_raw)
                except Exception:
                    pass
            expected_count = existing_dict.get('photo_count') or 0
            # Allow a small tolerance (photo_count rarely lies by more than a couple).
            photos_complete = existing_photos_len >= max(1, expected_count - 1)

            if (new_photo_ts and old_photo_ts and new_photo_ts == old_photo_ts
                    and is_photo_ready and photos_complete):
                skip_photo_fields = True
                logger.debug(
                    f"Photos unchanged for {mls_number} "
                    f"(ts={new_photo_ts}, len={existing_photos_len}/{expected_count}), "
                    f"preserving local paths"
                )
            elif new_photo_ts and old_photo_ts and new_photo_ts == old_photo_ts and not is_photo_ready:
                logger.debug(
                    f"Photos unchanged for {mls_number} but gallery not ready, refreshing URLs"
                )
            elif new_photo_ts and old_photo_ts and new_photo_ts == old_photo_ts and not photos_complete:
                logger.info(
                    f"Photos array truncated for {mls_number} "
                    f"(have {existing_photos_len}, expected {expected_count}); refreshing"
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

            # Gallery gate: any change in photo content means the local
            # gallery is stale. Flip the row back to 'pending' so the
            # nightly/post-sync backfill redownloads before it's shown
            # on the public site. Only applies when photo fields are in
            # this update (timestamp-change path; skip_photo_fields means
            # nothing changed so status stays as-is).
            if not skip_photo_fields and (
                'photos' in update_data or 'primary_photo' in update_data
                or 'photo_count' in update_data
                or 'photos_change_timestamp' in update_data
            ):
                update_data['gallery_status'] = 'pending'

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
            # New Canopy listings always start 'pending' — the public
            # site won't show them until the gallery is downloaded.
            listing.setdefault('gallery_status', 'pending')

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

    def _download_listing_photos(self, conn, mls_number: str, media_list: list) -> bool:
        """Download primary + gallery from Media array during sync.

        Uses fresh MediaURLs from the replication response (zero additional
        API calls). Called only when photos changed; the gallery gate has
        already set gallery_status='pending' before this runs. On success
        here, the gate flips to 'ready' so new listings appear on the public
        site within the same sync cycle.

        The photo UPDATE MUST run on the caller's batch connection (`conn`)
        — NOT a fresh connection. A fresh connection cannot see the just-
        INSERTed row from _upsert_listing (uncommitted) and would silently
        UPDATE zero rows, OR block on a row lock and hit statement_timeout.
        That was the root cause of the "canceling statement due to
        statement timeout" errors observed in mlsgrid-sync.log 2026-04-23.

        Follows PHOTO_PIPELINE_SPEC invariants:
          * invariant #1: photos[] contains only local /api/public/photos/
            paths on success (no CDN pollution — matches the fix shipped
            in gallery_backfill_strict on 2026-04-23).
          * invariant #2: photo_verified_at stamped only on ready state.
          * invariant #3 exception: sync writes gallery_status='ready' only
            AFTER verifying local files on disk (see DECISIONS.md D3).
          * Readiness tolerates ~10% broken photos (same rule as backfill)
            so a single chronically-404 upstream URL can't strand the row.

        Uses apps.photos.downloader.download_photo() rather than inline
        requests.get(..., stream=True) — the stream path caused CLOSE_WAIT
        hangs on PRD 2026-04-20 before being hardened.

        Returns True if primary is local + enough gallery downloaded to
        be considered ready. False otherwise (gate stays 'pending' and
        the gallery worker retries later).
        """
        if not media_list or not mls_number:
            return False

        PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

        primary_url, all_urls, count = extract_photos(media_list)
        if not all_urls:
            return False

        # Defer to the single owner of photo HTTP: apps.photos.downloader.
        # Same timeout tuple, same retry policy, same skip-on-failure
        # contract as the gallery worker — one HTTP path, one class of bug.
        from apps.photos.downloader import download_photo, detect_extension
        from apps.photos import storage

        # Per-request pacing to stay under MLS Grid's 2 rps ceiling on
        # media.mlsgrid.com. 0.56s gap => ~1.8 rps, matching the
        # gallery_backfill_strict worker's --max-rps 1.8 setting.
        #
        # Known gap (deferred): sync and gallery_backfill run in separate
        # processes with independent pacing. Together they can reach up to
        # ~3.6 rps briefly. Proper fix: move MLSGridThrottle into a shared
        # cross-process file-locked module. Tracked as a Phase 4+ refactor.
        import time as _time_mod
        _RPS_GAP = 1.0 / 1.8  # ~0.56s

        local_paths: List[str] = []
        errors = 0
        last_req_at = 0.0

        for idx, photo_url in enumerate(all_urls):
            ext = detect_extension(photo_url)
            filename = f"{mls_number}{ext}" if idx == 0 else f"{mls_number}_{idx:02d}{ext}"
            filepath = PHOTOS_DIR / filename

            if filepath.exists() and filepath.stat().st_size > 500:
                local_paths.append(f"/api/public/photos/mlsgrid/{filename}")
                continue

            # Pace the HTTP calls. Wait if the previous request was too recent.
            since_last = _time_mod.monotonic() - last_req_at
            if since_last < _RPS_GAP:
                _time_mod.sleep(_RPS_GAP - since_last)

            data = download_photo(photo_url)
            last_req_at = _time_mod.monotonic()

            if not data:
                # Don't pollute photos[] with an expired CDN URL — see
                # invariant #1 and the 2026-04-23 CDN-pollution fix.
                errors += 1
                continue

            storage.save_atomic(PHOTOS_DIR, filename, data)
            local_paths.append(f"/api/public/photos/mlsgrid/{filename}")

        if not local_paths:
            return False

        primary_local = local_paths[0]
        # Same tolerance as gallery_backfill_strict: a single chronically
        # dead photo can't strand the listing forever.
        broken_allowed = max(3, count // 10) if count else 3
        min_required = max(1, count - broken_allowed) if count else 1
        gallery_ready = len(local_paths) >= min_required

        import json as _json
        # Write on the CALLER'S connection so this UPDATE is part of the
        # same transaction/savepoint as the upsert — no row-lock contention,
        # no separate-connection visibility gap. Do NOT commit here; the
        # outer loop owns commit boundaries (every 10 rows).
        if gallery_ready:
            conn.execute(
                "UPDATE listings SET photos = ?, primary_photo = ?, "
                "photo_count = ?, photo_verified_at = CURRENT_TIMESTAMP, "
                "gallery_status = 'ready' "
                "WHERE mls_source = ? AND mls_number = ?",
                [_json.dumps(local_paths), primary_local, count,
                 self.mls_source, mls_number]
            )
        else:
            # Partial download — record what we have but keep pending;
            # the gallery worker's next pass will retry the gaps.
            conn.execute(
                "UPDATE listings SET photos = ?, primary_photo = ?, "
                "photo_count = ? "
                "WHERE mls_source = ? AND mls_number = ?",
                [_json.dumps(local_paths), primary_local, count,
                 self.mls_source, mls_number]
            )

        if errors:
            logger.info(
                "sync-download %s: %d/%d local (%d broken); ready=%s",
                mls_number, len(local_paths), count, errors, gallery_ready,
            )
        return gallery_ready

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
        conn,
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
            # DO NOT use expand_media=True here — it loads 28K Media arrays
            # into memory (~1.2 GB) and causes the VPS to swap/stall.
            # Photos are handled separately by apps/photos/cron.py which
            # fetches Media per-listing (small memory footprint).
            properties = self.client.fetch_properties(
                status=status,
                property_types=property_types,
                max_records=max_records,
                include_deleted=False,
                expand_media=False,
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
                # PHOTO_PIPELINE_SPEC invariant #7: each row is its own
                # SAVEPOINT inside the batch transaction. One row's failure
                # no longer poisons the previous up-to-9 siblings committed
                # in the same batch — which was the cascade pattern
                # documented in docs/incidents/20260324-navica-feed-stopped.md.
                savepoint = f"sync_row_{i}"
                try:
                    conn.execute(f"SAVEPOINT {savepoint}")

                    listing = map_reso_to_listing(prop, self.mls_source)

                    # Ensure schema has all columns this listing needs
                    if set(listing.keys()) - self._known_listing_columns:
                        self._known_listing_columns = ensure_listing_columns(
                            conn, listing, self._known_listing_columns
                        )
                        conn.commit()
                        # A fresh transaction starts on the next write; the
                        # old savepoint name is scoped to the closed tx, so
                        # reopen one for this row.
                        conn.execute(f"SAVEPOINT {savepoint}")

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

                    # Download photos for listings that need them.
                    # See docs/DECISIONS.md D3: photos download DURING sync.
                    # Check REGARDLESS of upsert result — a listing can have
                    # unchanged data but missing photos (e.g., after migration).
                    # Passes `conn` so the photo UPDATE runs in the same
                    # transaction as the upsert — no row-lock contention.
                    # Use storage.primary_exists() so we don't re-download
                    # when the primary is on disk as .jpeg (or .png/.webp)
                    # — previously the gate hardcoded .jpg and fired download
                    # on ~4,000 listings unnecessarily, causing the sync to
                    # drag 5+ hours instead of minutes (observed 2026-04-24).
                    if not dry_run and result != 'deleted':
                        media = prop.get('Media', [])
                        mls_num = listing.get('mls_number')
                        if mls_num and media:
                            from apps.photos import storage as _storage
                            if not _storage.primary_exists(self.mls_source, mls_num):
                                if self._download_listing_photos(conn, mls_num, media):
                                    self._photos_updated_count += 1

                    conn.execute(f"RELEASE SAVEPOINT {savepoint}")

                    # Commit every 10 records and yield briefly
                    if not dry_run and (i + 1) % 10 == 0:
                        conn.commit()
                        import time as _time_mod
                        _time_mod.sleep(0.05)  # 50ms yield

                    if (i + 1) % 100 == 0:
                        logger.info(f"Processed {i + 1}/{len(properties)}...")

                except Exception as e:
                    logger.error(f"Error processing {prop.get('ListingId')}: {e}")
                    stats['errors'] += 1
                    # Rollback JUST this row's savepoint, not the whole
                    # batch — sibling rows already committed in this
                    # transaction survive.
                    try:
                        conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                        conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                    except Exception:
                        # Savepoint already released or tx already closed;
                        # fall back to full rollback rather than hang the tx.
                        try:
                            conn.rollback()
                        except Exception:
                            pass

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
                expand_media=True,
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
                # PHOTO_PIPELINE_SPEC invariant #7: per-row savepoint.
                # See run_full_sync for the fuller comment and rationale
                # (20260324 incident, 946-row cascade).
                savepoint = f"sync_row_{i}"
                try:
                    conn.execute(f"SAVEPOINT {savepoint}")

                    listing = map_reso_to_listing(prop, self.mls_source)

                    # Ensure schema has all columns this listing needs
                    if set(listing.keys()) - self._known_listing_columns:
                        self._known_listing_columns = ensure_listing_columns(
                            conn, listing, self._known_listing_columns
                        )
                        conn.commit()
                        conn.execute(f"SAVEPOINT {savepoint}")

                    result = self._upsert_listing(
                        conn, listing, raw_prop=prop, dry_run=dry_run
                    )

                    # Download all photos for new or photo-changed listings.
                    # Media data is already in the replication response
                    # ($expand=Media), so this costs zero additional API calls.
                    # Passes `conn` so the photo UPDATE runs in the same
                    # transaction as the upsert — no row-lock contention.
                    # storage.primary_exists() checks all valid extensions
                    # (.jpg/.jpeg/.png/.webp) so we don't trigger spurious
                    # redownloads for the ~4k listings whose primary is .jpeg.
                    if not dry_run and result != 'deleted':
                        media = prop.get('Media', [])
                        mls_num = listing.get('mls_number')
                        if mls_num and media:
                            from apps.photos import storage as _storage
                            if not _storage.primary_exists(self.mls_source, mls_num):
                                if self._download_listing_photos(conn, mls_num, media):
                                    photos_downloaded += 1

                    if result == 'created':
                        stats['created'] += 1
                    elif result == 'updated':
                        stats['updated'] += 1
                    elif result == 'deleted':
                        stats['deleted'] += 1
                    else:
                        stats['skipped'] += 1

                    conn.execute(f"RELEASE SAVEPOINT {savepoint}")

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
                    try:
                        conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                        conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                    except Exception:
                        try:
                            conn.rollback()
                        except Exception:
                            pass

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
