"""Download full gallery photos for all active CanopyMLS listings.

After the 2026-04-20 backfill repopulated `photos` with fresh MLS Grid
CDN URLs, those URLs have signed tokens that expire in ~1 hour. Rather
than rely on them, download every photo to local disk so the frontend
serves /api/public/photos/mlsgrid/... paths that never expire.

Usage:
    /opt/mydreams/venv/bin/python3 scripts/download_all_galleries.py [--workers 8] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("download_all_galleries")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--status", default="ACTIVE")
    args = ap.parse_args()

    from apps.photos import manager, storage
    from apps.photos.downloader import download_photo
    from src.core.pg_adapter import get_db

    conn = get_db()
    rows = conn.execute(
        """
        SELECT id, mls_source, mls_number, photos
        FROM listings
        WHERE UPPER(status) = ?
          AND mls_source = 'CanopyMLS'
          AND photos IS NOT NULL
          AND json_array_length(photos::json) > 1
        ORDER BY list_date DESC
        """,
        [args.status.upper()],
    ).fetchall()

    rows = [dict(r) for r in rows]
    if args.limit:
        rows = rows[: args.limit]

    logger.info("Found %d listings with multi-photo galleries", len(rows))
    if not rows:
        return 0

    photos_dir = storage.get_source_dir("CanopyMLS")

    def _process_listing(row):
        mls = row["mls_number"]
        photos_raw = row["photos"]
        try:
            urls = json.loads(photos_raw) if isinstance(photos_raw, str) else photos_raw
        except Exception:
            return ("error", mls, 0, 0)
        if not isinstance(urls, list):
            return ("error", mls, 0, 0)

        downloaded = 0
        skipped = 0
        local_urls = []
        for i, url in enumerate(urls):
            if not (isinstance(url, str) and url.startswith("http")):
                continue
            # Storage naming: position 0 = {mls}.jpg, position i>0 = {mls}_{i:02}.jpg
            ext = ".jpeg" if url.lower().rsplit("?", 1)[0].endswith(".jpeg") else ".jpg"
            if i == 0:
                filename = f"{mls}{ext}"
            else:
                filename = f"{mls}_{i:02d}{ext}"
            filepath = photos_dir / filename

            if filepath.exists() and filepath.stat().st_size > 100:
                skipped += 1
                local_urls.append(f"/api/public/photos/mlsgrid/{filename}")
                continue

            data = download_photo(url)
            if not data:
                continue
            storage.save_atomic(photos_dir, filename, data)
            downloaded += 1
            local_urls.append(f"/api/public/photos/mlsgrid/{filename}")

        # Update DB photos column if we downloaded any new files
        if downloaded and local_urls:
            conn2 = get_db()
            try:
                conn2.execute(
                    "UPDATE listings SET photos = ?, photo_verified_at = CURRENT_TIMESTAMP WHERE id = ?",
                    [json.dumps(local_urls), row["id"]],
                )
                conn2.commit()
            finally:
                try:
                    conn2.close()
                except Exception:
                    pass

        return ("ok", mls, downloaded, skipped)

    started = time.time()
    total_downloaded = 0
    total_skipped = 0
    errors = 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_process_listing, row): row for row in rows}
        for i, fut in enumerate(as_completed(futures), 1):
            try:
                status, mls, dl, sk = fut.result()
            except Exception as e:
                errors += 1
                logger.warning("[%d/%d] worker crashed: %s", i, len(rows), e)
                continue

            if status == "ok":
                total_downloaded += dl
                total_skipped += sk
            else:
                errors += 1

            if i % 50 == 0 or i == len(rows):
                elapsed = time.time() - started
                rate = i / elapsed if elapsed else 0
                eta = (len(rows) - i) / rate if rate else 0
                logger.info(
                    "[%d/%d] downloaded=%d skipped=%d errors=%d rate=%.2f list/s ETA=%.0fs",
                    i, len(rows), total_downloaded, total_skipped, errors, rate, eta,
                )

    elapsed = time.time() - started
    logger.info(
        "Done in %.0fs: downloaded=%d skipped=%d errors=%d",
        elapsed, total_downloaded, total_skipped, errors,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
