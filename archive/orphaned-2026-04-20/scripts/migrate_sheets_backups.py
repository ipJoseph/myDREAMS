"""
Migrate historical Google Sheets backup tabs to contact_snapshots table.

Reads each backup tab (named YYMMDD.HHMM) from the backup spreadsheet,
parses rows into the snapshot schema, and batch inserts them.

Idempotent: skips tabs whose timestamp already exists in the database.

Usage:
    python3 scripts/migrate_sheets_backups.py [--dry-run] [--limit N]
"""

import os
import sys
import time
import argparse
import re
import logging
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "apps" / "fub-to-sheets"))

from dotenv import load_dotenv
load_dotenv()

import gspread
from google.oauth2.service_account import Credentials

from src.core.database import DREAMSDatabase
from fub_to_sheets_v2 import (
    CONTACTS_HEADER, _HEADER_TO_SNAPSHOT_COL,
    _SNAPSHOT_INT_COLS, _SNAPSHOT_FLOAT_COLS,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BACKUP_SHEET_ID = os.getenv(
    "GOOGLE_BACKUP_SHEET_ID",
    "1dR5DqYxFc6TG79__1TOEQcMDKi8XUwfaDNS1GE9qwKw"
)

# Pattern for backup tab names: YYMMDD.HHMM or YYMMDD.HHMM.N
TAB_NAME_RE = re.compile(r'^(\d{6})\.(\d{4})(?:\.\d+)?$')


def parse_tab_timestamp(tab_name: str) -> str:
    """Convert tab name like '250103.1430' to ISO timestamp."""
    m = TAB_NAME_RE.match(tab_name)
    if not m:
        raise ValueError(f"Cannot parse tab name: {tab_name}")
    date_part, time_part = m.group(1), m.group(2)
    # YYMMDD -> 20YY-MM-DD
    dt = datetime(
        year=2000 + int(date_part[:2]),
        month=int(date_part[2:4]),
        day=int(date_part[4:6]),
        hour=int(time_part[:2]),
        minute=int(time_part[2:4]),
        tzinfo=timezone.utc,
    )
    return dt.isoformat()


def get_existing_snapshot_timestamps(db: DREAMSDatabase) -> set:
    """Get all distinct snapshot_at values already in the database."""
    with db._get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT snapshot_at FROM contact_snapshots"
        ).fetchall()
        return {row[0] for row in rows}


def convert_row_to_snapshot(header_idx: dict, row: list, snapshot_at: str) -> dict:
    """Convert a single Sheets row to a snapshot dict."""
    contact_id = str(row[header_idx["id"]]) if header_idx.get("id") is not None and row[header_idx["id"]] else None
    if not contact_id:
        return None

    snap = {"contact_id": contact_id, "snapshot_at": snapshot_at, "sync_id": None}

    for header_name, db_col in _HEADER_TO_SNAPSHOT_COL.items():
        if db_col == "contact_id":
            continue
        col_idx = header_idx.get(header_name)
        if col_idx is None or col_idx >= len(row):
            continue
        val = row[col_idx]

        if db_col in _SNAPSHOT_INT_COLS:
            if val == "✓":
                val = 1
            else:
                try:
                    val = int(val) if val else 0
                except (ValueError, TypeError):
                    val = 0
        elif db_col in _SNAPSHOT_FLOAT_COLS:
            try:
                val = float(val) if val else 0.0
            except (ValueError, TypeError):
                val = 0.0
        elif val == "":
            val = None

        snap[db_col] = val

    return snap


def migrate(dry_run: bool = False, limit: int = 0):
    """Run the migration."""
    # Connect to Google Sheets
    service_account_file = os.getenv(
        "GOOGLE_SERVICE_ACCOUNT_FILE",
        str(PROJECT_ROOT / "apps" / "fub-to-sheets" / "service_account.json"),
    )
    creds = Credentials.from_service_account_file(
        service_account_file,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ],
    )
    gc = gspread.authorize(creds)
    backup_sh = gc.open_by_key(BACKUP_SHEET_ID)

    # Connect to database
    db_path = os.getenv("DREAMS_DB_PATH", str(PROJECT_ROOT / "data" / "dreams.db"))
    db = DREAMSDatabase(db_path)

    # Get existing timestamps to skip
    existing_timestamps = get_existing_snapshot_timestamps(db)
    logger.info(f"Found {len(existing_timestamps)} existing snapshot timestamps in DB")

    # Get all backup tabs
    worksheets = backup_sh.worksheets()
    backup_tabs = [ws for ws in worksheets if TAB_NAME_RE.match(ws.title)]
    backup_tabs.sort(key=lambda ws: ws.title)

    logger.info(f"Found {len(backup_tabs)} backup tabs to process")

    if limit > 0:
        backup_tabs = backup_tabs[:limit]
        logger.info(f"Limiting to {limit} tabs")

    imported = 0
    skipped = 0
    errors = 0

    for i, ws in enumerate(backup_tabs):
        try:
            snapshot_at = parse_tab_timestamp(ws.title)
        except ValueError as e:
            logger.warning(f"Skipping tab '{ws.title}': {e}")
            errors += 1
            continue

        if snapshot_at in existing_timestamps:
            logger.debug(f"Skipping '{ws.title}' (already imported)")
            skipped += 1
            continue

        logger.info(f"[{i+1}/{len(backup_tabs)}] Importing '{ws.title}' -> {snapshot_at}")

        if dry_run:
            imported += 1
            continue

        try:
            all_values = ws.get_all_values()
            if len(all_values) < 2:
                logger.warning(f"Tab '{ws.title}' has no data rows, skipping")
                skipped += 1
                continue

            # First row is header; build index from actual header
            actual_header = all_values[0]
            header_idx = {name: i for i, name in enumerate(actual_header)}

            snapshots = []
            for row in all_values[1:]:
                snap = convert_row_to_snapshot(header_idx, row, snapshot_at)
                if snap:
                    snapshots.append(snap)

            if snapshots:
                db.insert_contact_snapshots_batch(snapshots)
                logger.info(f"  Inserted {len(snapshots)} snapshots")

            imported += 1

            # Rate limit: ~60 reads/min, each tab is 1 read
            if (i + 1) % 50 == 0:
                logger.info("Rate limit pause (10s)...")
                time.sleep(10)
            else:
                time.sleep(1.2)

        except Exception as e:
            logger.error(f"Error importing tab '{ws.title}': {e}")
            errors += 1

    logger.info(f"Migration complete: {imported} imported, {skipped} skipped, {errors} errors")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate Sheets backup tabs to SQLite")
    parser.add_argument("--dry-run", action="store_true", help="Parse tabs but don't insert")
    parser.add_argument("--limit", type=int, default=0, help="Max tabs to process (0=all)")
    args = parser.parse_args()

    migrate(dry_run=args.dry_run, limit=args.limit)
