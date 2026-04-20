"""For every active CanopyMLS listing, fetch a fresh Media array from
MLS Grid, download every photo to /data/photos/mlsgrid/, and rewrite
the DB `photos` column to the local `/api/public/photos/...` paths.

This is the one script that fixes the Canopy gallery situation end to
end:

  - MLS Grid CDN URLs have signed tokens with a ~1 hour TTL, so we
    can't trust URLs already stored in the DB.
  - One API request per listing returns current (not yet expired)
    tokens, which we use immediately to pull the photo bytes to disk.
  - Once files are on disk, URLs served to the frontend are
    /api/public/photos/mlsgrid/CAR####.jpg paths that never expire.

Design:
  - Parallel: ThreadPoolExecutor with --workers concurrent tasks.
  - Idempotent: existing files (>100 bytes) are kept, not re-downloaded.
  - Resumable: --only-stale skips listings whose DB `photos` already
    point to local paths and whose expected files all exist on disk.
  - Safe on rate limits: per-listing API call is the only MLS Grid
    load; photos are downloaded from the AWS CDN which scales.
  - Writes photos column incrementally so a mid-run crash leaves
    partial-but-correct state.

Usage on PRD:
    /opt/mydreams/venv/bin/python3 scripts/fetch_and_download_galleries.py --workers 8
    /opt/mydreams/venv/bin/python3 scripts/fetch_and_download_galleries.py --only-stale  # nightly
    /opt/mydreams/venv/bin/python3 scripts/fetch_and_download_galleries.py --limit 500 --sort newest
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("fetch_and_download_galleries")


def _listing_needs_work(row: Dict[str, Any], photos_dir: Path) -> bool:
    """Return True if this listing still needs any gallery work."""
    mls = row["mls_number"]
    # Walk the stored photos; if every one is a local path AND the file
    # exists, skip the listing.
    photos_raw = row.get("photos")
    if not photos_raw:
        return True
    try:
        urls = json.loads(photos_raw) if isinstance(photos_raw, str) else photos_raw
    except Exception:
        return True
    if not isinstance(urls, list) or not urls:
        return True

    photo_count = row.get("photo_count") or 0
    if photo_count > 1 and len(urls) < photo_count - 1:
        return True  # array is truncated

    for u in urls:
        if not isinstance(u, str):
            return True
        if u.startswith("http"):
            return True  # still pointing at CDN
        # Local path like /api/public/photos/mlsgrid/CARXXXX.jpg
        filename = u.rsplit("/", 1)[-1] if "/" in u else u
        if not (photos_dir / filename).exists():
            return True
    return False


def _process_listing(row, client, extract_photos_fn, save_atomic_fn, download_photo_fn, photos_dir, get_db_fn):
    """Fetch fresh Media and download every photo. Returns (status, mls, downloaded, skipped)."""
    mls = row["mls_number"]
    try:
        media = client.fetch_media_for_listing(mls)
    except Exception as e:
        return ("error", mls, 0, 0, str(e)[:120])

    primary_url, all_urls, photo_count = extract_photos_fn(media)

    if not all_urls:
        # Either the listing is newly hidden by agent, or MLS Grid returned no Media.
        # Update photos column to NULL so localize_photo falls back correctly.
        conn = get_db_fn()
        try:
            conn.execute(
                "UPDATE listings SET photo_count = 0 WHERE id = ?",
                [row["id"]],
            )
            conn.commit()
        finally:
            try: conn.close()
            except Exception: pass
        return ("nomedia", mls, 0, 0, None)

    # Download each photo. Position 0 = primary file {mls}.{ext}; positions
    # 1..N = gallery files {mls}_{NN}.{ext}. Matches the existing on-disk
    # convention and what localize_photo scans for.
    downloaded = 0
    skipped = 0
    local_urls: List[str] = []

    for i, url in enumerate(all_urls):
        # Choose extension: MLS Grid usually .jpeg but we take whatever the URL ends with
        path_before_query = url.split("?", 1)[0]
        if path_before_query.lower().endswith(".jpg"):
            ext = ".jpg"
        elif path_before_query.lower().endswith(".png"):
            ext = ".png"
        elif path_before_query.lower().endswith(".webp"):
            ext = ".webp"
        else:
            ext = ".jpeg"

        filename = f"{mls}{ext}" if i == 0 else f"{mls}_{i:02d}{ext}"
        filepath = photos_dir / filename

        if filepath.exists() and filepath.stat().st_size > 100:
            skipped += 1
            local_urls.append(f"/api/public/photos/mlsgrid/{filename}")
            continue

        data = download_photo_fn(url)
        if not data:
            # Keep the CDN URL in this position so the frontend has something
            local_urls.append(url)
            continue
        save_atomic_fn(photos_dir, filename, data)
        downloaded += 1
        local_urls.append(f"/api/public/photos/mlsgrid/{filename}")

    # Update the DB with whatever mix of local + CDN we ended up with.
    primary_local = None
    if local_urls and local_urls[0].startswith("/api/"):
        primary_local = local_urls[0]

    conn = get_db_fn()
    try:
        if primary_local:
            conn.execute(
                "UPDATE listings SET photos = ?, primary_photo = ?, photo_count = ?, "
                "photo_ready = TRUE, photo_verified_at = CURRENT_TIMESTAMP WHERE id = ?",
                [json.dumps(local_urls), primary_local, photo_count, row["id"]],
            )
        else:
            conn.execute(
                "UPDATE listings SET photos = ?, photo_count = ?, "
                "photo_verified_at = CURRENT_TIMESTAMP WHERE id = ?",
                [json.dumps(local_urls), photo_count, row["id"]],
            )
        conn.commit()
    finally:
        try: conn.close()
        except Exception: pass

    return ("ok", mls, downloaded, skipped, None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument(
        "--only-stale",
        action="store_true",
        help="Skip listings whose DB photos are already all-local-and-on-disk.",
    )
    ap.add_argument(
        "--sort",
        choices=["newest", "oldest"],
        default="newest",
        help="Process newest listings first (default) so the visible pages repair quickest.",
    )
    args = ap.parse_args()

    from apps.mlsgrid.client import MLSGridClient
    from apps.navica.field_mapper import extract_photos
    from apps.photos import storage
    from apps.photos.downloader import download_photo
    from src.core.pg_adapter import get_db

    photos_dir = storage.get_source_dir("CanopyMLS")
    photos_dir.mkdir(parents=True, exist_ok=True)

    sort_sql = "DESC" if args.sort == "newest" else "ASC"

    conn = get_db()
    rows = conn.execute(
        f"""
        SELECT id, mls_source, mls_number, photo_count, photos
        FROM listings
        WHERE status = 'ACTIVE'
          AND mls_source = 'CanopyMLS'
        ORDER BY list_date {sort_sql} NULLS LAST
        """
    ).fetchall()
    rows = [dict(r) for r in rows]

    if args.only_stale:
        before = len(rows)
        rows = [r for r in rows if _listing_needs_work(r, photos_dir)]
        logger.info("Filter --only-stale: %d/%d listings need work", len(rows), before)
    else:
        logger.info("Processing all %d active CanopyMLS listings (sort=%s)", len(rows), args.sort)

    if args.limit:
        rows = rows[: args.limit]

    if not rows:
        logger.info("Nothing to do.")
        return 0

    client = MLSGridClient.from_env()
    started = time.time()
    total_dl = 0
    total_sk = 0
    errors = 0
    nomedia = 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                _process_listing, row, client, extract_photos,
                storage.save_atomic, download_photo, photos_dir, get_db,
            ): row
            for row in rows
        }
        for i, fut in enumerate(as_completed(futures), 1):
            try:
                status, mls, dl, sk, detail = fut.result()
            except Exception as e:
                errors += 1
                logger.warning("[%d/%d] worker crashed: %s", i, len(rows), e)
                continue

            if status == "ok":
                total_dl += dl
                total_sk += sk
            elif status == "nomedia":
                nomedia += 1
            elif status == "error":
                errors += 1
                logger.warning("[%d/%d] %s: %s", i, len(rows), mls, detail)

            if i % 100 == 0 or i == len(rows):
                elapsed = time.time() - started
                rate = i / elapsed if elapsed else 0
                eta = (len(rows) - i) / rate if rate else 0
                logger.info(
                    "[%d/%d] downloaded=%d skipped=%d nomedia=%d errors=%d rate=%.2f list/s ETA=%.0fs",
                    i, len(rows), total_dl, total_sk, nomedia, errors, rate, eta,
                )

    elapsed = time.time() - started
    logger.info(
        "Done in %.0fs (%.1f min): downloaded=%d skipped=%d nomedia=%d errors=%d",
        elapsed, elapsed / 60, total_dl, total_sk, nomedia, errors,
    )
    return 0 if errors < len(rows) * 0.05 else 1


if __name__ == "__main__":
    sys.exit(main())
