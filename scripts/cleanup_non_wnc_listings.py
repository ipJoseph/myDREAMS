"""
One-shot deletion of listings + photos for counties outside the WNC
service area defined in src/core/regions.py.

Modes:
    --dry-run       Print impact, change nothing.
    --quarantine    Move photo files to .quarantine-{YYYYMMDD}/ then DELETE
                    DB rows (listings + property_changes + contact_events).
                    Reversible by moving files back + restoring from
                    pg_dump-pre-wnc-cleanup-{date}.sql.gz.
    --commit        Hard-delete .quarantine-{YYYYMMDD}/ to reclaim disk.
                    Refuses to run if no quarantine dir found.

Safety:
- Pre-flight count check; refuses if expected counts off by > tolerance.
- DB writes happen in a single transaction.
- Photo files moved (mv), not deleted, until --commit.
- Reads WNC_COUNTIES from src/core/regions.py — single source of truth.
"""

import argparse
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("cleanup-non-wnc")

PHOTOS_DIR = Path(os.environ.get("DREAMS_PHOTOS_DIR", "/mnt/dreams-photos"))
QUARANTINE_DATE = datetime.now().strftime("%Y%m%d")
QUARANTINE_DIR = PHOTOS_DIR / f".quarantine-{QUARANTINE_DATE}"

# Pre-flight expected counts (refuse to proceed if delta is large).
EXPECTED_LISTINGS_DELETE = 47_792
EXPECTED_PROPERTY_CHANGES_DELETE = 11_543
EXPECTED_CONTACT_EVENTS_DELETE = 10
TOLERANCE_PCT = 5.0  # Allow +/- 5% drift since data changes between snapshot and run


def load_env():
    """Load DATABASE_URL etc. from .env (fallback for ad-hoc invocations)."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(
                    key.strip(),
                    value.strip().strip('"').strip("'"),
                )


def get_counties_csv():
    """Return the WNC counties as a SQL-safe IN-list literal."""
    from src.core.regions import WNC_COUNTIES
    return ", ".join(f"'{c}'" for c in sorted(WNC_COUNTIES))


def preflight_counts(conn):
    """Return dict of how many rows WOULD be deleted in each table.

    Uses IN-subquery rather than correlated EXISTS — the correlated form
    forced a nested-loop plan that hung on PRD (15K x 47K iterations).
    """
    counties_csv = get_counties_csv()

    listings_count = conn.execute(
        f"SELECT COUNT(*) AS n FROM listings "
        f"WHERE county NOT IN ({counties_csv}) OR county IS NULL"
    ).fetchone()["n"]

    pc_count = conn.execute(
        f"SELECT COUNT(*) AS n FROM property_changes "
        f"WHERE property_id IN ("
        f"  SELECT id FROM listings "
        f"  WHERE county NOT IN ({counties_csv}) OR county IS NULL"
        f")"
    ).fetchone()["n"]

    ce_count = conn.execute(
        f"SELECT COUNT(*) AS n FROM contact_events "
        f"WHERE property_mls IN ("
        f"  SELECT mls_number FROM listings "
        f"  WHERE (county NOT IN ({counties_csv}) OR county IS NULL) "
        f"  AND mls_number IS NOT NULL"
        f")"
    ).fetchone()["n"]

    return {
        "listings": listings_count,
        "property_changes": pc_count,
        "contact_events": ce_count,
    }


def get_to_delete_listings(conn):
    """Return list of dicts (id, mls_number, mls_source) for listings to delete."""
    counties_csv = get_counties_csv()
    rows = conn.execute(
        f"SELECT id, mls_number, mls_source FROM listings "
        f"WHERE county NOT IN ({counties_csv}) OR county IS NULL"
    ).fetchall()
    return [dict(r) for r in rows]


def quarantine_photos(listings, dry_run=False):
    """Move photo files for to-delete listings into the quarantine dir.

    Returns (files_moved, bytes_moved, listings_with_no_files).
    """
    if not dry_run:
        (QUARANTINE_DIR / "mlsgrid").mkdir(parents=True, exist_ok=True)
        (QUARANTINE_DIR / "navica").mkdir(parents=True, exist_ok=True)

    files_moved = 0
    bytes_moved = 0
    listings_without_files = 0
    progress_every = 1000

    for i, r in enumerate(listings, 1):
        mls_number = r["mls_number"]
        mls_source = r["mls_source"]
        if not mls_number:
            listings_without_files += 1
            continue

        if mls_source == "CanopyMLS":
            src_dir = PHOTOS_DIR / "mlsgrid"
            dst_dir = QUARANTINE_DIR / "mlsgrid"
        elif mls_source in ("NavicaMLS", "MountainLakesMLS"):
            src_dir = PHOTOS_DIR / "navica"
            dst_dir = QUARANTINE_DIR / "navica"
        else:
            listings_without_files += 1
            continue

        # Match {mls_number}.* (primary) and {mls_number}_* (gallery).
        matched = list(src_dir.glob(f"{mls_number}.*")) + list(src_dir.glob(f"{mls_number}_*"))
        if not matched:
            listings_without_files += 1
            continue

        for f in matched:
            if not f.is_file():
                continue
            try:
                size = f.stat().st_size
            except OSError:
                continue
            if not dry_run:
                try:
                    shutil.move(str(f), str(dst_dir / f.name))
                except OSError as e:
                    log.warning("Move failed for %s: %s", f, e)
                    continue
            files_moved += 1
            bytes_moved += size

        if i % progress_every == 0:
            log.info(
                "  Photo move progress: %d/%d listings (%d files, %.1f GB so far)",
                i, len(listings), files_moved, bytes_moved / (1024**3),
            )

    return files_moved, bytes_moved, listings_without_files


def delete_db_rows(conn, dry_run=False):
    """Run the actual DELETE statements (or print what would happen)."""
    counties_csv = get_counties_csv()

    if dry_run:
        log.info("  [dry-run] DB DELETE skipped")
        return

    log.info("  Deleting from property_changes...")
    cur = conn.execute(
        f"DELETE FROM property_changes "
        f"WHERE property_id IN ("
        f"  SELECT id FROM listings "
        f"  WHERE county NOT IN ({counties_csv}) OR county IS NULL"
        f")"
    )
    log.info("    property_changes rows deleted: %d", cur.rowcount)

    log.info("  Deleting from contact_events...")
    cur = conn.execute(
        f"DELETE FROM contact_events "
        f"WHERE property_mls IN ("
        f"  SELECT mls_number FROM listings "
        f"  WHERE (county NOT IN ({counties_csv}) OR county IS NULL) "
        f"  AND mls_number IS NOT NULL"
        f")"
    )
    log.info("    contact_events rows deleted: %d", cur.rowcount)

    log.info("  Deleting from listings...")
    cur = conn.execute(
        f"DELETE FROM listings "
        f"WHERE county NOT IN ({counties_csv}) OR county IS NULL"
    )
    log.info("    listings rows deleted: %d", cur.rowcount)


def cmd_dry_run():
    from src.core.pg_adapter import get_db
    conn = get_db()

    log.info("=== DRY RUN: no changes will be made ===")
    counts = preflight_counts(conn)
    log.info("Pre-flight counts (would be DELETED):")
    for k, v in counts.items():
        log.info("  %-20s %d rows", k, v)

    listings = get_to_delete_listings(conn)
    log.info("Enumerating photo files for %d listings...", len(listings))
    files, bytes_, no_files = quarantine_photos(listings, dry_run=True)
    log.info("Photo files that WOULD be quarantined: %d files, %.1f GB",
             files, bytes_ / (1024**3))
    log.info("Listings with no on-disk photo files: %d", no_files)
    conn.close()


def cmd_quarantine(force=False):
    from src.core.pg_adapter import get_db
    conn = get_db()

    log.info("=== QUARANTINE MODE ===")
    counts = preflight_counts(conn)
    log.info("Pre-flight counts:")
    for k, v in counts.items():
        log.info("  %-20s %d rows", k, v)

    expected = {
        "listings": EXPECTED_LISTINGS_DELETE,
        "property_changes": EXPECTED_PROPERTY_CHANGES_DELETE,
        "contact_events": EXPECTED_CONTACT_EVENTS_DELETE,
    }
    for k, v in counts.items():
        exp = expected[k]
        if exp == 0:
            continue  # contact_events expected near 0; skip percentage check
        delta_pct = abs(v - exp) / exp * 100
        if delta_pct > TOLERANCE_PCT:
            log.error(
                "Count for %s drifted by %.1f%% (expected %d, got %d). Aborting unless --force.",
                k, delta_pct, exp, v
            )
            if not force:
                conn.close()
                sys.exit(2)

    listings = get_to_delete_listings(conn)
    log.info("Quarantining %d photo files for %d listings to %s ...",
             0, len(listings), QUARANTINE_DIR)
    files, bytes_, no_files = quarantine_photos(listings, dry_run=False)
    log.info("Photos quarantined: %d files, %.1f GB. Listings with no files: %d",
             files, bytes_ / (1024**3), no_files)

    log.info("Beginning DB transaction...")
    try:
        delete_db_rows(conn, dry_run=False)
        conn.commit()
        log.info("DB DELETE committed.")
    except Exception as e:
        log.exception("DB delete failed: %s", e)
        conn.rollback()
        log.error("Rolled back. Photos remain in %s — restore by moving them back.",
                  QUARANTINE_DIR)
        conn.close()
        sys.exit(3)

    conn.close()
    log.info("Quarantine complete. Verify with --dry-run; commit with --commit.")


def cmd_commit():
    """Hard-delete the quarantine directory."""
    if not QUARANTINE_DIR.exists():
        log.error("No quarantine dir at %s. Did you run --quarantine?", QUARANTINE_DIR)
        sys.exit(2)

    log.info("=== COMMIT MODE ===")
    log.info("Hard-deleting %s ...", QUARANTINE_DIR)
    shutil.rmtree(QUARANTINE_DIR)
    log.info("Quarantine dir removed. Disk space reclaimed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="Print impact, no changes")
    g.add_argument("--quarantine", action="store_true", help="Move photos + DELETE DB rows")
    g.add_argument("--commit", action="store_true", help="Hard-delete quarantine dir")
    parser.add_argument("--force", action="store_true",
                        help="Bypass count-drift safety check (use with caution)")
    args = parser.parse_args()

    load_env()

    if args.dry_run:
        cmd_dry_run()
    elif args.quarantine:
        cmd_quarantine(force=args.force)
    elif args.commit:
        cmd_commit()


if __name__ == "__main__":
    main()
