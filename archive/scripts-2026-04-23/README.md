# Archived photo scripts — 2026-04-23

These three one-shot scripts were written during the 2026-04-20 photo
pipeline incident response. All three are now superseded by:

- `scripts/gallery_backfill_strict.py` — the canonical catchup worker,
  running under `photo-catchup.service` on PRD
- `apps/mlsgrid/sync_engine.py::_download_listing_photos` — inline
  primary+gallery download during sync (commit 49e2d7f)
- `scripts/audit_photo_invariants.py` — invariant check + --fix flipping

## What each script did

### `backfill_truncated_photos.py`
Recovered listings whose `photos[]` array had been truncated to just the
primary during a prior migration bug. Superseded by
`audit_photo_invariants.py --fix` (flags any row where photos_complete is
false and flips to pending for reprocessing) plus the worker's natural
re-download path.

### `download_all_galleries.py`
Bulk gallery downloader, threaded. Superseded by
`gallery_backfill_strict.py` which is single-threaded but matches the
2 rps MLS Grid rate ceiling precisely (the threaded version risked
exceeding it during bursts).

### `fetch_and_download_galleries.py`
Fetched fresh Media URLs per listing via the MLS Grid Media endpoint and
downloaded. Same job as `gallery_backfill_strict.py`; the `_strict`
version has better throttle semantics and commits row-by-row.

## Do not resurrect

These remain deprecated. If a future situation calls for a one-shot
bulk download, write a new script that uses `apps/photos/downloader.py`
and the MLSGridThrottle from `gallery_backfill_strict.py` rather than
reviving anything here.
