# Photo Module Design — apps/photos/

## Why this exists

Photo handling in myDREAMS is scattered across 10+ files, 4 download scripts,
3 serving paths, and 2 MLS-specific adapters. Each was built incrementally
to solve an immediate problem. The result:

- 2,313 active Canopy listings with no local photos (CDN URLs expired)
- 1,219 MountainLakes listings with zero photos (no download handler)
- Gallery downloads are on-demand only (no proactive sweep)
- Navica has no gallery download script and no cron job
- On-demand downloads use SQLite directly (not PostgreSQL)
- CDN URL expiry is handled inconsistently across sources
- No photo freshness tracking or verification

This module replaces all of that with one authoritative system.

## Architecture

```
apps/photos/
├── __init__.py
├── README.md
├── manager.py              # PhotoManager: the public API for all photo operations
├── downloader.py            # Download engine: HTTP fetch, retry, rate limit, workers
├── storage.py               # File I/O: save, exists, path, URL, cleanup
├── freshness.py             # Freshness tracking: verify, stale detection, redownload
├── adapters/
│   ├── __init__.py
│   ├── base.py              # Abstract PhotoAdapter
│   ├── mlsgrid.py           # MLS Grid: token-based CDN, Media API refresh
│   ├── navica.py            # Navica: stable CloudFront URLs
│   └── mountainlakes.py     # MountainLakes (Navica-based)
├── cron.py                  # Scheduled hygiene job
└── tests/
    ├── test_manager.py
    ├── test_storage.py
    └── test_downloader.py
```

## Key classes

### PhotoManager (manager.py)
The single entry point. All photo operations go through here.

```python
class PhotoManager:
    def download_for_listing(self, listing_id: str, media_urls: list) -> PhotoResult:
        """Download primary + gallery for one listing. Called by sync engine."""

    def ensure_primary(self, listing_id: str) -> bool:
        """Ensure primary photo exists locally. Downloads if missing."""

    def get_photo_urls(self, listing: dict) -> PhotoUrls:
        """Return the best available URLs (local > CDN > None) for a listing."""

    def verify_freshness(self, listing_id: str) -> FreshnessResult:
        """Check if photos are current. Redownload if stale."""

    def run_hygiene(self, status: str = 'ACTIVE') -> HygieneReport:
        """Scan all listings, download missing, verify stale. Used by cron."""
```

### PhotoAdapter (adapters/base.py)
Per-MLS interface. Each MLS has different URL formats, auth, rate limits.

```python
class PhotoAdapter:
    name: str                       # 'mlsgrid', 'navica', 'mountainlakes'
    source_dir: str                 # 'mlsgrid' or 'navica' (storage directory)
    cdn_urls_expire: bool           # True for MLS Grid, False for Navica

    def get_fresh_media_urls(self, mls_number: str) -> list[str]:
        """Fetch fresh CDN URLs from the MLS API. For MLS Grid, this calls
        the Media endpoint. For Navica, the CDN URLs don't expire so this
        returns whatever's in the database."""

    def parse_media_from_api_response(self, prop: dict) -> tuple[str, list[str], int]:
        """Extract (primary_url, all_urls, count) from a sync API response."""
```

### PhotoStorage (storage.py)
File I/O abstraction. Today: local disk. Tomorrow: could be S3/Supabase Storage.

```python
class PhotoStorage:
    def primary_path(self, source: str, mls_number: str) -> Path:
        """Return the local file path for a primary photo."""

    def gallery_path(self, source: str, mls_number: str, index: int) -> Path:
        """Return the local file path for a gallery photo."""

    def primary_exists(self, source: str, mls_number: str) -> bool:
        """Check if primary photo exists on disk."""

    def primary_url(self, source: str, mls_number: str) -> str | None:
        """Return the serving URL if the file exists, else None."""

    def gallery_urls(self, source: str, mls_number: str) -> list[str]:
        """Scan disk for all gallery photos, return serving URLs."""

    def save(self, source: str, filename: str, data: bytes) -> Path:
        """Write photo bytes to disk. Atomic (write to temp, then rename)."""
```

## Rules (from docs/DECISIONS.md)

1. **Canopy photos MUST be local.** CDN tokens expire. Never serve CDN URLs
   to the frontend. If no local file exists, show placeholder.

2. **Navica/MountainLakes photos CAN use CDN as fallback.** CloudFront URLs
   are stable. Prefer local, but CDN works as fallback.

3. **Download during sync.** When the sync engine processes a listing, it
   calls `PhotoManager.download_for_listing()` with the fresh Media URLs
   from the API response. No separate download step.

4. **Nightly hygiene cron.** Catches anything the sync missed: listings
   where `photo_local_path IS NULL` but `photo_count > 0`. Also verifies
   photo freshness (has photo_count changed since last download?).

5. **Atomic file writes.** Write to `{filename}.tmp`, then `os.rename()`.
   Prevents partial downloads from being served.

6. **No mixed URL arrays.** The `photos` column in the database should
   contain EITHER all local URLs OR all CDN URLs, never a mix. The
   `localize_photo()` function in listing_service.py handles fallback
   at read time.

## Migration from current code

### What gets replaced

| Current file | Replaced by | Action |
|---|---|---|
| `apps/mlsgrid/download_photos.py` | `apps/photos/manager.py` + `adapters/mlsgrid.py` | Archive |
| `apps/mlsgrid/download_gallery.py` | `apps/photos/manager.py` | Archive |
| `apps/navica/download_photos.py` | `apps/photos/manager.py` + `adapters/navica.py` | Archive |
| `src/core/listing_service.py` `localize_photo()` | `apps/photos/manager.py` `get_photo_urls()` | Replace in-place |
| `apps/property-api/routes/public.py` on-demand download | `apps/photos/manager.py` `ensure_primary()` | Replace in-place |
| Inline photo download in sync_engine.py | Call to `PhotoManager.download_for_listing()` | Replace in-place |

### What stays

| Current | Reason |
|---|---|
| `/api/public/photos/<source>/<filename>` route | Still serves files from disk. No change. |
| `PHOTOS_DIRS` constant | Moves into `PhotoStorage` but same directories. |
| `photo_local_path`, `photos`, `photo_count` DB columns | Same schema, same meaning. |
| Frontend components (PropertyCard, PhotoBrowser) | No change. They consume URLs. |
| `next.config.ts` remotePatterns | No change. |

## Cron schedule

```
# Photo hygiene: fill gaps, verify freshness (runs after MLS sync)
0 4 * * * cd /opt/mydreams && DATABASE_URL=... python3 -m apps.photos.cron >> data/logs/photo-hygiene.log 2>&1
```

The nightly 3 AM primary download cron and the on-demand gallery download
are both replaced by this single hygiene job + sync-time downloads.

## Verification

After the module is built:

1. `python3 -m apps.photos.cron --dry-run` reports how many listings need photos
2. `python3 -m apps.photos.cron` downloads them
3. Homepage shows photos for ALL listings (zero placeholders on active listings with photo_count > 0)
4. Listing detail page shows full gallery
5. New listings synced via incremental sync have photos within minutes
6. `apps/photos/tests/` all pass
