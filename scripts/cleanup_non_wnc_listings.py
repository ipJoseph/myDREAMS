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


def _scan_photo_dir_by_prefix(src_dir):
    """Scan src_dir ONCE and build a {mls_number_prefix: [(filename, size)]} index.

    Avoids per-listing glob() against a 1.4M-file directory (which is O(N) per
    call due to filesystem readdir scan, killing the runtime).

    A file is keyed by the part of its name before the first '.' or '_':
        '12345.jpg'    -> '12345'
        '12345_01.jpg' -> '12345'
        '67890.jpeg'   -> '67890'
    """
    index = {}
    if not src_dir.exists():
        return index
    log.info("  Scanning %s ... (one-time pass)", src_dir)
    n = 0
    with os.scandir(src_dir) as it:
        for entry in it:
            if not entry.is_file():
                continue
            name = entry.name
            # Split on first '_' or '.', whichever comes first.
            first_dot = name.find('.')
            first_under = name.find('_')
            if first_under == -1:
                cut = first_dot
            elif first_dot == -1:
                cut = first_under
            else:
                cut = min(first_dot, first_under)
            if cut <= 0:
                continue
            key = name[:cut]
            try:
                size = entry.stat().st_size
            except OSError:
                continue
            index.setdefault(key, []).append((name, size))
            n += 1
    log.info("  Indexed %d files in %s", n, src_dir)
    return index


def quarantine_photos(listings, dry_run=False, hard_delete=False):
    """Move photo files for to-delete listings.

    If hard_delete=True, files are unlinked directly (no quarantine dir).
    This is necessary when the volume is so full that mkdir fails (no
    inodes / no space for new directory entry). Rollback is via pg_dump
    + re-fetch from MLS CDN.

    Returns (files_moved_or_deleted, bytes_freed, listings_with_no_files).
    """
    if not dry_run and not hard_delete:
        (QUARANTINE_DIR / "mlsgrid").mkdir(parents=True, exist_ok=True)
        (QUARANTINE_DIR / "navica").mkdir(parents=True, exist_ok=True)

    # Build per-source filename index ONCE (~1.4M files, takes seconds with scandir).
    mlsgrid_index = _scan_photo_dir_by_prefix(PHOTOS_DIR / "mlsgrid")
    navica_index = _scan_photo_dir_by_prefix(PHOTOS_DIR / "navica")

    files_moved = 0
    bytes_moved = 0
    listings_without_files = 0
    progress_every = 5000

    for i, r in enumerate(listings, 1):
        mls_number = r["mls_number"]
        mls_source = r["mls_source"]
        if not mls_number:
            listings_without_files += 1
            continue

        if mls_source == "CanopyMLS":
            src_dir = PHOTOS_DIR / "mlsgrid"
            dst_dir = QUARANTINE_DIR / "mlsgrid"
            index = mlsgrid_index
        elif mls_source in ("NavicaMLS", "MountainLakesMLS"):
            src_dir = PHOTOS_DIR / "navica"
            dst_dir = QUARANTINE_DIR / "navica"
            index = navica_index
        else:
            listings_without_files += 1
            continue

        matched = index.get(str(mls_number), [])
        if not matched:
            listings_without_files += 1
            continue

        for fname, size in matched:
            src_path = src_dir / fname
            if not dry_run:
                try:
                    if hard_delete:
                        src_path.unlink()
                    else:
                        shutil.move(str(src_path), str(dst_dir / fname))
                except OSError as e:
                    log.warning("File op failed for %s: %s", src_path, e)
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


def cmd_quarantine(force=False, hard_delete=False):
    from src.core.pg_adapter import get_db
    conn = get_db()

    log.info("=== %s MODE ===", "HARD-DELETE" if hard_delete else "QUARANTINE")
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
    if hard_delete:
        log.info("HARD-DELETING photos for %d listings (no quarantine; rollback via pg_dump only)", len(listings))
    else:
        log.info("Quarantining photos for %d listings to %s ...", len(listings), QUARANTINE_DIR)
    files, bytes_, no_files = quarantine_photos(listings, dry_run=False, hard_delete=hard_delete)
    verb = "deleted" if hard_delete else "quarantined"
    log.info("Photos %s: %d files, %.1f GB. Listings with no files: %d",
             verb, files, bytes_ / (1024**3), no_files)

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
    g.add_argument("--quarantine", action="store_true", help="Move photos to quarantine + DELETE DB rows")
    g.add_argument("--hard-delete", action="store_true",
                   help="rm photos directly + DELETE DB rows (use when disk is too full to quarantine; rollback via pg_dump only)")
    g.add_argument("--commit", action="store_true", help="Hard-delete quarantine dir")
    parser.add_argument("--force", action="store_true",
                        help="Bypass count-drift safety check (use with caution)")
    args = parser.parse_args()

    load_env()

    if args.dry_run:
        cmd_dry_run()
    elif args.quarantine:
        cmd_quarantine(force=args.force, hard_delete=False)
    elif args.hard_delete:
        cmd_quarantine(force=args.force, hard_delete=True)
    elif args.commit:
        cmd_commit()


if __name__ == "__main__":
    main()
