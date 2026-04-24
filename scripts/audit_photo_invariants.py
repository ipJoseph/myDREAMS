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


def _audit_listing(row: Dict, source: str) -> List[str]:
    """Return a list of violation strings for this listing. Empty = clean."""
    violations: List[str] = []
    mls = row.get("mls_number") or f"id={row.get('id')}"

    if not row.get("photo_verified_at"):
        violations.append("photo_verified_at is NULL")

    photos = _parse_photos(row.get("photos"))
    if photos is None:
        violations.append("photos column is empty or malformed JSON")
        return violations

    primary = row.get("primary_photo") or (photos[0] if photos else None)
    if not primary or not primary.startswith(LOCAL_PREFIX):
        violations.append(f"primary_photo not local: {str(primary)[:80]}")

    # Per-MLS strictness: Canopy requires every gallery URL local.
    require_all_local = source in SOURCES_ALL_LOCAL

    photos_dir = storage.get_source_dir(source)
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
            f"{cdn_count}/{len(photos)} photos still have CDN URLs (CanopyMLS requires all local)"
        )

    if missing_files:
        sample = ",".join(missing_files[:3])
        suffix = f" (+{len(missing_files)-3} more)" if len(missing_files) > 3 else ""
        violations.append(f"{len(missing_files)} files missing on disk: {sample}{suffix}")

    return violations


def audit_source(conn, source: str, fix: bool, sample_limit: Optional[int]) -> int:
    """Audit one mls_source. Returns violation count."""
    logger.info("=== auditing source=%s ===", source)

    sql = (
        "SELECT id, mls_number, photos, primary_photo, photo_verified_at, photo_count "
        "FROM listings "
        "WHERE mls_source = ? AND gallery_status = 'ready' "
        "  AND status IN ('ACTIVE', 'PENDING')"
    )
    rows = conn.execute(sql, [source]).fetchall()
    rows = [dict(r) for r in rows]
    logger.info("%s: %d listings claim gallery_status='ready'", source, len(rows))

    if sample_limit and sample_limit < len(rows):
        import random
        random.seed(42)
        rows = random.sample(rows, sample_limit)
        logger.info("%s: sampling %d rows (--sample)", source, len(rows))

    violating_ids: List[int] = []
    by_reason: Dict[str, int] = {}

    for row in rows:
        vs = _audit_listing(row, source)
        if not vs:
            continue
        violating_ids.append(row["id"])
        for v in vs:
            # Coalesce detailed reasons into categories for summary
            key = v.split(":")[0][:60]
            by_reason[key] = by_reason.get(key, 0) + 1
        logger.info("VIOLATION %s: %s", row.get("mls_number"), "; ".join(vs))

    logger.info("%s: %d violations across %d listings", source, sum(by_reason.values()), len(violating_ids))
    for reason, count in sorted(by_reason.items(), key=lambda x: -x[1]):
        logger.info("  %4d x %s", count, reason)

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
        total_violations += audit_source(conn, source, args.fix, args.sample)

    logger.info("===== audit complete: %d total violations =====", total_violations)
    return 1 if total_violations > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
