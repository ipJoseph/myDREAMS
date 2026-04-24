"""Photo pipeline invariant audit.

Verifies `docs/PHOTO_PIPELINE_SPEC.md` invariants #1 and #2 for every
listing that claims `gallery_status = 'ready'`. If the claim is a lie
(non-local URLs in `photos[]`, files missing on disk, or
`photo_verified_at` null), the script reports it and, with --fix, flips
the row back to 'pending' so the gallery worker reprocesses it.

Usage:
    # Report only (cron-safe, exits 1 on any violation)
    python3 scripts/audit_photo_invariants.py --source CanopyMLS

    # Report and heal (flips liars to pending)
    python3 scripts/audit_photo_invariants.py --source CanopyMLS --fix

    # All sources at once
    python3 scripts/audit_photo_invariants.py --source all

Per-MLS rules (from plan/i-am-at-a-radiant-stearns.md):
    CanopyMLS        — every photos[] element must be local
    NavicaMLS        — primary_photo must be local; photos[] may be CDN
    MountainLakesMLS — primary_photo must be local; photos[] may be CDN
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
logger = logging.getLogger("audit_photo_invariants")

LOCAL_PREFIX = "/api/public/photos/"
SOURCES_ALL = ("CanopyMLS", "NavicaMLS", "MountainLakesMLS")
SOURCES_ALL_LOCAL = ("CanopyMLS",)  # entire gallery must be local


def _parse_photos(photos_raw) -> Optional[List[str]]:
    """Parse the photos column into a list of strings, or None on malformed."""
    if not photos_raw:
        return None
    if isinstance(photos_raw, list):
        return [str(u) for u in photos_raw]
    try:
        parsed = json.loads(photos_raw) if isinstance(photos_raw, str) else photos_raw
    except Exception:
        return None
    if not isinstance(parsed, list):
        return None
    return [str(u) for u in parsed]


def _audit_listing(row: Dict, source: str) -> List[Tuple[str, str]]:
    """Return a list of (category, detail) violation tuples. Empty = clean.

    Category strings are stable across listings so cron summaries can
    roll up counts; detail strings are per-listing and human-readable.
    """
    violations: List[Tuple[str, str]] = []

    if not row.get("photo_verified_at"):
        violations.append(("photo_verified_at is NULL", ""))

    photos = _parse_photos(row.get("photos"))
    if photos is None:
        violations.append(("photos column empty or malformed", ""))
        return violations

    primary = row.get("primary_photo") or (photos[0] if photos else None)
    photos_dir = storage.get_source_dir(source)

    if not primary or not primary.startswith(LOCAL_PREFIX):
        violations.append(
            ("primary_photo not local (CDN URL)", str(primary)[:80])
        )
    elif primary and primary.startswith(LOCAL_PREFIX):
        # Primary path claims to be local — verify the file actually exists.
        # photos[] may or may not include primary; check independently.
        primary_filename = primary.rsplit("/", 1)[-1]
        if not (photos_dir / primary_filename).exists():
            violations.append(
                ("primary_photo file missing on disk", primary_filename)
            )

    # Per-MLS strictness: Canopy requires every gallery URL local.
    require_all_local = source in SOURCES_ALL_LOCAL
    cdn_count = 0
    missing_files: List[str] = []
    for u in photos:
        if not u.startswith(LOCAL_PREFIX):
            cdn_count += 1
            continue
        filename = u.rsplit("/", 1)[-1]
        if not (photos_dir / filename).exists():
            missing_files.append(filename)

    if require_all_local and cdn_count:
        violations.append(
            ("gallery has CDN URLs (strict-local source)",
             f"{cdn_count}/{len(photos)} non-local")
        )

    if missing_files:
        sample = ",".join(missing_files[:3])
        suffix = f" (+{len(missing_files)-3} more)" if len(missing_files) > 3 else ""
        violations.append(
            ("gallery files missing on disk",
             f"{len(missing_files)} missing: {sample}{suffix}")
        )

    return violations


def audit_source(conn, source: str, fix: bool, sample_limit: Optional[int],
                 verbose: bool) -> int:
    """Audit one mls_source. Returns violation count."""
    # Audit scope matches the public-grid filter (see
    # src/core/listing_service._build_conditions when require_idx=True):
    # idx_opt_in=1 AND status IN ('ACTIVE','PENDING') AND
    # gallery_status='ready'. Listings outside that set never render to
    # users, so flagging them as "violations" is noise — these are
    # intentionally opted-out records. The hourly cron would email on
    # every run if we kept them in scope.
    sql = (
        "SELECT id, mls_number, photos, primary_photo, photo_verified_at, photo_count "
        "FROM listings "
        "WHERE mls_source = ? AND gallery_status = 'ready' "
        "  AND status IN ('ACTIVE', 'PENDING') "
        "  AND idx_opt_in = 1"
    )
    rows = conn.execute(sql, [source]).fetchall()
    rows = [dict(r) for r in rows]

    if sample_limit and sample_limit < len(rows):
        import random
        random.seed(42)
        rows = random.sample(rows, sample_limit)

    violating_ids: List[int] = []
    examples_by_category: Dict[str, List[str]] = {}
    by_category: Dict[str, int] = {}

    for row in rows:
        vs = _audit_listing(row, source)
        if not vs:
            continue
        violating_ids.append(row["id"])
        mls = row.get("mls_number") or f"id={row['id']}"
        for category, detail in vs:
            by_category[category] = by_category.get(category, 0) + 1
            if category not in examples_by_category:
                examples_by_category[category] = []
            if len(examples_by_category[category]) < 5:
                examples_by_category[category].append(mls)
        if verbose:
            per_listing = "; ".join(f"{c}" + (f" [{d}]" if d else "") for c, d in vs)
            logger.info("VIOLATION %s: %s", mls, per_listing)

    # One-line summary per source (quiet by default — cron-friendly).
    logger.info(
        "%s: %d listings checked, %d distinct violators, %d violations across categories",
        source, len(rows), len(violating_ids), sum(by_category.values()),
    )
    for category, count in sorted(by_category.items(), key=lambda x: -x[1]):
        examples = ",".join(examples_by_category.get(category, [])[:3])
        logger.info("  %6d x %s [e.g. %s]", count, category, examples)

    if violating_ids and fix:
        # Flip liars to pending so the gallery worker picks them up.
        # Invariant #2 requires photo_verified_at nulled on non-ready state.
        placeholders = ",".join(["?"] * len(violating_ids))
        conn.execute(
            f"UPDATE listings SET gallery_status = 'pending' WHERE id IN ({placeholders})",
            violating_ids,
        )
        conn.commit()
        logger.info("%s: flipped %d rows to 'pending' (--fix)", source, len(violating_ids))

    return len(violating_ids)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--source", default="CanopyMLS",
        help="mls_source to audit (default CanopyMLS). Use 'all' for every source.",
    )
    ap.add_argument(
        "--fix", action="store_true",
        help="Flip violating rows from 'ready' to 'pending' so the worker can reprocess them.",
    )
    ap.add_argument(
        "--sample", type=int, default=None,
        help="Audit only a random sample of N rows per source (for quick spot checks).",
    )
    ap.add_argument(
        "--verbose", "-v", action="store_true",
        help="Log every violating listing individually. Default: categorized summary only.",
    )
    args = ap.parse_args()

    if args.source == "all":
        sources = list(SOURCES_ALL)
    else:
        if args.source not in SOURCES_ALL:
            logger.error("Unknown source %r. Valid: %s, all", args.source, SOURCES_ALL)
            return 2
        sources = [args.source]

    conn = get_db()
    total_violations = 0
    for source in sources:
        total_violations += audit_source(conn, source, args.fix, args.sample, args.verbose)

    logger.info("===== audit complete: %d total violations =====", total_violations)
    return 1 if total_violations > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
