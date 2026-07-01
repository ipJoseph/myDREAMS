"""
Hive (SourceRE) Sync Engine — Mountain Lakes Board of REALTORS®

Replaces the Navica nav26 feed as of 2026-06-30. Writes to the same
listings table with mls_source='MountainLakesMLS' so all downstream
code (dashboard, API, public site) remains unaware of the vendor change.

Key improvements over nav26:
- Server-side APIModificationTimestamp filtering (true incrementals)
- Explicit DeletedInSource deletion signal (48-hour window)
- RESO OData standard — same pattern as Canopy/MLS Grid
- Hosted photo CDN (cdn.sourceredb.com), downloaded locally

Usage:
    python -m apps.hive.sync_engine --test
    python -m apps.hive.sync_engine --full --status Active
    python -m apps.hive.sync_engine --incremental
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
STATE_FILE = PROJECT_ROOT / 'data' / 'hive_sync_state.json'

sys.path.insert(0, str(PROJECT_ROOT))

from apps.hive.client import HiveClient, HiveAuthError, HiveAPIError
from apps.navica.field_mapper import (
    map_reso_to_listing,
    map_reso_to_member,
    ensure_listing_columns,
)

MLS_SOURCE = 'MountainLakesMLS'

# Photo fields — skip during update when photos haven't changed
PHOTO_FIELDS = {
    'primary_photo', 'photos', 'photo_count', 'photo_source',
    'photo_verified_at', 'photo_review_status', 'media_keys',
}


def load_env():
    env_path = PROJECT_ROOT / '.env'
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip().strip('"\''))


class HiveSyncEngine:
    """
    Sync engine for Mountain Lakes MLS data via Hive (SourceRE).

    Lifecycle per sync run:
    1. Fetch from SourceRE API (full or incremental)
    2. Map RESO fields → listings table via shared field_mapper
    3. Apply WNC scope filter (is_in_scope)
    4. Upsert with photo preservation logic
    5. Handle DeletedInSource deletions
    6. Track sync state for next incremental
    """

    def __init__(self, db_path: str = None):
        self.mls_source = MLS_SOURCE
        self.client: Optional[HiveClient] = None

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
        from src.core.pg_adapter import get_db
        return get_db()

    def _init_client(self):
        if self.client is None:
            self.client = HiveClient.from_env()

    # ---------------------------------------------------------------
    # Sync state
    # ---------------------------------------------------------------

    def _load_sync_state(self) -> Dict:
        if STATE_FILE.exists():
            with open(STATE_FILE) as f:
                return json.load(f)
        return {}

    def _save_sync_state(self, state: Dict):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)

    # ---------------------------------------------------------------
    # Change detection
    # ---------------------------------------------------------------

    def _detect_changes(self, conn, listing: Dict, existing: Optional[Dict]) -> List[Dict]:
        if not existing:
            return []

        changes = []
        now = datetime.now().isoformat()
        listing_id = listing['id']

        old_price = existing.get('list_price')
        new_price = listing.get('list_price')
        if old_price and new_price and old_price != new_price:
            pct = round((new_price - old_price) / old_price * 100, 1)
            changes.append({
                'listing_id': listing_id,
                'mls_number': listing['mls_number'],
                'change_type': 'price',
                'old_value': str(old_price),
                'new_value': str(new_price),
                'pct_change': pct,
                'detected_at': now,
            })
            logger.info(f"Price change: {listing['mls_number']} ${old_price:,} -> ${new_price:,} ({pct:+.1f}%)")

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
            logger.info(f"Status change: {listing['mls_number']} {old_status} -> {new_status}")

        return changes

    def _record_changes(self, conn, changes: List[Dict]):
        for change in changes:
            try:
                conn.execute(
                    'INSERT INTO property_changes '
                    '(property_id, change_type, old_value, new_value, change_percent, detected_at) '
                    'VALUES (?, ?, ?, ?, ?, ?)',
                    [change['listing_id'], change['change_type'], change['old_value'],
                     change['new_value'], change.get('pct_change'), change['detected_at']],
                )
            except Exception as e:
                logger.debug(f"Could not record change: {e}")

    # ---------------------------------------------------------------
    # Upsert
    # ---------------------------------------------------------------

    def _upsert_listing(
        self,
        conn,
        listing: Dict,
        raw_prop: Dict = None,
        dry_run: bool = False,
    ) -> str:
        """
        Insert or update a listing. Returns 'created', 'updated', 'deleted', or 'skipped'.
        """
        mls_number = listing.get('mls_number')
        if not mls_number:
            return 'skipped'

        existing = conn.execute(
            "SELECT * FROM listings WHERE mls_source = ? AND mls_number = ?",
            [self.mls_source, mls_number],
        ).fetchone()
        existing_dict = dict(existing) if existing else None

        # DeletedInSource handling — SourceRE signals deletion this way.
        # Field is null for normal records; only True on deleted ones.
        if raw_prop and raw_prop.get('DeletedInSource') is True:
            if existing_dict:
                if dry_run:
                    return 'deleted'
                now = datetime.now().isoformat()
                conn.execute(
                    "UPDATE listings SET status = 'DELETED', idx_opt_in = 0, "
                    "updated_at = ? WHERE id = ?",
                    [now, existing_dict['id']],
                )
                logger.info(f"Deleted: {mls_number} (DeletedInSource, was {existing_dict.get('status')})")
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
            return 'deleted'

        changes = self._detect_changes(conn, listing, existing_dict)
        if dry_run:
            return 'created' if not existing else 'updated'

        if changes:
            self._record_changes(conn, changes)

        now = datetime.now().isoformat()

        if existing:
            # Skip photo fields if photos haven't changed
            skip_photo_fields = False
            new_photo_ts = listing.get('photos_change_timestamp')
            old_photo_ts = existing_dict.get('photos_change_timestamp')
            is_photo_ready = existing_dict.get('gallery_status') == 'ready'
            existing_photos_len = 0
            raw_photos = existing_dict.get('photos')
            if raw_photos:
                try:
                    photos_list = raw_photos if isinstance(raw_photos, list) else json.loads(raw_photos)
                    existing_photos_len = len(photos_list)
                except Exception:
                    pass
            expected_count = existing_dict.get('photo_count') or 0
            photos_complete = existing_photos_len >= max(1, expected_count - 1)

            if (new_photo_ts and old_photo_ts and new_photo_ts == old_photo_ts
                    and is_photo_ready and photos_complete):
                skip_photo_fields = True

            update_data = {
                k: v for k, v in listing.items()
                if v is not None
                and k not in ('id', 'captured_at')
                and not (skip_photo_fields and k in PHOTO_FIELDS)
            }
            update_data['updated_at'] = now

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

            if update_data:
                set_clause = ", ".join([f"{k} = ?" for k in update_data])
                values = list(update_data.values()) + [existing_dict['id']]
                conn.execute(f"UPDATE listings SET {set_clause} WHERE id = ?", values)
            return 'updated'
        else:
            listing['captured_at'] = now
            listing['updated_at'] = now
            listing.setdefault('gallery_status', 'pending')
            insert_data = {k: v for k, v in listing.items() if v is not None}
            columns = list(insert_data.keys())
            placeholders = ', '.join(['?' for _ in columns])
            conn.execute(
                f"INSERT INTO listings ({', '.join(columns)}) VALUES ({placeholders})",
                list(insert_data.values()),
            )
            return 'created'

    # ---------------------------------------------------------------
    # Core sync methods
    # ---------------------------------------------------------------

    def run_full_sync(
        self,
        status: str = None,
        dry_run: bool = False,
        max_records: int = None,
    ) -> Dict[str, Any]:
        """Full sync — fetch all current ML listings (no timestamp filter)."""
        self._init_client()

        stats = {
            'sync_type': 'full', 'started_at': datetime.now().isoformat(),
            'fetched': 0, 'created': 0, 'updated': 0, 'deleted': 0,
            'skipped': 0, 'out_of_scope': 0, 'errors': 0,
        }

        logger.info(f"Starting Hive full sync (status={status or 'all'}, dry_run={dry_run})")

        try:
            properties = self.client.fetch_properties(status=status, max_records=max_records)
        except HiveAPIError as e:
            logger.error(f"Fetch failed: {e}")
            stats['errors'] += 1
            return stats

        stats['fetched'] = len(properties)
        logger.info(f"Fetched {len(properties)} properties")

        if not properties:
            return stats

        conn = self._get_connection()
        try:
            from src.core.regions import is_in_scope

            for i, prop in enumerate(properties):
                try:
                    listing = map_reso_to_listing(prop, self.mls_source)

                    if not is_in_scope(listing.get('county')):
                        stats['out_of_scope'] += 1
                        continue

                    # Schema expansion commits (releases any open savepoint),
                    # so it must happen BEFORE setting the per-row savepoint.
                    new_cols = set(listing.keys()) - self._known_listing_columns
                    if new_cols:
                        self._known_listing_columns = ensure_listing_columns(
                            conn, listing, self._known_listing_columns
                        )
                        conn.commit()

                    conn.execute("SAVEPOINT row_sync")
                    result = self._upsert_listing(conn, listing, raw_prop=prop, dry_run=dry_run)
                    stats[result] = stats.get(result, 0) + 1
                    conn.execute("RELEASE SAVEPOINT row_sync")

                    if (i + 1) % 100 == 0:
                        logger.info(f"Processed {i + 1}/{len(properties)}...")
                        if not dry_run:
                            conn.commit()

                except Exception as e:
                    logger.error(f"Error processing {prop.get('ListingId')}: {e}")
                    stats['errors'] += 1
                    try:
                        conn.execute("ROLLBACK TO SAVEPOINT row_sync")
                        conn.execute("RELEASE SAVEPOINT row_sync")
                    except Exception:
                        conn.rollback()

            if not dry_run:
                conn.commit()
                self._save_sync_state({
                    'last_sync': datetime.now(timezone.utc).isoformat(),
                    'sync_type': 'full',
                    'status_filter': status,
                    'records_synced': len(properties),
                })

        finally:
            conn.close()

        stats['completed_at'] = datetime.now().isoformat()
        stats['api_stats'] = self.client.get_stats()
        return stats

    def run_incremental_sync(
        self,
        dry_run: bool = False,
        max_records: int = None,
    ) -> Dict[str, Any]:
        """
        Incremental sync — server-side APIModificationTimestamp filter.

        Unlike Navica nav26 (which had to fetch all records and filter client-side),
        Hive/SourceRE supports true server-side timestamp filtering. This means
        incremental runs fetch only genuinely changed records.
        """
        self._init_client()

        stats = {
            'sync_type': 'incremental', 'started_at': datetime.now().isoformat(),
            'fetched': 0, 'created': 0, 'updated': 0, 'deleted': 0,
            'skipped': 0, 'out_of_scope': 0, 'errors': 0,
        }

        state = self._load_sync_state()
        modified_since = None

        if 'last_sync' in state:
            modified_since = datetime.fromisoformat(state['last_sync'])
            logger.info(f"Incremental sync: fetching records modified since {modified_since}")
        else:
            logger.warning("No previous sync state. Falling back to last 24 hours.")
            modified_since = datetime.now(timezone.utc) - timedelta(hours=24)

        try:
            # include_deleted=True so we catch DeletedInSource signals
            properties = self.client.fetch_properties(
                modified_since=modified_since,
                include_deleted=True,
                max_records=max_records,
            )
        except HiveAPIError as e:
            logger.error(f"Fetch failed: {e}")
            stats['errors'] += 1
            return stats

        stats['fetched'] = len(properties)
        logger.info(f"Fetched {stats['fetched']} changed properties")

        if not properties:
            logger.info("No changes since last sync")
            if not dry_run:
                self._save_sync_state({
                    'last_sync': datetime.now(timezone.utc).isoformat(),
                    'sync_type': 'incremental',
                    'records_synced': 0,
                })
            return stats

        conn = self._get_connection()
        try:
            from src.core.regions import is_in_scope

            for i, prop in enumerate(properties):
                try:
                    listing = map_reso_to_listing(prop, self.mls_source)

                    if not is_in_scope(listing.get('county')):
                        stats['out_of_scope'] += 1
                        continue

                    new_cols = set(listing.keys()) - self._known_listing_columns
                    if new_cols:
                        self._known_listing_columns = ensure_listing_columns(
                            conn, listing, self._known_listing_columns
                        )
                        conn.commit()

                    conn.execute("SAVEPOINT row_sync")
                    result = self._upsert_listing(conn, listing, raw_prop=prop, dry_run=dry_run)
                    stats[result] = stats.get(result, 0) + 1
                    conn.execute("RELEASE SAVEPOINT row_sync")

                    if (i + 1) % 100 == 0:
                        logger.info(f"Processed {i + 1}/{stats['fetched']}...")
                        if not dry_run:
                            conn.commit()

                except Exception as e:
                    logger.error(f"Error processing {prop.get('ListingId')}: {e}")
                    stats['errors'] += 1
                    try:
                        conn.execute("ROLLBACK TO SAVEPOINT row_sync")
                        conn.execute("RELEASE SAVEPOINT row_sync")
                    except Exception:
                        conn.rollback()

            if not dry_run:
                conn.commit()
                self._save_sync_state({
                    'last_sync': datetime.now(timezone.utc).isoformat(),
                    'sync_type': 'incremental',
                    'records_synced': stats['fetched'],
                })

        finally:
            conn.close()

        stats['completed_at'] = datetime.now().isoformat()
        stats['api_stats'] = self.client.get_stats()
        return stats

    def sync_members(self, dry_run: bool = False) -> Dict:
        """Sync Mountain Lakes agent/member records."""
        self._init_client()
        stats = {'fetched': 0, 'created': 0, 'updated': 0, 'errors': 0}

        try:
            members = self.client.fetch_agents()
        except HiveAPIError as e:
            logger.error(f"Member fetch failed: {e}")
            return stats

        stats['fetched'] = len(members)
        if not members or dry_run:
            return stats

        conn = self._get_connection()
        try:
            for m in members:
                try:
                    agent = map_reso_to_member(m)
                    if not agent.get('member_key'):
                        continue

                    existing = conn.execute(
                        "SELECT id FROM agents WHERE member_key = ?",
                        [agent['member_key']],
                    ).fetchone()

                    now = datetime.now().isoformat()
                    if existing:
                        agent['updated_at'] = now
                        set_clause = ", ".join(f"{k} = ?" for k in agent)
                        conn.execute(
                            f"UPDATE agents SET {set_clause} WHERE member_key = ?",
                            list(agent.values()) + [agent['member_key']],
                        )
                        stats['updated'] += 1
                    else:
                        agent['created_at'] = now
                        agent['updated_at'] = now
                        cols = list(agent.keys())
                        conn.execute(
                            f"INSERT INTO agents ({', '.join(cols)}) "
                            f"VALUES ({', '.join(['?' for _ in cols])})",
                            list(agent.values()),
                        )
                        stats['created'] += 1
                except Exception as e:
                    logger.debug(f"Member upsert error: {e}")
                    stats['errors'] += 1

            conn.commit()
        finally:
            conn.close()

        return stats


def print_stats(stats: Dict):
    logger.info(
        f"Sync complete: {stats.get('fetched', 0)} fetched, "
        f"{stats.get('created', 0)} created, "
        f"{stats.get('updated', 0)} updated, "
        f"{stats.get('deleted', 0)} deleted, "
        f"{stats.get('out_of_scope', 0)} out-of-scope, "
        f"{stats.get('errors', 0)} errors"
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Hive (Mountain Lakes) sync engine")
    parser.add_argument('--test', action='store_true', help='Test API connection')
    parser.add_argument('--incremental', action='store_true', help='Incremental sync')
    parser.add_argument('--full', action='store_true', help='Full sync')
    parser.add_argument('--status', help='Status filter for full sync')
    parser.add_argument('--dry-run', action='store_true', help='Preview without DB writes')
    parser.add_argument('--max-records', type=int, help='Limit records fetched')
    args = parser.parse_args()

    load_env()
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    engine = HiveSyncEngine()

    if args.test:
        engine._init_client()
        engine.client.test_connection()
    elif args.full:
        stats = engine.run_full_sync(status=args.status, dry_run=args.dry_run, max_records=args.max_records)
        print_stats(stats)
    elif args.incremental:
        stats = engine.run_incremental_sync(dry_run=args.dry_run, max_records=args.max_records)
        print_stats(stats)
    else:
        parser.print_help()
