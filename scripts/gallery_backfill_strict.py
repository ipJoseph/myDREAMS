"""Strict-rate-limited gallery downloader for CanopyMLS listings.

MLS Grid suspended us once today for going over rate limits. This
script is the conservative replacement:

  - SEQUENTIAL. No threading. One request at a time.
  - A global throttle sleeps to maintain max 1.0 req/sec against
    mlsgrid.com (both api.mlsgrid.com and media.mlsgrid.com count).
  - Rolling-window budget: pauses if we've hit the 24-hour request
    cap (MLS Grid warning: 40,000 requests per 24 hours).
  - Newest listings first. Default sort list_date DESC so the home
    page recovers first, older inventory catches up over nights.
  - Resumable: each listing's state is written to the DB on success;
    re-running picks up where we left off.

Usage:
  # Launch-and-forget (overnight):
  /opt/mydreams/venv/bin/python3 scripts/gallery_backfill_strict.py \
      --max-rps 1.0 \
      --daily-budget 35000

  # Continue from where we left off (nightly cron at 23:00 UTC):
  /opt/mydreams/venv/bin/python3 scripts/gallery_backfill_strict.py --only-stale
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("gallery_backfill_strict")


class MLSGridThrottle:
    """Paces every outbound request against mlsgrid.com.

    Enforces:
      * a minimum gap between requests (1 / max_rps seconds)
      * a sliding 24-hour budget of total requests

    Thread-safe (we only use one thread today, but keeping it safe
    means no surprises if future code parallelises).
    """

    def __init__(self, max_rps: float, daily_budget: int):
        self._min_gap = 1.0 / max_rps if max_rps > 0 else 0.0
        self._daily_budget = daily_budget
        self._last_request_at = 0.0
        self._recent_24h: deque = deque()  # timestamps
        self._lock = threading.Lock()

    def acquire(self):
        """Block until a request can safely be issued."""
        while True:
            with self._lock:
                now = time.monotonic()
                # Evict timestamps older than 24 h
                cutoff = now - 86400
                while self._recent_24h and self._recent_24h[0] < cutoff:
                    self._recent_24h.popleft()

                # If we're over the 24h budget, sleep until the oldest entry ages out.
                if len(self._recent_24h) >= self._daily_budget:
                    oldest = self._recent_24h[0]
                    wait = max(1.0, (oldest + 86400) - now)
                    logger.warning(
                        "24h budget full (%d); sleeping %.0fs for oldest entry to expire",
                        len(self._recent_24h), wait,
                    )
                else:
                    # Respect per-request minimum gap
                    since_last = now - self._last_request_at
                    wait = max(0.0, self._min_gap - since_last)

                    if wait <= 0:
                        self._last_request_at = now
                        self._recent_24h.append(now)
                        return

            time.sleep(wait)


# Image magic-byte prefixes. A corrupt/truncated file can be >100 bytes
# and pass a size check, but real images always start with one of these.
_IMAGE_MAGIC = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"RIFF", b"GIF8")


def _file_looks_valid(filepath: Path) -> bool:
    """Return True if the file exists, is big enough, AND starts with
    a known image magic number. Guards against partial/corrupt writes
    that the old `size > 100` check would have passed."""
    try:
        if filepath.stat().st_size < 500:
            return False
        with open(filepath, "rb") as f:
            head = f.read(8)
        return any(head.startswith(m) for m in _IMAGE_MAGIC)
    except Exception:
        return False


def _listing_needs_work(row: Dict[str, Any], photos_dir: Path) -> bool:
    """True if this listing's gallery is not yet fully local-on-disk."""
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
        return True

    for u in urls:
        if not isinstance(u, str):
            return True
        if u.startswith("http"):
            return True
        filename = u.rsplit("/", 1)[-1] if "/" in u else u
        if not _file_looks_valid(photos_dir / filename):
            return True
    return False


def _process_listing(
    row: Dict[str, Any],
    throttle: MLSGridThrottle,
    client,
    extract_photos_fn,
    save_atomic_fn,
    download_photo_fn,
    detect_extension_fn,
    photos_dir: Path,
    get_db_fn,
) -> Dict[str, int]:
    """Fetch fresh Media, download each photo, rewrite DB row to local paths.

    Every MLS Grid HTTP call is preceded by throttle.acquire().
    Returns {'downloaded': N, 'skipped': N, 'errors': N}.
    """
    mls = row["mls_number"]
    stats = {"downloaded": 0, "skipped": 0, "errors": 0}

    throttle.acquire()
    try:
        media = client.fetch_media_for_listing(mls)
    except Exception as e:
        logger.warning("%s: fetch_media failed: %s", mls, str(e)[:100])
        stats["errors"] += 1
        return stats

    primary_url, all_urls, photo_count = extract_photos_fn(media)
    if not all_urls:
        # MLS reports no media for this listing — mark skipped.
        # Wrap the DB write in try/except so a transient PG error (timeout,
        # connection blip) doesn't propagate and stop the entire drain.
        # We'd rather skip-and-continue than halt 6000+ remaining listings.
        conn = get_db_fn()
        try:
            try:
                conn.execute(
                    "UPDATE listings SET photo_count = 0, gallery_status = 'skipped' WHERE id = ?",
                    [row["id"]],
                )
                conn.commit()
            except Exception as e:
                logger.warning("%s: mark-skipped DB write failed: %s", mls, str(e)[:120])
                stats["errors"] += 1
                try: conn.rollback()
                except Exception: pass
        finally:
            try: conn.close()
            except Exception: pass
        return stats

    local_urls: List[str] = []
    for i, url in enumerate(all_urls):
        # One source of truth for extension detection — apps/photos/downloader
        ext = detect_extension_fn(url)

        filename = f"{mls}{ext}" if i == 0 else f"{mls}_{i:02d}{ext}"
        filepath = photos_dir / filename

        if filepath.exists() and _file_looks_valid(filepath):
            stats["skipped"] += 1
            local_urls.append(f"/api/public/photos/mlsgrid/{filename}")
            continue

        throttle.acquire()
        data = download_photo_fn(url)
        if not data:
            # Don't keep CDN URL — it expires in ~1h and pollutes invariant #1.
            # The listing's readiness is evaluated on successful downloads only.
            stats["errors"] += 1
            continue

        save_atomic_fn(photos_dir, filename, data)
        local_urls.append(f"/api/public/photos/mlsgrid/{filename}")
        stats["downloaded"] += 1

    # local_urls now contains ONLY successful /api/public/photos/ paths.
    primary_local = local_urls[0] if local_urls else None

    # Readiness: the primary must be local, and we must have most of the
    # gallery. Tolerate up to max(3, 10% of photo_count) broken/missing
    # photos so a single chronically-dead upstream URL doesn't block the
    # listing forever (~4% of real MLS photos are permanently 404).
    broken_allowed = max(3, photo_count // 10) if photo_count else 3
    min_required = max(1, photo_count - broken_allowed) if photo_count else 1
    gallery_ready = bool(primary_local) and len(local_urls) >= min_required

    new_status = "ready" if gallery_ready else "pending"
    if stats["errors"] > 0:
        logger.info(
            "%s: %d/%d local (%d broken); status=%s",
            mls, len(local_urls), photo_count, stats["errors"], new_status,
        )

    # Invariant #2: photo_verified_at is only set on successful verify.
    verified_expr = "CURRENT_TIMESTAMP" if gallery_ready else "photo_verified_at"

    conn = get_db_fn()
    try:
        try:
            if primary_local:
                conn.execute(
                    f"UPDATE listings SET photos = ?, primary_photo = ?, photo_count = ?, "
                    f"photo_verified_at = {verified_expr}, "
                    f"gallery_status = ? WHERE id = ?",
                    [json.dumps(local_urls), primary_local, photo_count,
                     new_status, row["id"]],
                )
            else:
                conn.execute(
                    f"UPDATE listings SET photos = ?, photo_count = ?, "
                    f"photo_verified_at = {verified_expr}, gallery_status = ? "
                    f"WHERE id = ?",
                    [json.dumps(local_urls), photo_count, new_status, row["id"]],
                )
            conn.commit()
        except Exception as e:
            # Transient PG errors (statement timeout, connection blip) must
            # not stop the drain. Files are on disk; next iteration will
            # retry the DB write cleanly.
            logger.warning("%s: DB write failed after download: %s", mls, str(e)[:120])
            stats["errors"] += 1
            try: conn.rollback()
            except Exception: pass
    finally:
        try: conn.close()
        except Exception: pass

    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--max-rps", type=float, default=1.0,
        help="Maximum MLS Grid requests per second (safe: 1.0; emergency: 0.5)",
    )
    ap.add_argument(
        "--daily-budget", type=int, default=35000,
        help="Max total MLS Grid requests in rolling 24h (warning: 40,000)",
    )
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument(
        "--only-stale", action="store_true",
        help="Skip listings already fully local-on-disk.",
    )
    ap.add_argument(
        "--sort", choices=["newest", "oldest"], default="newest",
        help="Process newest listings first (default) so home page recovers fastest.",
    )
    args = ap.parse_args()

    from apps.mlsgrid.client import MLSGridClient
    from apps.navica.field_mapper import extract_photos
    from apps.photos import storage
    from apps.photos.downloader import download_photo, detect_extension
    from src.core.pg_adapter import get_db

    photos_dir = storage.get_source_dir("CanopyMLS")
    photos_dir.mkdir(parents=True, exist_ok=True)

    throttle = MLSGridThrottle(args.max_rps, args.daily_budget)

    sort_sql = "DESC" if args.sort == "newest" else "ASC"
    conn = get_db()
    # PHOTO_PIPELINE_SPEC.md: gallery_priority DESC first so listings a user
    # just viewed (priority=10) jump the queue. Within same priority we
    # fall back to list_date order.
    #
    # The gallery_priority column is guarded by existence check so this script
    # keeps working during the brief window between code deploy and
    # ALTER TABLE completion on PRD (which can be blocked for hours by lock
    # contention during business hours).
    priority_col_exists = bool(conn.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'listings' AND column_name = 'gallery_priority'"
    ).fetchone())
    order_by = (
        f"gallery_priority DESC, list_date {sort_sql} NULLS LAST"
        if priority_col_exists
        else f"list_date {sort_sql} NULLS LAST"
    )
    rows = conn.execute(
        f"""
        SELECT id, mls_source, mls_number, photo_count, photos, list_date
        FROM listings
        WHERE status = 'ACTIVE'
          AND mls_source = 'CanopyMLS'
        ORDER BY {order_by}
        """
    ).fetchall()
    rows = [dict(r) for r in rows]

    if args.only_stale:
        before = len(rows)
        rows = [r for r in rows if _listing_needs_work(r, photos_dir)]
        logger.info("Filter --only-stale: %d/%d listings need work", len(rows), before)
    else:
        logger.info(
            "Processing %d active CanopyMLS listings (sort=%s, max_rps=%.2f, daily_budget=%d)",
            len(rows), args.sort, args.max_rps, args.daily_budget,
        )

    if args.limit:
        rows = rows[: args.limit]

    if not rows:
        logger.info("Nothing to do.")
        return 0

    client = MLSGridClient.from_env()
    started = time.time()
    total_dl = 0
    total_sk = 0
    total_err = 0

    try:
        for i, row in enumerate(rows, 1):
            stats = _process_listing(
                row, throttle, client, extract_photos, storage.save_atomic,
                download_photo, detect_extension, photos_dir, get_db,
            )
            total_dl += stats["downloaded"]
            total_sk += stats["skipped"]
            total_err += stats["errors"]

            if i % 25 == 0 or i == len(rows):
                elapsed = time.time() - started
                rate = i / elapsed if elapsed else 0
                eta = (len(rows) - i) / rate if rate else 0
                logger.info(
                    "[%d/%d] %s list/%s downloaded=%d skipped=%d errors=%d rate=%.2f list/s ETA=%.0fs",
                    i, len(rows), row.get("list_date"), row.get("mls_number"),
                    total_dl, total_sk, total_err, rate, eta,
                )
    except KeyboardInterrupt:
        logger.warning("Interrupted; partial progress saved in DB.")
    finally:
        elapsed = time.time() - started
        logger.info(
            "Done in %.0fs (%.1f min): downloaded=%d skipped=%d errors=%d",
            elapsed, elapsed / 60, total_dl, total_sk, total_err,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
