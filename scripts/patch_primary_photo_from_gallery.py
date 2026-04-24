"""Pure-DB patcher: set primary_photo = photos[0] where the gallery is
already local on disk but primary_photo still holds a stale CDN URL.

Background
----------
Before the 2026-04-23 refactor, the sync engine wrote local paths into
`photos` (the JSON array) but never updated the `primary_photo` column.
That left thousands of listings with a mixed state:

    photos       = ["/api/public/photos/mlsgrid/CAR12345.jpg", "/api/..."]
    primary_photo = "https://media.mlsgrid.com/token=...&expires=..."

The audit flags these as "primary_photo not local (CDN URL)" — but the
gallery_backfill_strict worker's `--only-stale` filter looks at
`photos[]`, not `primary_photo`. So when audit --fix flips these rows
to pending, the worker skips them because their gallery is already
fully local, and they stay pending forever.

This script closes that gap with zero HTTP calls and zero disk writes —
pure DB work.

Usage
-----
    # Report only (dry-run)
    python3 scripts/patch_primary_photo_from_gallery.py --source CanopyMLS

    # Apply the fix
    python3 scripts/patch_primary_photo_from_gallery.py --source CanopyMLS --fix

    # Also flip gallery_status back to 'ready' for the listings we just
    # corrected (so they reappear on the public site):
    python3 scripts/patch_primary_photo_from_gallery.py --source CanopyMLS --fix --mark-ready
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from apps.photos import storage  # noqa: E402
from src.core.pg_adapter import get_db  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("patch_primary_photo")

LOCAL_PREFIX = "/api/public/photos/"


def _first_local(photos_raw) -> str | None:
    """Return the first element of `photos` that looks like a local URL, or None."""
    if not photos_raw:
        return None
    try:
        arr = json.loads(photos_raw) if isinstance(photos_raw, str) else photos_raw
    except Exception:
        return None
    if not isinstance(arr, list) or not arr:
        return None
    head = arr[0]
    if isinstance(head, str) and head.startswith(LOCAL_PREFIX):
        return head
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="CanopyMLS")
    ap.add_argument("--fix", action="store_true",
                    help="Apply the update; default is dry-run.")
    ap.add_argument("--mark-ready", action="store_true",
                    help="Also flip gallery_status to 'ready' (use after "
                         "verifying --fix ran cleanly). Implies --fix.")
    args = ap.parse_args()

    if args.mark_ready and not args.fix:
        args.fix = True

    conn = get_db()

    # Find rows where primary_photo is CDN (starts with http) but the
    # gallery's first element is local. We only consider ACTIVE/PENDING
    # status because those are the visible-on-site rows.
    # LIKE pattern is parameterized so psycopg2's %s-format path doesn't
    # try to interpret the % in 'http%' as a format marker.
    rows = conn.execute(
        "SELECT id, mls_number, primary_photo, photos, gallery_status "
        "FROM listings "
        "WHERE mls_source = ? "
        "  AND status IN ('ACTIVE', 'PENDING') "
        "  AND primary_photo IS NOT NULL "
        "  AND primary_photo LIKE ?",
        [args.source, "http%"],
    ).fetchall()
    rows = [dict(r) for r in rows]
    logger.info(
        "%s: %d rows with CDN primary_photo in active/pending status",
        args.source, len(rows),
    )

    fixable: List[dict] = []
    for row in rows:
        first_local = _first_local(row.get("photos"))
        if not first_local:
            continue
        # Verify the file actually exists on disk before swapping
        filename = first_local.rsplit("/", 1)[-1]
        photos_dir = storage.get_source_dir(args.source)
        if not (photos_dir / filename).exists():
            continue
        fixable.append({
            "id": row["id"],
            "mls_number": row["mls_number"],
            "new_primary": first_local,
            "gallery_status": row["gallery_status"],
        })

    logger.info(
        "%s: %d of %d rows can be patched (gallery[0] is local AND file exists)",
        args.source, len(fixable), len(rows),
    )

    if not fixable:
        return 0

    # Show a few examples
    for f in fixable[:5]:
        logger.info(
            "  example: %s (status=%s) -> %s",
            f["mls_number"], f["gallery_status"], f["new_primary"][:60],
        )

    if not args.fix:
        logger.info("(dry-run; pass --fix to apply)")
        return 0

    # Apply in batches of 500 to avoid one giant transaction
    BATCH = 500
    updated = 0
    flipped_ready = 0
    for i in range(0, len(fixable), BATCH):
        chunk = fixable[i : i + BATCH]
        try:
            for f in chunk:
                conn.execute(
                    "UPDATE listings SET primary_photo = ? WHERE id = ?",
                    [f["new_primary"], f["id"]],
                )
                updated += 1
                if args.mark_ready and f["gallery_status"] != "ready":
                    conn.execute(
                        "UPDATE listings SET gallery_status = 'ready', "
                        "photo_verified_at = CURRENT_TIMESTAMP WHERE id = ?",
                        [f["id"]],
                    )
                    flipped_ready += 1
            conn.commit()
            logger.info("  committed %d/%d", updated, len(fixable))
        except Exception as e:
            logger.warning("batch starting at %d failed: %s", i, e)
            try: conn.rollback()
            except Exception: pass

    logger.info(
        "%s: patched primary_photo on %d rows; flipped to ready on %d rows",
        args.source, updated, flipped_ready,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
