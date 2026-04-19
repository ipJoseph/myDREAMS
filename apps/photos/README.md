# Photo Manager

Single owner of all photo operations for myDREAMS.

## Why this exists

Photo handling was scattered across 10+ files: sync engines downloaded
during sync (stalling the entire process when a CDN URL hung), separate
cron scripts used expired CDN URLs, on-demand downloads used SQLite
directly, and no single module owned the photo lifecycle.

This module replaces all of that. One system, one set of rules.

## Architecture

```
apps/photos/
├── manager.py          # Public API: download_for_listing, run_photo_fill
├── downloader.py       # HTTP fetch with 10s timeout, skip-on-failure
├── storage.py          # File I/O: paths, existence checks, atomic writes
├── cron.py             # Hygiene cron: fill gaps, verify freshness
├── adapters/
│   ├── base.py         # Abstract adapter interface
│   ├── mlsgrid.py      # Canopy: CDN expires, must download locally
│   └── navica.py       # Navica/MountainLakes: CDN stable, can fallback
└── README.md
```

## Key rules (from docs/DECISIONS.md)

1. **Canopy photos MUST be local.** CDN tokens expire.
2. **Navica/MountainLakes CAN use CDN as fallback.** CloudFront is stable.
3. **Download is SEPARATE from sync.** Sync stores fresh URLs; this module downloads.
4. **Skip on failure.** One bad CDN URL never stalls the batch.
5. **Atomic writes.** Temp file + rename prevents serving partial downloads.

## Usage

```bash
# Fill missing primary photos (fast, ~10 min)
python3 -m apps.photos.cron

# Full galleries (slower, ~2 hours)
python3 -m apps.photos.cron --gallery

# Dry run
python3 -m apps.photos.cron --dry-run

# Specific source
python3 -m apps.photos.cron --source NavicaMLS --limit 100
```

## From code

```python
from apps.photos.manager import download_for_listing, download_from_api_response

# During sync (with fresh API response):
result = download_from_api_response(mls_number, prop, mls_source="CanopyMLS")

# Standalone download with known URLs:
result = download_for_listing("CAR4363555", ["https://cdn.../photo.jpg"], "CanopyMLS")
```
