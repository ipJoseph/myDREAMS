"""One-shot Navica + MountainLakes primary-photo drain.

Per PHOTO_PIPELINE_SPEC + DECISIONS D2:
- NavicaMLS / MountainLakesMLS gallery photos MAY remain CDN (CloudFront
  URLs don't expire, safe to serve to browsers).
- Primary photo MUST be local so the detail page always renders instantly
  without depending on an outbound HTTP call.

This script downloads the primary photo for every ACTIVE Navica /
MountainLakes listing that doesn't have one on disk yet, writes the file
to /mnt/dreams-photos/navica/, and updates the DB:
  - primary_photo  ← /api/public/photos/navica/{mls_number}.{ext}
  - photo_verified_at ← CURRENT_TIMESTAMP
  - photos[]       ← LEFT UNTOUCHED (keeps the CDN gallery)

Small volume (~115 listings today), stable CloudFront CDN, no rate-limit
constraint from Navica — concurrent workers are safe.

Usage:
    python3 scripts/drain_navica_primary.py              # dry-run
    python3 scripts/drain_navica_primary.py --fix        # apply
    python3 scripts/drain_navica_primary.py --fix --workers 10
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from apps.photos import storage  # noqa: E402
from apps.photos.downloader import download_photo, detect_extension  # noqa: E402
from src.core.pg_adapter import get_db  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("drain_navica")

SOURCES = ("NavicaMLS", "MountainLakesMLS")
LOCAL_PREFIX = "/api/public/photos/navica/"


def _needs_work(row) -> bool:
    """True if the listing's primary_photo column is CDN (not local) — then
    we either need to download the file + update DB, or (if file already on
    disk) just update DB. `_download_one` handles both cases and returns
    'downloaded' or 'skipped' accordingly."""
    pp = row.get("primary_photo") or ""
    if pp.startswith(LOCAL_PREFIX):
        # Already local in DB. Confirm file is actually there.
        filename = pp.rsplit("/", 1)[-1]
        photos_dir = storage.get_source_dir(row["mls_source"])
        return not (photos_dir / filename).exists()
    return True


def _first_url(row) -> Optional[str]:
    """Return the best URL candidate for downloading the primary photo."""
    pp = row.get("primary_photo")
    if isinstance(pp, str) and pp.startswith("http"):
        return pp
    # Try photos[0]
    photos_raw = row.get("photos")
    if photos_raw:
        try:
            arr = json.loads(photos_raw) if isinstance(photos_raw, str) else photos_raw
            if isinstance(arr, list) and arr and isinstance(arr[0], str) and arr[0].startswith("http"):
                return arr[0]
        except Exception:
            pass
    return None


def _download_one(row) -> Tuple[str, str, Optional[str]]:
    """Download the primary photo for one listing.

    Returns (mls_number, status, local_path_or_error).
    status in {'downloaded', 'skipped', 'no_url', 'error'}
    """
    mls = row["mls_number"]
    source = row["mls_source"]
    url = _first_url(row)
    if not url:
        return (mls, "no_url", None)

    ext = detect_extension(url)
    dest_dir = storage.get_source_dir(source)
    filename = f"{mls}{ext}"
    filepath = dest_dir / filename

    if filepath.exists() and filepath.stat().st_size > 500:
        local_url = f"{LOCAL_PREFIX}{filename}"
        return (mls, "skipped", local_url)

    data = download_photo(url)
    if not data:
        return (mls, "error", "download failed")

    storage.save_atomic(dest_dir, filename, data)
    local_url = f"{LOCAL_PREFIX}{filename}"
    return (mls, "downloaded", local_url)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true",
                    help="Apply DB updates; default is dry-run.")
    ap.add_argument("--workers", type=int, default=10,
                    help="Parallel download workers (default 10).")
    args = ap.parse_args()

    conn = get_db()
    # Include ACTIVE and PENDING (under-contract) listings. PENDING rows
    # aren't visible on the public grid today but can return to ACTIVE if
    # a contract falls through — keeping them drained saves a second pass
    # later and keeps the invariant audit clean.
    rows = conn.execute(
        "SELECT id, mls_number, mls_source, primary_photo, photos "
        "FROM listings "
        "WHERE mls_source IN ('NavicaMLS', 'MountainLakesMLS') "
        "  AND status IN ('ACTIVE', 'PENDING') AND idx_opt_in = 1",
    ).fetchall()
    rows = [dict(r) for r in rows]
    logger.info("Active Navica/MtnLakes listings: %d", len(rows))

    need_work = [r for r in rows if _needs_work(r)]
    logger.info("Listings where DB primary_photo needs to be local: %d", len(need_work))
    if not need_work:
        logger.info("Nothing to do. Everything already local.")
        return 0

    # Parallel download
    downloaded = 0
    skipped = 0
    errors = 0
    no_url = 0
    to_update = []  # (mls_number, mls_source, local_url)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(_download_one, r): r for r in need_work}
        for i, fut in enumerate(as_completed(futures), 1):
            mls, status, detail = fut.result()
            row = futures[fut]
            if status == "downloaded":
                downloaded += 1
                to_update.append((mls, row["mls_source"], detail))
            elif status == "skipped":
                skipped += 1
                to_update.append((mls, row["mls_source"], detail))
            elif status == "error":
                errors += 1
                logger.warning("  %s: %s", mls, detail)
            else:
                no_url += 1
            if i % 25 == 0 or i == len(need_work):
                logger.info("  progress %d/%d (dl=%d skipped=%d err=%d)",
                            i, len(need_work), downloaded, skipped, errors)

    logger.info(
        "Drain result: downloaded=%d skipped=%d errors=%d no_url=%d",
        downloaded, skipped, errors, no_url,
    )

    if not args.fix:
        logger.info("(dry-run; pass --fix to update DB with new primary_photo values)")
        return 0

    # Apply DB updates. One UPDATE per listing; leave photos[] untouched.
    conn = get_db()
    committed = 0
    for mls, source, local_url in to_update:
        try:
            conn.execute(
                "UPDATE listings SET primary_photo = ?, "
                "photo_verified_at = CURRENT_TIMESTAMP "
                "WHERE mls_source = ? AND mls_number = ?",
                [local_url, source, mls],
            )
            committed += 1
        except Exception as e:
            logger.warning("  DB update failed for %s: %s", mls, e)
    conn.commit()
    logger.info("DB updates committed: %d", committed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
