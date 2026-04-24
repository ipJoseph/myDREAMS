"""
PhotoManager — single owner of all photo operations.

This is the public API. Sync engines, API routes, and cron jobs call
methods here. The manager delegates to adapters (per-MLS), storage
(file I/O), and downloader (HTTP fetch).

Design:
- Download is SEPARATE from sync (sync stores fresh URLs; manager downloads)
- Skip-on-failure (one bad photo never stalls the batch)
- Idempotent (safe to run multiple times; skips already-downloaded photos)
- Source-aware (Canopy CDN expires, Navica doesn't — different rules)

See docs/DECISIONS.md D2-D3 and docs/PHOTO_MODULE_DESIGN.md.
"""

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# Ensure project root is importable
_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from apps.photos import storage, downloader
from apps.photos.adapters.mlsgrid import MLSGridPhotoAdapter
from apps.photos.adapters.navica import NavicaPhotoAdapter

logger = logging.getLogger(__name__)

# Adapter registry
ADAPTERS = {
    "CanopyMLS": MLSGridPhotoAdapter(),
    "mlsgrid": MLSGridPhotoAdapter(),
    "NavicaMLS": NavicaPhotoAdapter(),
    "MountainLakesMLS": NavicaPhotoAdapter(),
    "navica": NavicaPhotoAdapter(),
}


@dataclass
class DownloadResult:
    mls_number: str
    primary_downloaded: bool = False
    gallery_downloaded: int = 0
    errors: int = 0
    skipped: bool = False
    local_urls: List[str] = field(default_factory=list)


@dataclass
class HygieneReport:
    total_checked: int = 0
    already_ok: int = 0
    downloaded: int = 0
    failed: int = 0
    errors: List[str] = field(default_factory=list)


def get_adapter(mls_source: str):
    """Get the photo adapter for an MLS source."""
    return ADAPTERS.get(mls_source, ADAPTERS.get("mlsgrid"))


def download_for_listing(
    mls_number: str,
    media_urls: List[str],
    mls_source: str = "CanopyMLS",
    primary_only: bool = False,
) -> DownloadResult:
    """Download photos for one listing. Called by sync engine or hygiene cron.

    Args:
        mls_number: The MLS number (e.g., "CAR4363555")
        media_urls: List of CDN URLs (fresh from API response)
        mls_source: MLS source name for storage directory mapping
        primary_only: If True, download only the primary photo (faster)

    Returns:
        DownloadResult with counts and local URLs
    """
    result = DownloadResult(mls_number=mls_number)

    if not media_urls or not mls_number:
        result.skipped = True
        return result

    adapter = get_adapter(mls_source)
    photos_dir = storage.get_source_dir(mls_source)

    for i, url in enumerate(media_urls):
        if primary_only and i > 0:
            break

        # Determine filename
        ext = downloader.detect_extension(url)
        if i == 0:
            filename = storage.primary_filename(mls_number, ext)
        else:
            filename = storage.gallery_filename(mls_number, i, ext)

        filepath = photos_dir / filename

        # Skip if already on disk
        if filepath.exists() and filepath.stat().st_size > 100:
            source_name = storage.SOURCE_DIRS.get(
                (mls_source or "").lower().replace(" ", ""), "mlsgrid"
            )
            result.local_urls.append(f"/api/public/photos/{source_name}/{filename}")
            if i == 0:
                result.primary_downloaded = True
            continue

        # Download
        data = downloader.download_photo(url)
        if data:
            storage.save_atomic(photos_dir, filename, data)
            source_name = storage.SOURCE_DIRS.get(
                (mls_source or "").lower().replace(" ", ""), "mlsgrid"
            )
            result.local_urls.append(f"/api/public/photos/{source_name}/{filename}")
            if i == 0:
                result.primary_downloaded = True
            else:
                result.gallery_downloaded += 1
        else:
            result.errors += 1

    return result


def download_from_api_response(
    mls_number: str,
    prop: Dict,
    mls_source: str = "CanopyMLS",
    primary_only: bool = False,
) -> DownloadResult:
    """Download photos using a raw API response (with Media array).

    Extracts URLs via the MLS adapter, then downloads.
    Called by the sync engine after processing a listing.
    """
    adapter = get_adapter(mls_source)
    primary_url, all_urls, count = adapter.extract_media_from_response(prop)

    if not all_urls:
        return DownloadResult(mls_number=mls_number, skipped=True)

    return download_for_listing(
        mls_number=mls_number,
        media_urls=all_urls,
        mls_source=mls_source,
        primary_only=primary_only,
    )


def update_db_photo_paths(
    mls_number: str,
    mls_source: str,
    result: DownloadResult,
    conn=None,
) -> None:
    """Update the database with local photo paths after download.

    Writes the authoritative local-paths JSON and bumps photo_verified_at.
    Does NOT set gallery_status here — the caller decides ready/pending
    based on per-MLS readiness rules (PHOTO_PIPELINE_SPEC invariant #1)
    and the listing's expected photo_count. See _download_listing_photos
    in apps/mlsgrid/sync_engine.py for the Canopy-path example.

    photo_local_path and photo_ready are deprecated and no longer written;
    gallery_status is the source of truth.

    If `conn` is provided, runs on that connection and does NOT commit or
    close — caller owns the transaction boundary. If None (default), opens
    a new connection, commits, and closes it. Loop callers should pass
    a shared conn to avoid N open/close cycles per N rows.
    """
    if not result.local_urls:
        return

    owns_conn = conn is None
    try:
        if owns_conn:
            from src.core.pg_adapter import get_db
            conn = get_db()
        primary_local = (
            result.local_urls[0]
            if result.local_urls and result.local_urls[0].startswith("/api/")
            else None
        )
        if primary_local:
            conn.execute(
                "UPDATE listings SET photos = ?, primary_photo = ?, "
                "photo_verified_at = CURRENT_TIMESTAMP "
                "WHERE mls_source = ? AND mls_number = ?",
                [json.dumps(result.local_urls), primary_local,
                 mls_source, mls_number],
            )
        else:
            conn.execute(
                "UPDATE listings SET photos = ?, "
                "photo_verified_at = CURRENT_TIMESTAMP "
                "WHERE mls_source = ? AND mls_number = ?",
                [json.dumps(result.local_urls), mls_source, mls_number],
            )
        if owns_conn:
            conn.commit()
            conn.close()
        try:
            from src.core.listing_service import invalidate_photo_dir_cache
            invalidate_photo_dir_cache(storage.get_source_dir(mls_source))
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"Failed to update photo paths for {mls_number}: {e}")
        if owns_conn and conn is not None:
            try: conn.close()
            except Exception: pass


def run_photo_fill(
    mls_source: str = "CanopyMLS",
    status: str = "ACTIVE",
    primary_only: bool = True,
    limit: Optional[int] = None,
) -> HygieneReport:
    """Fill missing photos for active listings.

    Queries the database for listings without local photos, downloads them.
    This is the main hygiene function called by the cron job.

    For Canopy: uses the photos/primary_photo CDN URLs from the database
    (these may be expired — if download fails, the listing stays without photos
    until the next sync refreshes the URLs).

    For Navica/MountainLakes: CDN URLs don't expire, so this always works.
    """
    from src.core.pg_adapter import get_db

    report = HygieneReport()

    # Single connection held for the whole fill pass. Avoids N open/close
    # cycles through the pool in the inner loop. Commit every 50 rows so
    # crashes don't lose the whole pass.
    conn = get_db()
    try:
        # Find listings whose gallery is not yet ready. gallery_status is
        # the spec's source of truth; photo_local_path is deprecated.
        rows = conn.execute(
            "SELECT mls_number, mls_source, primary_photo, photos "
            "FROM listings "
            "WHERE UPPER(status) = ? AND mls_source = ? "
            "AND (gallery_status IS NULL OR gallery_status != 'ready') "
            "ORDER BY list_date DESC",
            [status.upper(), mls_source],
        ).fetchall()

        if limit:
            rows = rows[:limit]

        logger.info(f"Photo fill: {len(rows)} {mls_source} listings need photos")
        report.total_checked = len(rows)

        for i, row in enumerate(rows):
            mls_num = row[0] if isinstance(row, (list, tuple)) else row["mls_number"]
            source = row[1] if isinstance(row, (list, tuple)) else row["mls_source"]

            # Check disk first (might be downloaded but DB not updated)
            if storage.primary_exists(source, mls_num):
                # Update DB to reflect what's on disk
                local = storage.gallery_urls(source, mls_num)
                update_db_photo_paths(mls_num, source, DownloadResult(
                    mls_number=mls_num, local_urls=local, primary_downloaded=True
                ), conn=conn)
                report.already_ok += 1
            else:
                # Get URLs to download from
                primary_url_val = row[2] if isinstance(row, (list, tuple)) else row.get("primary_photo")
                photos_json = row[3] if isinstance(row, (list, tuple)) else row.get("photos")

                urls = []
                if photos_json:
                    try:
                        parsed = json.loads(photos_json) if isinstance(photos_json, str) else photos_json
                        if isinstance(parsed, list):
                            urls = [u for u in parsed if isinstance(u, str) and u.startswith("http")]
                    except (json.JSONDecodeError, TypeError):
                        pass

                if not urls and primary_url_val and primary_url_val.startswith("http"):
                    urls = [primary_url_val]

                if not urls:
                    report.failed += 1
                else:
                    # Download
                    dl_result = download_for_listing(
                        mls_number=mls_num,
                        media_urls=urls,
                        mls_source=source,
                        primary_only=primary_only,
                    )

                    if dl_result.primary_downloaded:
                        update_db_photo_paths(mls_num, source, dl_result, conn=conn)
                        report.downloaded += 1
                    elif dl_result.errors > 0:
                        # DB URLs failed (likely expired CDN tokens).
                        # Try fetching fresh URLs from the MLS API.
                        adapter = get_adapter(source)
                        if adapter.cdn_urls_expire:
                            fresh_urls = adapter.get_fresh_urls(mls_num)
                            if fresh_urls:
                                dl_result2 = download_for_listing(
                                    mls_number=mls_num,
                                    media_urls=fresh_urls,
                                    mls_source=source,
                                    primary_only=primary_only,
                                )
                                if dl_result2.primary_downloaded:
                                    update_db_photo_paths(mls_num, source, dl_result2, conn=conn)
                                    report.downloaded += 1
                                else:
                                    report.failed += 1
                            else:
                                report.failed += 1
                        else:
                            report.failed += 1
                    else:
                        report.failed += 1

            # Periodic commit so a crash doesn't lose the whole pass.
            if (i + 1) % 50 == 0:
                try:
                    conn.commit()
                except Exception as e:
                    logger.warning(f"periodic commit failed at row {i+1}: {e}")

            if (i + 1) % 100 == 0:
                logger.info(f"  Photo fill progress: {i + 1}/{len(rows)} "
                             f"(downloaded={report.downloaded}, failed={report.failed})")

        # Final commit for any rows since the last 50-row boundary.
        try:
            conn.commit()
        except Exception as e:
            logger.warning(f"final commit failed: {e}")
    finally:
        try: conn.close()
        except Exception: pass

    logger.info(f"Photo fill complete: checked={report.total_checked}, "
                 f"downloaded={report.downloaded}, already_ok={report.already_ok}, "
                 f"failed={report.failed}")
    return report
